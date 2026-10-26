/** Real isolated Microsoft Edge E2E of EvidenceTrail WHY provenance panel.
 * Starts ONLY the local sample-mode Python API with an ephemeral loopback
 * port. No vendor keys, model calls, external government HTTP or SQL reads.
 */
import {spawn} from "node:child_process";
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {join,resolve} from "node:path";
import {createHash} from "node:crypto";

const ROOT=resolve(import.meta.dirname,"..");
const EDGE="C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const runTag=String(Date.now());
const profile=join(ROOT,"acceptance","logs","why-edge-"+runTag);
const evidenceDir=join(ROOT,"acceptance","logs","why-browser-run-"+runTag);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const safeEnv={};
for(const k of ["PATH","PATHEXT","SYSTEMROOT","WINDIR","TEMP","TMP",
                 "USERPROFILE","APPDATA","LOCALAPPDATA","COMSPEC",
                 "PROGRAMFILES","PROGRAMFILES(X86)"]){
 if(process.env[k])safeEnv[k]=process.env[k];
}
safeEnv.PYTHONDONTWRITEBYTECODE="1";
await mkdir(profile,{recursive:true});
await mkdir(evidenceDir,{recursive:true});
const serverSrc=[
 "from evidencetrail.api import create_local_server",
 "s=create_local_server('127.0.0.1',0)",
 "print('WHY_PORT='+str(s.server_port),flush=True)",
 "s.serve_forever()"
].join(";");
const server=spawn("py",["-3","-u","-c",serverSrc],
 {cwd:ROOT,env:safeEnv,windowsHide:true,stdio:["ignore","pipe","pipe"]});
