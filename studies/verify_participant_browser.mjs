/** Real isolated Microsoft Edge smoke of offline opt-in analyst packet.
 * Answers are deliberately AUTOMATED FIXTURES and are deleted after testing.
 * NEVER count as independent human Impact responses.
 */
import {spawn} from "node:child_process";
import {mkdir,readFile,readdir,unlink,writeFile} from "node:fs/promises";
import {existsSync} from "node:fs";
import {join,resolve} from "node:path";
import {pathToFileURL} from "node:url";

const ROOT=resolve(import.meta.dirname,"..");
const EDGE="C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const art=join(ROOT,"acceptance","logs");
const profiles=join(art,"blind-study-edge-smoke");
const downloads=join(profiles,"download");
const CASES=["blind-study-pilot-slot0.html","blind-study-pilot-slot6.html"];
if(!existsSync(EDGE))throw Error("REAL_MICROSOFT_EDGE_BINARY_MISSING");
await mkdir(downloads,{recursive:true});
async function runOne(filename,i){
 const f=join(art,filename);
 if(!existsSync(f))throw Error("GENERATE_PACKET_FIRST_"+filename);
 const profile=join(profiles,"isolated-"+i+"-"+Date.now());
 await mkdir(profile,{recursive:true});
 const edge=spawn(EDGE,["--headless=new","--no-first-run","--disable-extensions",
  "--disable-sync","--remote-debugging-port=0","--user-data-dir="+profile,
  "--window-size=1280,940",pathToFileURL(f).href],
  {windowsHide:true,stdio:"ignore"});
 let ws;const pending=new Map();let n=0;
 try{
  let port=0;
  for(let step=0;step<100;step++){
   try{const raw=await readFile(join(profile,"DevToolsActivePort"),"utf8");
       port=Number(raw.split(/\r?\n/)[0]);if(port)break;}catch{}
   await sleep(150);
  }
  if(!port)throw Error("EDGE_DEBUGGING_FAILED");
  let tab;
  for(let step=0;step<100;step++){
   const list=await fetch("http://127.0.0.1:"+port+"/json/list").then(r=>r.json()).catch(()=>[]);
   tab=list.find(x=>x.type==="page"&&x.url.startsWith("file:"));
   if(tab)break;
   await sleep(150);
  }
  if(!tab)throw Error("OFFLINE_FILE_TAB_NOT_OPEN");
  ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((yes,no)=>{ws.addEventListener("open",yes,{once:true});ws.addEventListener("error",no,{once:true})});
  ws.addEventListener("message",ev=>{
   let event;try{event=JSON.parse(String(ev.data))}catch{return}
   const pend=pending.get(event.id);if(!pend)return;
   clearTimeout(pend.timer);pending.delete(event.id);
   event.error?pend.reject(Error("CDP_"+event.error.message)):pend.resolve(event.result);
  });
  const cdp=(method,params={})=>new Promise((resolve,reject)=>{
   const id=++n,timer=setTimeout(()=>{pending.delete(id);reject(Error("CDP_TIMEOUT_"+method))},16000);
   pending.set(id,{resolve,reject,timer});
   ws.send(JSON.stringify({id,method,params}));
  });
  const evalJS=async code=>{
   const r=await cdp("Runtime.evaluate",{expression:code,awaitPromise:true,returnByValue:true});
   if(r.exceptionDetails)throw Error("PAGE_JAVASCRIPT_"+r.exceptionDetails.text);
   return r.result.value;
  };
  await cdp("Page.enable");await cdp("Runtime.enable");
  await cdp("Browser.setDownloadBehavior",{behavior:"allow",downloadPath:downloads});
  for(let count=0;count<80;count++){
   if(await evalJS("document.readyState==='complete' && typeof PACKET==='object'"))break;
   await sleep(150);
  }
  const before=await evalJS(`({
    protocol:location.protocol,
    defaultLocked:document.getElementById('begin').disabled,
    goldLeak:document.documentElement.innerText.includes('latest_nhc_selected_wind_mph'),
    tasks:PACKET.tasks.map(x=>({arm:x.arm,hasOverlay:!!x.admission_overlay,cards:x.cards.length}))
  })`);
  if(before.protocol!=="file:"||!before.defaultLocked||before.goldLeak
      ||before.tasks.length!==2||before.tasks.some(t=>t.cards!==7))throw Error("OFFLINE_PACKET_CONTRACT_FAILED");
  const initiated=await evalJS(`(()=>{
    const cb=document.getElementById("consent");cb.checked=true;
    cb.dispatchEvent(new Event("change",{bubbles:true}));
    document.getElementById("begin").click();
    return document.getElementById("taskStatus").textContent
  })()`);
  if(initiated!=="Question 1 of 2")throw Error("CONSENT_START_FAILED");
  for(let j=0;j<2;j++){
   const state=await evalJS(`({
    step:document.getElementById("taskStatus").textContent,
    visibleCards:document.getElementById("cards").children.length,
    overlay:!document.getElementById("overlayHelp").classList.contains("hide"),
    expected:!!PACKET.tasks[taskIndex].admission_overlay
   })`);
   if(state.step!=="Question "+(j+1)+" of 2"||state.visibleCards!==7||state.overlay!==state.expected)
    throw Error("TASK_CARD_OR_CONDITION_MISMATCH");
   await sleep(1250);
   await evalJS(`(()=>{
    document.getElementById("wind").value="100";
    document.getElementById("counties").value="51";
    document.querySelector('input[name="cite"]').checked=true;
    document.getElementById("answers").requestSubmit();
    return true;
   })()`);
  }
  if(!(await evalJS(`!document.getElementById("finish").classList.contains("hide") && answers.length===2`)))
   throw Error("PARTICIPANT_TWO_TASK_FLOW_FAILED");
  const screenshot=await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
  await writeFile(join(art,"blind-study-edge-slot"+i+".png"),Buffer.from(screenshot.data,"base64"));
  await evalJS("document.getElementById('download').click()");
  const token=await evalJS("PACKET.session_token");
  const name="evidencetrail-response-"+token+".json";
  let saved;
  for(let k=0;k<40;k++){
   const files=await readdir(downloads);
   if(files.includes(name)){saved=join(downloads,name);break;}
   await sleep(200);
  }
  if(!saved)throw Error("REAL_EDGE_DOWNLOAD_MISSING");
  const exported=JSON.parse(await readFile(saved,"utf8"));
  if(exported.kind!=="EVIDENCETRAIL_BLIND_ANALYST_RESULT_V1"||
     exported.answers?.length!==2||
     exported.answers.some(x=>x.elapsed_ms<1000))throw Error("EXPORTED_JSON_INVALID");
  await unlink(saved); // Avoid accidentally treating robot answers as people.
  console.log("BLIND_STUDY_REAL_EDGE_FLOW_PASS",filename,
              "CONDITION_SEQUENCE",before.tasks.map(t=>t.arm).join(","),
              "HUMAN_PARTICIPANTS",0);
 }finally{
  try{ws?.close()}catch{}
  try{edge.kill()}catch{}
 }
}
for(let i=0;i<CASES.length;i++)await runOne(CASES[i],i);
console.log("BLIND_STUDY_REAL_EDGE_ALL_PASS_NO_HUMAN_OUTCOMES");
