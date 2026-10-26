/**
 * Real isolated Edge browser smoke of new sample-only Counterfactual Lab.
 * Built-ins only: node 24, CDP WebSocket; no live sponsor calls, credentials,
 * browser profile access or external app assets.
 * node verify_counterfactual_browser.mjs
 */
import {spawn} from "node:child_process";
import {existsSync} from "node:fs";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
const ROOT=dirname(fileURLToPath(import.meta.url));
const LOG=join(ROOT,"acceptance","logs","counterfactual-ui");
const EDGE="C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
let origin=null,DEMO=null;
const sleep=ms=>new Promise(ok=>setTimeout(ok,ms));
if(!existsSync(EDGE))throw Error("EDGE_EXECUTABLE_MISSING");
await mkdir(LOG,{recursive:true});
const profile=join(LOG,"isolated-edge-"+Date.now());
let server=null,edge=null,ws=null,next=0;
const waiting=new Map();
function rpc(method,params={}){
 return new Promise((resolve,reject)=>{
  const id=++next;
  const timer=setTimeout(()=>{waiting.delete(id);reject(Error("CDP_TIMEOUT_"+method));},16000);
  waiting.set(id,{resolve,reject,timer,method});
  ws.send(JSON.stringify({id,method,params}));
 });
}
async function runjs(expression,awaitPromise=false){
 const ret=await rpc("Runtime.evaluate",{expression,returnByValue:true,awaitPromise});
 if(ret.exceptionDetails)throw Error("JS_ERROR_"+ret.exceptionDetails.text);
 return ret.result?.value;
}
async function waitHealth(){
 for(let i=0;i<80;i++){
  if(server.exitCode!==null)throw Error("SAMPLE_SERVER_EXITED");
  if(!origin){await sleep(130);continue;}
  try{
   const r=await fetch(origin+"/health",{signal:AbortSignal.timeout(950)});
   const data=await r.json();
   if(r.ok&&data.sample_mode_only===true)return;
  }catch{}
  await sleep(130);
 }
 throw Error("SAMPLE_SERVER_NO_HEALTH");
}
async function waitPort(){
 for(let i=0;i<100;i++){
  if(edge.exitCode!==null)throw Error("EDGE_EXITED");
  try{
   const data=(await readFile(join(profile,"DevToolsActivePort"),"utf8")).split(/\r?\n/)[0];
   if(Number(data)>0)return Number(data);
  }catch{}
  await sleep(140);
 }
 throw Error("CDP_PORT_MISSING");
}
async function connect(port){
 let page=null;
 for(let i=0;i<80;i++){
  const tabs=await fetch("http://127.0.0.1:"+port+"/json/list")
    .then(r=>r.json()).catch(()=>[]);
  page=tabs.find(x=>x.type==="page"&&x.url.startsWith(DEMO));
  if(page)break;
  await sleep(130);
 }
 if(!page)throw Error("DEMO_PAGE_NOT_LOADED");
 ws=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(Error("CDP_WEBSOCKET_FAILED")),8000);
  ws.addEventListener("open",()=>{clearTimeout(timer);resolve();},{once:true});
  ws.addEventListener("error",()=>{clearTimeout(timer);reject(Error("CDP_CONNECT_ERROR"));},{once:true});
 });
 ws.addEventListener("message",ev=>{
  let m;try{m=JSON.parse(String(ev.data));}catch{return;}
  const pending=waiting.get(m.id);if(!pending)return;
  waiting.delete(m.id);clearTimeout(pending.timer);
  if(m.error)pending.reject(Error("CDP_"+pending.method+"_"+m.error.message));
  else pending.resolve(m.result);
 });
 await rpc("Page.enable");
 await rpc("Runtime.enable");
 await rpc("Emulation.setDeviceMetricsOverride",{
  width:1440,height:900,deviceScaleFactor:1,mobile:false
 });
}
async function waitDemoDomReady(){
  // CDP tab discovery precedes DOMContentLoaded on some cold Edge boots.
  // Wait for actual controls rather than clicking immediately and racing.
  for(let i=0;i<80;i++){
   try{
    const ready=await runjs(
      "document.readyState==='complete' && !!document.getElementById('mode') && "+
      "!!document.getElementById('when') && !!document.getElementById('counter')"
    );
    if(ready)return;
   }catch{}
   await sleep(150);
  }
  throw Error("DEMO_DOM_NOT_READY");
}
async function clickCounter(mode,clock){
 const js="(function(){document.getElementById('mode').value="+JSON.stringify(mode)+
   ";document.getElementById('when').value="+JSON.stringify(clock)+
   ";document.getElementById('counter').click()})()";
 await runjs(js);
 const status=await runjs("new Promise((resolve,reject)=>{let n=0;const timer=setInterval(()=>{n++;const s=document.getElementById('counterStatus').textContent;if(s.startsWith('PASS')||s.startsWith('CAUTION')){clearInterval(timer);resolve(s);}else if(s.startsWith('Counterfactual analysis failed')||n>100){clearInterval(timer);reject(Error(s));}},100);})",true);
 if(!status.startsWith("PASS"))throw Error("PIPELINE_COUNTERFACTUAL_VERDICTS_DISAGREE");
 const fields="({verdict:document.getElementById('verdict').dataset.code,witness:document.getElementById('cfWitness').textContent,policy:document.getElementById('cfPolicyInfo').textContent,ablations:document.getElementById('cfAblations').textContent,requirements:document.getElementById('cfRequirements').textContent})";
 const v=await runjs(fields);
 if(!v)throw Error("EMPTY_BROWSER_RESULT");
 return v;
}
async function capture(name, section="counter-heading"){
 await runjs("document.getElementById("+JSON.stringify(section)+").scrollIntoView({block:'start'})");
 await sleep(250);
 const x=await rpc("Page.captureScreenshot",{format:"png",captureBeyondViewport:false,fromSurface:true});
 const bytes=Buffer.from(x.data,"base64");
 if(bytes.length<12000)throw Error("SCREENSHOT_BLANK");
 await writeFile(join(LOG,name),bytes);
 console.log("SCREENSHOT",name,"BYTES",bytes.length);
}
try{
 // Bind an ephemeral port in the CHILD server. A fixed-port health check
 // could accidentally accept another checkout's already-running server.
 server=spawn("py",["-3","-u","-c",[
  "from evidencetrail.api import create_local_server",
  "s=create_local_server('127.0.0.1',0)",
  "print('ISOLATED_SAMPLE_SERVER_PORT='+str(s.server_port),flush=True)",
  "s.serve_forever()"
 ].join(";")],{
  cwd:ROOT,windowsHide:true,stdio:["ignore","pipe","ignore"]
 });
 let serverOutput="";
 server.stdout.setEncoding("utf8");
 server.stdout.on("data",data=>{
  serverOutput+=data;
  const match=serverOutput.match(/ISOLATED_SAMPLE_SERVER_PORT=(\d+)/);
  if(match){origin="http://127.0.0.1:"+match[1];DEMO=origin+"/demo";}
 });
 await waitHealth();
 console.log("ISOLATED_SAMPLE_SERVER_PORT="+new URL(origin).port);
 edge=spawn(EDGE,[
  "--headless=new","--no-first-run","--disable-extensions","--disable-sync",
  "--disable-background-networking","--hide-scrollbars","--remote-debugging-port=0",
  "--user-data-dir="+profile,"--window-size=1440,900",DEMO
 ],{windowsHide:true,stdio:"ignore"});
 await connect(await waitPort());
 await waitDemoDomReady();
 const late=await clickCounter("REPORTED_DATELINE_REPLAY","2024-09-08T16:45");
 if(late.verdict!=="WARN" ||
  !late.witness.includes("Exact minimum set: 2")||
  !late.ablations.includes("GOV-2024-09-08-1637")||
  !late.ablations.includes("SYN-CAP-YAGI-ALPHA-LUCYEN")||
  !late.ablations.includes("PIVOTAL")||
  !late.policy.includes("INSUFFICIENT EVIDENCE")||
  !late.requirements.includes("MISSING REAL SITE POPULATION")){
  throw Error("REPORTED_1645_WITNESS_MISMATCH");
 }
 console.log("REPORTED_1645_BROWSER_PASS_WARN_MIN2_PIVOTAL2");
 await capture("counterfactual-1645-reported.png");
 const strict=await clickCounter("STRICT_AS_OF_2024","2024-09-08T16:45");
 if(strict.verdict!=="INSUFFICIENT_EVIDENCE"||
  !strict.witness.includes("No sufficient WARN set")||
  !strict.requirements.includes("HISTORICAL AVAILABILITY NOT AUTHENTICATED")){
  throw Error("STRICT_1645_ABSTENTION_MISMATCH");
 }
 console.log("STRICT_1645_BROWSER_PASS_ABSTAIN");
 await capture("counterfactual-1645-strict.png");
 const early=await clickCounter("REPORTED_DATELINE_REPLAY","2024-09-08T16:30");
 if(early.verdict!=="INSUFFICIENT_EVIDENCE"||
  !early.requirements.includes("MISSING DISTRICT NAMED BULLETIN")){
  throw Error("REPORTED_1630_ABSTENTION_MISMATCH");
 }
 console.log("REPORTED_1630_BROWSER_PASS_ABSTAIN");
 await capture("counterfactual-1630-reported.png");
 // Fourth REAL headless Edge interaction: button -> local HTTP /integrity
 // -> seven dynamically evaluated data-laundering and clean-control checks.
 await runjs("document.getElementById('integrityLab').click()");
 const integrity=await runjs("new Promise((resolve,reject)=>{let n=0;const timer=setInterval(()=>{n++;const s=document.getElementById('integrityStatus').textContent;if(s.startsWith('PASS')||s.startsWith('CAUTION')){clearInterval(timer);resolve(s);}else if(s.startsWith('Challenge failed')||n>100){clearInterval(timer);reject(Error(s));}},100);})",true);
 if(!integrity.startsWith("PASS"))throw Error("INTEGRITY_CHALLENGE_NOT_PASS");
 const integrityFields=await runjs("({score:document.getElementById('integrityScore').textContent,unguarded:document.getElementById('unguardedAttack').textContent,protected:document.getElementById('protectedAttack').textContent,cases:document.getElementById('integrityCases').textContent})");
 if(!integrityFields.score.includes("7/7")||
    !integrityFields.unguarded.includes("WARN")||
    !integrityFields.protected.includes("SOURCE_LOCATOR_ALIAS_REFUSED")||
    !integrityFields.cases.includes("AMBIGUOUS_SCENARIO_CAPACITY_REFUSED")||
    !integrityFields.cases.includes("SOURCE_EXCERPT_ALIAS_REFUSED")){
  throw Error("INTEGRITY_CHALLENGE_BROWSER_MISMATCH");
 }
 console.log("SOURCE_INDEPENDENCE_BROWSER_PASS_7_OF_7");
 await capture("source-independence-challenge.png","integrity-heading");
 // Fifth real isolated Edge interaction: entirely different external NHC case.
 // Here 15:00 UTC NOAA bulletin MUST NOT leak into an 11:00 UTC as-of.
 await runjs("document.getElementById('miltonClock').value='2024-10-07T11:00:00Z';document.getElementById('miltonPolicy').value='reported';document.getElementById('miltonRun').click()");
 const miltonEarly=await runjs("new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{n++;const s=document.getElementById('miltonStatus').textContent;if(s.includes('SELECTED ISSUED BULLETIN FOUND')){clearInterval(t);resolve(s);}else if(s.includes('replay failed')||n>100){clearInterval(t);reject(Error(s));}},100)})",true);
 const earlyFields=await runjs("({latest:document.getElementById('miltonLatest').textContent,unsafe:document.getElementById('miltonUnsafe').textContent,count:document.getElementById('miltonCount').textContent,source:document.getElementById('miltonAdmitted').textContent,excluded:document.getElementById('miltonExcluded').textContent})");
 if(!earlyFields.latest.includes("100 mph") ||
    !earlyFields.unsafe.includes("155 mph") ||
    !earlyFields.count.includes("1 of 4") ||
    !earlyFields.source.includes("NHC-AL142024-PUBLIC-008") ||
    !earlyFields.excluded.includes("NHC-AL142024-PUBLIC-010")){
  throw Error("NOAA_MILTON_EARLY_ISSUE_CLOCK_LEAK");
 }
 console.log("NOAA_EXTERNAL_MILTON_BROWSER_PASS_ASOF_100_NOT_FUTURE_155");
 await capture("noaa-milton-external-replay.png","milton-heading");
 await runjs("document.getElementById('miltonPolicy').value='strict';document.getElementById('miltonRun').click()");
 await runjs("new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{n++;const s=document.getElementById('miltonStatus').textContent;if(s.includes('NO ADMISSIBLE ARCHIVED ISSUE')){clearInterval(t);resolve(s);}else if(s.includes('replay failed')||n>100){clearInterval(t);reject(Error(s));}},100)})",true);
 const strictFields=await runjs("({latest:document.getElementById('miltonLatest').textContent,count:document.getElementById('miltonCount').textContent})");
 if(strictFields.latest!=="None admissible"||!strictFields.count.includes("0 of 4")){
  throw Error("NOAA_MILTON_STRICT_ORIGINAL_BYTES_WERE_FALSIFIED");
 }
 console.log("NOAA_EXTERNAL_MILTON_BROWSER_PASS_STRICT_ABSTAIN");
 // Sixth real Edge scenario: independent issuer families and date-only bounds.
 await runjs("document.getElementById('crossClock').value='2024-10-07T11:00:00Z';document.getElementById('crossPolicy').value='reported';document.getElementById('crossRun').click()");
 await runjs("new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{n++;const s=document.getElementById('crossStatus').textContent;if(s.includes('REPORTED DATELINE REPLAY')){clearInterval(t);resolve(s);}else if(s.includes('audit failed')||n>100){clearInterval(t);reject(Error(s));}},100)})",true);
 const cross=await runjs("({wind:document.getElementById('crossWind').textContent,counties:document.getElementById('crossCounties').textContent,issuers:document.getElementById('crossIssuers').textContent,withheld:document.getElementById('crossWithheld').textContent,baseline:document.getElementById('crossBaseline').textContent})");
 if(cross.wind!=="100 mph"||cross.counties!=="51 counties"||cross.issuers!=="2 / 2"||
    !cross.withheld.includes("FL-GOV-20241007-1100-ET")||
    !cross.baseline.includes("Deliberately invalid time-blind baseline"))
   throw Error("CROSS_ISSUER_FIRST_EXAMINATION_FAILED");
 console.log("CROSS_ISSUER_BROWSER_PASS_100_51_TWO_FAMILIES");
 await capture("cross-issuer-milton-2024.png","cross-heading");
 await runjs("document.getElementById('crossClock').value='2024-10-07T03:59:00Z';document.getElementById('crossRun').click()");
 await runjs("new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{n++;const s=document.getElementById('crossStatus').textContent;if(s.includes('REPORTED DATELINE REPLAY')){clearInterval(t);resolve(s);}else if(s.includes('audit failed')||n>100){clearInterval(t);reject(Error(s));}},100)})",true);
 const earlyState=await runjs("({wind:document.getElementById('crossWind').textContent,counties:document.getElementById('crossCounties').textContent,issuers:document.getElementById('crossIssuers').textContent})");
 if(earlyState.wind!=="No eligible report"||earlyState.counties!=="35 counties"||
    earlyState.issuers!=="1 / 2")throw Error("CROSS_ISSUER_DATE_ONLY_LEAK");
 console.log("CROSS_ISSUER_BROWSER_PASS_DATE_ONLY_NO_BACKDATE");
 await runjs("document.getElementById('crossPolicy').value='strict';document.getElementById('crossRun').click()");
 await runjs("new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{n++;const s=document.getElementById('crossStatus').textContent;if(s.includes('STRICT AS OF 2024')){clearInterval(t);resolve(s);}else if(s.includes('audit failed')||n>100){clearInterval(t);reject(Error(s));}},100)})",true);
 const strictIssuer=await runjs("({wind:document.getElementById('crossWind').textContent,counties:document.getElementById('crossCounties').textContent,issuers:document.getElementById('crossIssuers').textContent})");
 if(strictIssuer.wind!=="No eligible report"||
    strictIssuer.counties!=="No eligible order"||
    strictIssuer.issuers!=="0 / 2")throw Error("CROSS_ISSUER_STRICT_ORIGINAL_TIME_FAKE");
 console.log("CROSS_ISSUER_BROWSER_PASS_STRICT_ABSTAIN");
 await writeFile(join(LOG,"counterfactual-browser-smoke.json"),JSON.stringify({
  status:"REAL_EDGE_BROWSER_6_SCENARIOS_PASS",sample_only:true,
  no_real_nightshift_or_zetaris_call:true,
  scenarios:["16:45 reported WARN simulated minimum2 pivotal2",
   "16:45 strict INSUFFICIENT_EVIDENCE",
   "16:30 reported INSUFFICIENT_EVIDENCE",
   "Source independence challenge 7/7 (real UI)",
   "NOAA NHC external 11:00 as-of 100 vs future 155 and strict abstain",
   "Cross-issuer original families/date precision and strict abstain"]
 },null,2)+"\n");
 console.log("EDGE_COUNTERFACTUAL_ALL_PASS");
}catch(exc){
 console.error("EDGE_COUNTERFACTUAL_SMOKE_FAILED",exc.message);
 process.exitCode=1;
}finally{
 for(const x of waiting.values())clearTimeout(x.timer);
 if(ws&&ws.readyState===WebSocket.OPEN)ws.close();
 if(edge)edge.kill();
 if(server)server.kill();
}