let output="",serverError="";
server.stdout.setEncoding("utf8");server.stderr.setEncoding("utf8");
server.stdout.on("data",c=>{output+=c});
server.stderr.on("data",c=>{serverError+=c.slice(0,200)});
let edge,ws;
try{
 let port;
 for(let i=0;i<100;i++){
  const match=output.match(/WHY_PORT=(\d+)/);
  if(match){port=Number(match[1]);break}
  if(server.exitCode!==null)throw Error("OFFLINE_LOOPBACK_API_EXITED");
  await sleep(100);
 }
 if(!port)throw Error("OFFLINE_API_PORT_NOT_READY");
 const local="http://127.0.0.1:"+port;
 edge=spawn(EDGE,["--headless=new","--no-first-run","--disable-sync",
   "--disable-extensions","--remote-debugging-port=0",
   "--user-data-dir="+profile,"--window-size=1280,960",local+"/why"],
   {env:safeEnv,windowsHide:true,stdio:"ignore"});
 let cdpPort;
 for(let i=0;i<100;i++){
  try{cdpPort=Number((await readFile(join(profile,"DevToolsActivePort"),
                                  "utf8")).split(/\r?\n/)[0]);if(cdpPort)break}catch{}
  await sleep(130);
 }
 if(!cdpPort)throw Error("EDGE_DEBUG_PORT_MISSING");
 let page;
 for(let i=0;i<100;i++){
  const pages=await fetch("http://127.0.0.1:"+cdpPort+"/json/list")
   .then(r=>r.json()).catch(()=>[]);
  page=pages.find(x=>x.type==="page"&&x.url===local+"/why");
  if(page)break;
  await sleep(130);
 }
 if(!page)throw Error("WHY_TAB_NOT_FOUND");
 ws=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((yes,no)=>{
  ws.addEventListener("open",yes,{once:true});
  ws.addEventListener("error",no,{once:true});
 });
 let counter=0;const waiting=new Map();
 ws.addEventListener("message",ev=>{
  let msg;try{msg=JSON.parse(String(ev.data))}catch{return}
  const w=waiting.get(msg.id);if(!w)return;
  clearTimeout(w.timer);waiting.delete(msg.id);
  msg.error?w.reject(Error("CDP_ERROR_"+msg.error.message)):w.resolve(msg.result);
 });
 const rpc=(method,params={})=>new Promise((resolve,reject)=>{
  const id=++counter;
  const timer=setTimeout(()=>{waiting.delete(id);reject(Error("CDP_TIMEOUT_"+method))},20000);
  waiting.set(id,{resolve,reject,timer});
  ws.send(JSON.stringify({id,method,params}));
 });
 const ev=async expression=>{
  const x=await rpc("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});
  if(x.exceptionDetails)throw Error("WHY_SCRIPT_EXCEPTION");
  return x.result.value;
 };
 await rpc("Page.enable");await rpc("Runtime.enable");
 const ready=async()=>ev(`document.getElementById('status')?.textContent ===
       'Verified local source-pinned replay'`);
 let started=false;
 for(let i=0;i<90;i++){if(await ready()){started=true;break}await sleep(140)}
 if(!started)throw Error("WHY_DATA_NOT_LOADED");
 const first=await ev(`({
  claims:document.getElementById('claims').textContent,
  timeline:document.getElementById('timeline').children.length,
  sources:document.getElementById('removed').options.length
 })`);
 if(!first.claims.includes("100 mph")||!first.claims.includes("51 counties")
    ||first.timeline!==7||first.sources!==7)throw Error("WHY_11AM_BASELINE_MISMATCH");
 console.log("WHY_EDGE_ASOF_11AM_PASS_100_51");
 const evidenceMap=await ev(`({title:document.getElementById('evidenceMapHeading').textContent,
  sourceCount:document.querySelectorAll('#mapSources button').length,
  claims:document.getElementById('mapConclusion').textContent,
  impact:document.getElementById('mapImpactText').textContent})`);
 if(evidenceMap.title!=="What supports this conclusion?"||evidenceMap.sourceCount!==7||
    !evidenceMap.claims.includes("100 mph")||!evidenceMap.claims.includes("51 counties")||
    !evidenceMap.impact.includes("51 counties → 35 counties"))
  throw Error("WHY_EVIDENCE_MAP_BASELINE_MISMATCH_"+JSON.stringify(evidenceMap));
 await ev(`document.querySelector('#mapSources button[aria-label="Preview removing source NHC-AL142024-PUBLIC-008"]').click()`);
 const mapAfterRemoval=await ev(`({impact:document.getElementById('mapImpactText').textContent,
  pressed:document.querySelector('#mapSources button[aria-label="Preview removing source NHC-AL142024-PUBLIC-008"]').getAttribute('aria-pressed'),
  detail:document.getElementById('removal').textContent})`);
 if(!mapAfterRemoval.impact.includes("100 mph → No admissible claim")||
    mapAfterRemoval.pressed!=="true"||!mapAfterRemoval.detail.includes("ABSTAIN"))
  throw Error("WHY_EVIDENCE_MAP_WITHDRAWAL_MISMATCH_"+JSON.stringify(mapAfterRemoval));
 await ev(`document.querySelector('#mapSources button[aria-label="Preview removing source FL-EO-24-215"]').click()`);
 if(!await ev(`document.getElementById('mapImpactText').textContent.includes('51 counties → 35 counties')`))
  throw Error("WHY_EVIDENCE_MAP_RESTORE_MISMATCH");
 console.log("WHY_EDGE_EVIDENCE_MAP_SOURCE_TO_CLAIM_AND_WITHDRAWAL_PASS");
 // Product layout invariants, real keyboard operation and reduced-motion state.
 await rpc("Emulation.setEmulatedMedia",{features:[{name:"prefers-reduced-motion",value:"reduce"}]});
 for(const width of [375,768,1440]){
  await rpc("Emulation.setDeviceMetricsOverride",{width,height:960,deviceScaleFactor:1,mobile:false});
  const layout=await ev(`(()=>{
   const root=document.documentElement,claim=document.getElementById('conclusion');
   return {overflow:root.scrollWidth>innerWidth+1,
    nav:[...document.querySelectorAll('nav[aria-label="EvidenceTrail views"] a')].every(a=>a.getBoundingClientRect().width>0),
    claimWidth:claim.getBoundingClientRect().width,
    order:!!(claim.compareDocumentPosition(document.getElementById('coalitionPanel'))&Node.DOCUMENT_POSITION_FOLLOWING),
    target:document.getElementById('createCase').getBoundingClientRect().height,
    scrollbar:getComputedStyle(root).scrollbarColor,
    reduced:matchMedia('(prefers-reduced-motion: reduce)').matches};})()`);
  if(layout.overflow||!layout.nav||layout.claimWidth<280||!layout.order||layout.target<44||layout.scrollbar==='auto'||!layout.reduced)
   throw Error('UI_LAYOUT_OR_ACCESSIBILITY_'+width+'_'+JSON.stringify(layout));
  await ev('scrollTo(0,0)');
  const shot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await writeFile(join(evidenceDir,'why-'+width+'.png'),Buffer.from(shot.data,'base64'));
 }
 await ev(`document.getElementById('evidenceMapHeading').scrollIntoView({block:'start',behavior:'instant'})`);
 const mapShot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile(join(evidenceDir,'evidence-map-1440.png'),Buffer.from(mapShot.data,'base64'));
 await ev(`document.getElementById('asof').focus()`);
 await rpc('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
 await rpc('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
 if(!await ev(`document.getElementById('asof').value==='2024-10-07T15:00:00Z' && document.activeElement.id==='asof'`))
  throw Error('NATIVE_SELECT_KEYBOARD_FAILED');
 await ev(`document.getElementById('asof').value='2024-10-07T11:00:00Z'`);
 await ev(`document.getElementById('createCase').focus()`);
 await rpc('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',unmodifiedText:'\r',windowsVirtualKeyCode:13});
 await rpc('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
 if(!await ev(`!document.getElementById('caseEditor').hidden && document.activeElement.id==='draftCaseId'`))
  throw Error('EDITOR_KEYBOARD_FOCUS_FAILED_'+await ev(`JSON.stringify({active:document.activeElement.id,hidden:document.getElementById('caseEditor').hidden,run:document.getElementById('run').disabled})`));
 await ev(`(()=>{const t=document.querySelector('#sourceRows textarea');t.value='Source excerpt with multiple words. '.repeat(60);t.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await rpc('Emulation.setDeviceMetricsOverride',{width:375,height:960,deviceScaleFactor:1,mobile:false});
 let reflowed=false;
 for(let i=0;i<40;i++){
  reflowed=await ev(`(()=>{const t=document.querySelector('#sourceRows textarea');return t.clientHeight>=t.scrollHeight-3&&document.documentElement.scrollWidth<=innerWidth+1;})()`);
  if(reflowed)break;await sleep(50);
 }
 if(!reflowed)throw Error('LONG_EXCERPT_CLIPPED_AFTER_MOBILE_REFLOW');
 await ev(`document.querySelector('#sourceRows textarea').scrollIntoView({block:'center'})`);
 const mobileForm=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile(join(evidenceDir,'source-form-375.png'),Buffer.from(mobileForm.data,'base64'));
 await rpc('Emulation.setDeviceMetricsOverride',{width:1440,height:960,deviceScaleFactor:1,mobile:false});
 await ev(`document.getElementById('draftTitle').value='Retain my draft';document.getElementById('draftTitle').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('cancelDraft').click()`);
 if(!await ev(`document.activeElement.id==='createCase'`))throw Error('CANCEL_FOCUS_NOT_RESTORED');
 await ev(`document.getElementById('createCase').click()`);
 if(!await ev(`document.getElementById('draftTitle').value==='Retain my draft' && document.getElementById('adoptDraft').disabled`))
  throw Error('CANCELLED_DRAFT_RECOVERY_FAILED');
 await ev(`document.getElementById('cancelDraft').click();window.caseWorkbench.reset();document.getElementById('status').textContent='Verified local source-pinned replay'`);
 console.log('UI_EDGE_RESPONSIVE_375_768_1440_KEYBOARD_DRAFT_RECOVERY_PASS');
 const missing=await ev(`({
  needed:document.getElementById('needed')?.textContent,
  excluded:document.getElementById('unavailable')?.textContent,
  clock:document.getElementById('metrics').textContent
 })`);
 if(!missing.needed?.includes("FL_PRESS")||
    !missing.needed.includes("NO_SOURCE_ADMISSIBLE_AT_AS_OF")||
    !missing.excluded?.includes("NHC-AL142024-PUBLIC-010")||
    !missing.clock.includes("2024-10-07T11:00:00Z"))
  throw Error("WHY_MISSING_EVIDENCE_EXPLANATION_ABSENT");
 console.log("WHY_EDGE_MISSING_EVIDENCE_AND_CLOCK_PASS");
 await ev(`(()=>{
  const select=document.getElementById("removed");
  select.value="FL-EO-24-215";
  select.dispatchEvent(new Event("change",{bubbles:true}));
 })()`);
 const removing=await ev("document.getElementById('removal').textContent");
 if(!removing.includes("35 counties")||!removing.includes("51 counties"))
  throw Error("WHY_REMOVAL_FALLBACK_MISMATCH");
 console.log("WHY_EDGE_REMOVE_FL_215_PASS_FALLBACK_35");
 await ev(`(()=>{
  document.getElementById("asof").value="2024-10-07T15:00:00Z";
  document.getElementById("controls").requestSubmit();
 })()`);
 let after;
 for(let i=0;i<90;i++){
  after=await ev("document.getElementById('claims').textContent");
  if(after.includes("155 mph"))break;await sleep(140);
 }
 if(!after?.includes("155 mph"))throw Error("WHY_15PM_EXPECTED_155_MISSING");
 await ev(`(()=>{
  const select=document.getElementById("removed");
  select.value="NHC-AL142024-PUBLIC-010";
  select.dispatchEvent(new Event("change",{bubbles:true}));
 })()`);
 const changed=await ev("document.getElementById('removal').textContent");
 if(!changed.includes("125 mph")||!changed.includes("155 mph"))
  throw Error("WHY_155_TO_125_REMOVAL_MISMATCH");
 console.log("WHY_EDGE_REMOVE_NHC_010_PASS_FALLBACK_125");
 await ev(`(()=>{
  document.getElementById("mode").value="strict";
  document.getElementById("controls").requestSubmit();
 })()`);
 let abstained=false;
 for(let i=0;i<90;i++){
  abstained=await ev(`document.getElementById('claims').textContent.includes('ABSTAIN')
     && document.getElementById('timeline').textContent.includes('Strict policy')`);
  if(abstained)break;await sleep(140);
 }
 if(!abstained)throw Error("WHY_STRICT_ABSTENTION_MISSING");
 const strictNeed=await ev("document.getElementById('needed').textContent");
 if(!strictNeed.includes("ORIGINAL_AVAILABILITY_ATTESTATION_REQUIRED")||
    !strictNeed.includes("does not yet admit external attestations"))
  throw Error("WHY_STRICT_NEXT_EVIDENCE_MISSING");
 const screenshot=await rpc("Page.captureScreenshot",{format:"png",
                                                    captureBeyondViewport:false});
 const target=join(evidenceDir,"why-counterfactual-edge.png");
 await writeFile(target,Buffer.from(screenshot.data,"base64"));
 console.log("WHY_EDGE_STRICT_ABSTAIN_PASS_SCREENSHOT",target);
 // New open-case workflow; these robot cases are never external user evidence.
 const waitFor=async expression=>{
  for(let i=0;i<100;i++){if(await ev(expression))return;await sleep(120)}
  console.error("LOCAL_UI_STATE",await ev(`({error:document.getElementById('draftErrors')?.textContent,
   preview:document.getElementById('draftPreview')?.textContent,update:document.getElementById('updateSummary')?.textContent,
   claims:document.getElementById('claims')?.textContent})`));
  throw Error("OPEN_CASE_UI_CONDITION_TIMEOUT: "+expression);
 };
 await ev("document.getElementById('warehouseExample').click()");
 await waitFor("document.getElementById('claims').textContent.includes('25 pallets') && document.getElementById('cutsets').textContent.includes('2 source(s)')");
 const sourceCase=await ev(`({status:document.getElementById('caseStatus').textContent,
   claims:document.getElementById('claims').textContent,coverage:document.getElementById('searchCoverage').textContent})`);
 if(!sourceCase.status.includes("OPERATOR_DECLARED_NOT_EXTERNALLY_VERIFIED")||
    !sourceCase.claims.includes("FICTIONAL SOURCE")||!sourceCase.coverage.includes("6 source subsets"))
  throw Error("OPEN_CASE_TRUST_OR_SEARCH_BOUND_MISSING");
 console.log("OPEN_CASE_EDGE_REDUNDANCY_MINIMUM_TWO_PASS");
 await ev(`(()=>{
  const checkbox=document.querySelector('#jointSources input[value="STOCK-LEDGER"]');
  checkbox.checked=true;checkbox.dispatchEvent(new Event('change',{bubbles:true}));
  document.getElementById('testJoint').click();
 })()`);
 await waitFor("document.getElementById('jointEffect').textContent.includes('STOCK-LEDGER') && document.getElementById('jointEffect').textContent.includes('Claim values unchanged')");
 await ev(`(()=>{
  const checkbox=document.querySelector('#jointSources input[value="STOCK-CHECK"]');
  checkbox.checked=true;checkbox.dispatchEvent(new Event('change',{bubbles:true}));
  document.getElementById('testJoint').click();
 })()`);
 await waitFor("document.getElementById('jointEffect').textContent.includes('12 pallets') && document.getElementById('jointEffect').textContent.includes('25 pallets')");
 console.log("OPEN_CASE_EDGE_JOINT_WITHDRAWAL_25_TO_12_PASS");
 await ev("document.getElementById('coalitionPanel').scrollIntoView({block:'start'})");
 const coalitionShot=await rpc("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
 await writeFile(join(evidenceDir,"open-case-warehouse-edge.png"),Buffer.from(coalitionShot.data,"base64"));
 await ev("document.getElementById('searchDepth').value='1';document.getElementById('controls').requestSubmit()");
 await waitFor("document.getElementById('searchCoverage').textContent.includes('through size 1') && document.getElementById('cutsets').textContent.includes('At least 2')");
 const packet=await fetch(local+"/case-examples/warehouse").then(r=>r.json());
 packet.case_id="JUDGE-FILE-IMPORT-FICTIONAL";
 packet.title="Programmatic file import: unseen 73-pallet case";
 packet.as_of_utc="2026-10-24T09:00:00.500000Z";
 for(const row of packet.sources){
  if(!["STOCK-LEDGER","STOCK-CHECK"].includes(row.source_id))continue;
  row.observation_fields.value=73;
  row.excerpt="FICTIONAL new imported test "+row.source_id+" declares 73 pallets.";
  row.paraphrase=row.excerpt;
  row.excerpt_sha256=createHash("sha256").update(row.excerpt).digest("hex");
  const pin=packet.pins.find(p=>p.source_id===row.source_id);
  pin.expected_value=73;pin.excerpt_sha256=row.excerpt_sha256;
  row.published_at_displayed_utc=row.issued_at_claimed_utc="2026-10-24T09:00:00.250000Z";
  pin.claimed_issue_utc="2026-10-24T09:00:00.250000Z";
 }
 const importFile=join(profile,"unseen.case.json");
 await writeFile(importFile,JSON.stringify(packet));
 const documentNode=await rpc("DOM.getDocument",{depth:0});
 const fileNode=await rpc("DOM.querySelector",{nodeId:documentNode.root.nodeId,selector:"#casefile"});
 await rpc("DOM.setFileInputFiles",{nodeId:fileNode.nodeId,files:[importFile]});
 await waitFor("document.getElementById('claims').textContent.includes('73 pallets') && document.getElementById('caseStatus').textContent.includes('unseen 73-pallet')");
 if(await ev("document.getElementById('caseClock').value")!==packet.as_of_utc)
  throw Error("OPEN_CASE_IMPORTED_PRECISE_CLOCK_CHANGED");
 console.log("OPEN_CASE_EDGE_REAL_FILE_IMPORT_UNSEEN_73_PASS");
 // A late example response must not replace a newer file import or its replay.
 await ev(`(()=>{
  window.originalCaseFetch=window.fetch;
  window.releaseExample=null;window.releaseImportedReplay=null;
  window.fetch=(url,options)=>{
   if(url==='/case-examples/warehouse')return new Promise(resolve=>{
    window.releaseExample=()=>resolve(window.originalCaseFetch(url,options));
   });
   if(url==='/case-investigation' && JSON.parse(options.body).case.case_id==='JUDGE-FILE-IMPORT-FICTIONAL')
    return new Promise(resolve=>{window.releaseImportedReplay=()=>resolve(window.originalCaseFetch(url,options));});
   return window.originalCaseFetch(url,options);
  };
  document.getElementById('casefile').value='';
  document.getElementById('warehouseExample').click();
 })()`);
 await rpc("DOM.setFileInputFiles",{nodeId:fileNode.nodeId,files:[importFile]});
 await waitFor("typeof window.releaseImportedReplay==='function'");
 await ev("window.releaseExample()");
 await sleep(300);
 await ev("window.releaseImportedReplay();window.fetch=window.originalCaseFetch");
 await waitFor("document.getElementById('caseStatus').textContent.includes('unseen 73-pallet') && !document.getElementById('run').disabled");
 await ev("document.getElementById('controls').requestSubmit()");
 await waitFor("!document.getElementById('run').disabled");
 if(!await ev("document.getElementById('claims').textContent.includes('73 pallets') && document.getElementById('caseStatus').textContent.includes('unseen 73-pallet')"))
  throw Error("OPEN_CASE_LATE_EXAMPLE_REPLACED_NEWER_FILE_IMPORT");
 console.log("OPEN_CASE_EDGE_OVERLAPPING_LOAD_LATEST_INTENT_PASS");
 await ev("document.getElementById('mode').value='strict';document.getElementById('controls').requestSubmit()");
 await waitFor("document.getElementById('claims').textContent.includes('ABSTAIN') && document.getElementById('needed').textContent.includes('ORIGINAL_AVAILABILITY_ATTESTATION_REQUIRED')");
 const damaged=structuredClone(packet);damaged.sources.at(-1).excerpt="Tampered future source";
 const badFile=join(profile,"damaged-future.case.json");
 await writeFile(badFile,JSON.stringify(damaged));
 await rpc("DOM.setFileInputFiles",{nodeId:fileNode.nodeId,files:[badFile]});
 await waitFor("document.getElementById('status').textContent==='Replay unavailable' && !document.getElementById('claims').textContent.includes('73 pallets') && document.getElementById('coalitionPanel').hidden");
 console.log("OPEN_CASE_EDGE_TAMPERED_FUTURE_REFUSED_NO_STALE_RESULT_PASS");
 // Author a case without editing JSON or computing source hashes.
 await ev("document.getElementById('createCase').click()");
 const enterRow=async({id,value,clock})=>ev(`(()=>{
  const row=document.querySelector('#sourceRows .source-row');
  const fields={source_id:${JSON.stringify(id)},claim_key:'STOCK',issuer_family:'USER_LOG',
    unit:'pallets',value:${JSON.stringify(value)},publisher:'Fictional browser exercise',
    locator:${JSON.stringify('synthetic://browser/'+id)},excerpt:${JSON.stringify('FICTIONAL '+id+' declares '+value+' pallets.')},
    source_type:'fictional',clock_type:'precise',issued_at:${JSON.stringify(clock)}};
  for(const [key,val] of Object.entries(fields)){
   const input=row.querySelector('[data-field="'+key+'"]');input.value=val;
   input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  }
 })()`);
 await ev(`(()=>{
  for(const [id,val] of Object.entries({draftCaseId:'BROWSER-AUTHORED',draftTitle:'Authored in the source form',
    draftQuestion:'Which declaration changes the stock?',draftClock:'2025-02-04T09:00:00.500000Z'})){
   const input=document.getElementById(id);input.value=val;input.dispatchEvent(new Event('input',{bubbles:true}));
  }
 })()`);
 await enterRow({id:'REF-A',value:'73',clock:'2025-02-04T08:00:00Z'});
 await ev("document.getElementById('previewDraft').click()");
 await waitFor("document.getElementById('draftPreview').textContent.includes('73 pallets') && !document.getElementById('draftReviewed').disabled");
 await ev(`(()=>{const i=document.querySelector('#sourceRows [data-field="value"]');
  i.value='74';i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 if(!await ev("document.getElementById('adoptDraft').disabled && document.getElementById('draftPreview').textContent===''") )
  throw Error("WORKBENCH_EDIT_REUSED_STALE_PREVIEW");
 await enterRow({id:'REF-A',value:'74',clock:'2025-02-04T08:00:00Z'});
 await ev("document.getElementById('previewDraft').click()");
 await waitFor("document.getElementById('draftPreview').textContent.includes('74 pallets')");
 await ev("document.getElementById('caseEditor').scrollIntoView({block:'start'})");
 const formShot=await rpc("Page.captureScreenshot",{format:'png',captureBeyondViewport:false});
 await writeFile(join(evidenceDir,'case-workbench-form-edge.png'),Buffer.from(formShot.data,'base64'));
 await ev("document.getElementById('draftReviewed').click();document.getElementById('adoptDraft').click()");
 await waitFor("document.getElementById('claims').textContent.includes('74 pallets') && document.getElementById('caseStatus').textContent.includes('Authored in the source form')");
 console.log("WORKBENCH_EDGE_FORM_REVIEW_AND_STALE_PREVIEW_PASS");
 await ev("document.getElementById('addEvidence').click()");
 await enterRow({id:'REF-B',value:'92',clock:'2025-02-04T08:30:00Z'});
 await ev("document.getElementById('previewDraft').click()");
 await waitFor("document.getElementById('draftPreview').textContent.includes('92 pallets')");
 await ev("document.getElementById('draftReviewed').click();document.getElementById('adoptDraft').click()");
 await waitFor("document.getElementById('claims').textContent.includes('92 pallets') && document.getElementById('updateChanges').textContent.includes('74 pallets')");
 if(!await ev("document.getElementById('updateSummary').textContent.includes('2025-02-04T09:00:00.500000Z') && document.getElementById('updateSummary').textContent.includes('Operator')"))
  throw Error("WORKBENCH_COMPARISON_CHANGED_CLOCK_OR_CLAIMED_AUTONOMY");
 console.log("WORKBENCH_EDGE_ADDED_EVIDENCE_74_TO_92_PASS");
 await ev("document.getElementById('addEvidence').click()");
 await enterRow({id:'REF-FUTURE',value:'99',clock:'2025-02-04T10:00:00Z'});
 await ev("document.getElementById('previewDraft').click()");
 await waitFor("document.getElementById('draftPreview').textContent.includes('Excluded')");
 await ev("document.getElementById('draftReviewed').click();document.getElementById('adoptDraft').click()");
 await waitFor("document.getElementById('updateSummary').textContent.includes('0 admitted') && document.getElementById('claims').textContent.includes('92 pallets')");
 console.log("WORKBENCH_EDGE_FUTURE_ADDITION_PRESERVES_CLAIM_PASS");
 await ev("document.getElementById('addEvidence').click()");
 await enterRow({id:'REF-LATE-PREVIEW',value:'94',clock:'2025-02-04T08:45:00Z'});
 await ev(`(()=>{
  window.workbenchFetch=window.fetch;window.releaseWorkbenchPreview=null;window.workbenchResponseReturned=false;
  window.fetch=(url,options)=>url==='/case-evidence'?new Promise(resolve=>{
   window.releaseWorkbenchPreview=async()=>{const response=await window.workbenchFetch(url,options);
    resolve(response);window.workbenchResponseReturned=true;};
  }):window.workbenchFetch(url,options);
  document.getElementById('previewDraft').click();
 })()`);
 await waitFor("typeof window.releaseWorkbenchPreview==='function'");
 await ev(`(()=>{
  const input=document.querySelector('#sourceRows [data-field="value"]');input.value='95';
  input.dispatchEvent(new Event('input',{bubbles:true}));
  window.releaseWorkbenchPreview();window.fetch=window.workbenchFetch;
 })()`);
 await waitFor("window.workbenchResponseReturned");
 await sleep(100);
 if(!await ev("document.getElementById('draftPreview').textContent==='' && document.getElementById('draftReviewed').disabled && document.getElementById('adoptDraft').disabled"))
  throw Error("WORKBENCH_LATE_PREVIEW_OVERWROTE_NEWER_EDIT");
 await ev("document.getElementById('cancelDraft').click()");
 console.log("WORKBENCH_EDGE_DELAYED_PREVIEW_CANNOT_AUTHORIZE_EDITED_DATA_PASS");
 await ev("document.getElementById('addEvidence').click()");
 await enterRow({id:'REF-NAIVE',value:'100',clock:'2025-02-04T08:59:00'});
 await ev("document.getElementById('previewDraft').click()");
 await waitFor("document.getElementById('draftErrors').textContent.includes('timezone') && document.getElementById('adoptDraft').disabled");
 if(!await ev(`(()=>{const input=document.querySelector('#sourceRows [data-field="issued_at"]');return document.activeElement===input&&input.getAttribute('aria-invalid')==='true'&&!!document.getElementById(input.getAttribute('aria-describedby'));})()`))
  throw Error('INVALID_CLOCK_ACCESSIBLE_ERROR_FOCUS_FAILED');
 await ev(`(()=>{
  const row=document.querySelector('#sourceRows .source-row');
  for(const [key,val] of Object.entries({clock_type:'local_day',local_day:'2025-02-04',utc_offset_minutes:'420'})){
   const input=row.querySelector('[data-field="'+key+'"]');input.value=val;
   input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  document.getElementById('previewDraft').click();
 })()`);
 await waitFor("document.getElementById('draftPreview').textContent.includes('2025-02-04T17:00:00Z') && document.getElementById('draftPreview').textContent.includes('Excluded')");
 await ev("document.getElementById('cancelDraft').click()");
 // Preserve both kinds of draft when the operator switches editors.
 await ev(`document.getElementById('createCase').click();document.getElementById('draftTitle').value='Separate draft';document.getElementById('draftTitle').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('cancelDraft').click();document.getElementById('addEvidence').focus();document.getElementById('addEvidence').click()`);
 if(!await ev(`(()=>{const source=document.querySelector('#sourceRows [data-field="value"]');return source.value==='100'&&document.querySelector('#sourceRows [data-field="issued_at"]').value==='2025-02-04T08:59:00'&&document.activeElement===document.querySelector('#sourceRows [data-field="source_id"]')&&document.getElementById('adoptDraft').disabled;})()`))
  throw Error('APPEND_FOCUS_OR_CROSS_EDITOR_DRAFT_RESTORE_FAILED');
 await ev(`document.getElementById('cancelDraft').click();document.getElementById('createCase').click()`);
 if(!await ev(`document.getElementById('draftTitle').value==='Separate draft'`))throw Error('CREATE_DRAFT_LOST_AFTER_APPEND');
 await ev(`document.getElementById('cancelDraft').click()`);
 console.log('UI_EDGE_APPEND_VISIBLE_FOCUS_AND_TWO_DRAFT_RECOVERY_PASS');
 const workbenchShot=await rpc("Page.captureScreenshot",{format:'png',captureBeyondViewport:false});
 await writeFile(join(evidenceDir,'case-workbench-edge.png'),Buffer.from(workbenchShot.data,'base64'));
 console.log("WORKBENCH_EDGE_NAIVE_CLOCK_REFUSED_AND_DATE_ONLY_CUTOFF_PASS");
 await ev("document.getElementById('resetCase').click()");
 await waitFor("document.getElementById('claims').textContent.includes('155 mph') && document.getElementById('resetCase').hidden");
 // Exercise the browser's local-Nightshift consent flow with an injected
 // contract response. This is UI plumbing only; no model or sponsor request.
 await ev(`(()=>{
  window.appFetch=window.fetch;window.nightshiftUiCalls=0;
  window.fetch=async(url,options)=>{
   if(url==='/health')return new Response(JSON.stringify({local_nightshift_enabled:true}),{status:200,headers:{'Content-Type':'application/json'}});
   if(url==='/case-local-nightshift'){
    window.nightshiftUiCalls++;
    const input=JSON.parse(options.body),replayInput={...input};delete replayInput.confirm_local_nightshift;
    const response=await window.appFetch('/case-investigation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(replayInput)});
    const report=await response.json(),change=report.experiment.changed_claims[0];
    report.nightshift_local_proposal={status:'PROPOSAL_REJECTED_BY_DETERMINISTIC_CHECK',model_called:true,
     request_attempted:true,requested_mode:'meterless/local',routed_model:'local-runtime/test-fixture',
     route_identity_independently_verified:false,rejection_code:'EXPLANATION_META_OR_PLACEHOLDER_TEXT'};
    report.model_called=true;report.nightshift_request_attempted=true;report.model_or_sponsor_called=true;
    report.execution_trace.push({action:'CHECK_LOCAL_NIGHTSHIFT_PROPOSAL',status:'PROPOSAL_REJECTED_BY_DETERMINISTIC_CHECK',
     model_called:true,request_attempted:true,deterministic_verdict_unchanged:true});
    return new Response(JSON.stringify(report),{status:200,headers:{'Content-Type':'application/json'}});
   }
   return window.appFetch(url,options);
  };
 })()`);
 await ev("checkLocalNightshiftAvailability()");
 await ev("document.getElementById('warehouseExample').click()");
 await waitFor("!document.getElementById('nightshiftPanel').hidden && document.getElementById('claims').textContent.includes('25 pallets')");
 await ev(`(()=>{for(const id of ['STOCK-CHECK','STOCK-LEDGER']){
  const input=[...document.querySelectorAll('#jointSources input')].find(x=>x.value===id);
  input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));}
  document.getElementById('testJoint').click();})()`);
 await waitFor("document.getElementById('jointEffect').textContent.includes('12 pallets')");
 if(!await ev("document.getElementById('askLocalNightshift').disabled && window.nightshiftUiCalls===0"))
  throw Error('NIGHTSHIFT_REQUESTED_BEFORE_USER_CONSENT');
 await ev("document.getElementById('confirmLocalNightshift').click()");
 if(!await ev("!document.getElementById('askLocalNightshift').disabled"))
  throw Error('NIGHTSHIFT_BUTTON_NOT_ENABLED_AFTER_OPT_IN');
 await ev("document.getElementById('askLocalNightshift').click()");
 await waitFor("document.getElementById('nightshiftResult').textContent.includes('PROPOSAL_REJECTED_BY_DETERMINISTIC_CHECK')");
 const modelCard=await ev(`({text:document.getElementById('nightshiftResult').textContent,
  calls:window.nightshiftUiCalls,after:document.getElementById('claims').textContent})`);
 if(modelCard.calls!==1||!modelCard.text.includes('25 pallets (STOCK-LEDGER) to 12 pallets (STOCK-OLD)')||
    !modelCard.text.includes('text-quality check')||
    !modelCard.text.includes('not independently attested')||!modelCard.after.includes('25 pallets'))
  throw Error('NIGHTSHIFT_UI_CHANGED_VERDICT_OR_LOST_DISCLOSURE');
 console.log('NIGHTSHIFT_UI_REJECTED_PROSE_DETERMINISTIC_FALLBACK_PASS_NOT_VENDOR_PROOF');
 await ev("window.fetch=window.appFetch;document.getElementById('resetCase').click()");
 await waitFor("document.getElementById('claims').textContent.includes('155 mph') && document.getElementById('resetCase').hidden");
 // Return to a positive claim, then force a LOCAL transport error. This is
 // browser failure injection only, never a sponsor/model success simulation.
 await ev(`(()=>{
  document.getElementById("mode").value="reported";
  document.getElementById("controls").requestSubmit();
 })()`);
 let restored=false;
 for(let i=0;i<90;i++){
  restored=await ev("document.getElementById('claims').textContent.includes('155 mph')");
  if(restored)break;await sleep(140);
 }
 if(!restored)throw Error("WHY_REPORTED_RECOVERY_MISSING");
 await ev(`(()=>{
  window.fetch=()=>Promise.reject(new Error("INJECTED_LOCAL_NETWORK_FAILURE"));
  document.getElementById("asof").value="2024-10-07T03:59:00Z";
  document.getElementById("controls").requestSubmit();
 })()`);
 let cleared=false;
 for(let i=0;i<90;i++){
  cleared=await ev(`document.getElementById('status').textContent==='Replay unavailable'
   && !document.getElementById('claims').textContent.includes('155 mph')
   && document.getElementById('removed').disabled
   && document.getElementById('removal').textContent===''
   && document.getElementById('stamp').textContent===''
   && document.getElementById('timeline').textContent===''`);
  if(cleared)break;await sleep(140);
 }
 if(!cleared)throw Error("WHY_STALE_RESULT_AFTER_NETWORK_FAILURE");
 console.log("WHY_EDGE_FAILED_REPLAY_CLEARS_STALE_RESULT_PASS");
 console.log("WHY_REAL_EDGE_ALL_PASS_NO_SPONSOR_NO_HUMANS");
}catch(e){
 console.error("WHY_EDGE_FAIL",e.message);
 process.exitCode=2;
}finally{
 try{ws?.close()}catch{}
 try{edge?.kill()}catch{}
 try{server.kill()}catch{}
}
