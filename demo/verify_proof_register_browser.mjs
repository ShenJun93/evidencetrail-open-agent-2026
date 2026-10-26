/** Real isolated Edge journey test: demo -> Why -> proof register.
 * Runs one SAMPLE_ONLY ephemeral local API. No vendor keys or sponsor calls.
 */
import {spawn} from "node:child_process";
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {resolve,join} from "node:path";

const ROOT=resolve(import.meta.dirname,"..");
const EDGE="C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const tmp=join(ROOT,"acceptance","logs","proof-register-edge-"+Date.now());
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const env={};
for(const k of ["PATH","PATHEXT","SYSTEMROOT","WINDIR","TEMP","TMP",
                "USERPROFILE","APPDATA","LOCALAPPDATA","COMSPEC",
                "PROGRAMFILES","PROGRAMFILES(X86)"]){
 if(process.env[k])env[k]=process.env[k];
}
env.PYTHONDONTWRITEBYTECODE="1";
await mkdir(tmp,{recursive:true});
await mkdir(join(ROOT,'acceptance','logs','ui-redesign'),{recursive:true});
const server=spawn("py",["-3","-u","-c",[
 "from evidencetrail.api import create_local_server",
 "s=create_local_server('127.0.0.1',0)",
 "print('PROOF_PORT='+str(s.server_port),flush=True)",
 "s.serve_forever()"].join(";")],
 {cwd:ROOT,env,windowsHide:true,stdio:["ignore","pipe","pipe"]});
let out="",edge,ws;
server.stdout.setEncoding("utf8");
server.stdout.on("data",chunk=>out+=chunk);
try{
 let port=0;
 for(let k=0;k<110;k++){
  const m=out.match(/PROOF_PORT=(\d+)/);
  if(m){port=Number(m[1]);break}
  if(server.exitCode!==null)throw Error("API_EXITED");
  await sleep(100);
 }
 if(!port)throw Error("LOCAL_API_NOT_READY");
 const host="http://127.0.0.1:"+port;
 edge=spawn(EDGE,["--headless=new","--no-first-run","--disable-sync",
   "--disable-extensions","--remote-debugging-port=0",
   "--user-data-dir="+tmp,"--window-size=1360,950",
   host+"/demo?utm_source=chatgpt.com"],
   {env,windowsHide:true,stdio:"ignore"});
 let dp=0;
 for(let i=0;i<110;i++){
  try{dp=Number((await readFile(join(tmp,"DevToolsActivePort"),
               "utf8")).split(/\r?\n/)[0]);if(dp)break}catch{}
  await sleep(100);
 }
 if(!dp)throw Error("EDGE_CDP_PORT_MISSING");
 let page;
 for(let i=0;i<110;i++){
  const list=await fetch("http://127.0.0.1:"+dp+"/json/list")
   .then(r=>r.json()).catch(()=>[]);
  page=list.find(x=>x.type==="page"&&x.url.startsWith(host));
  if(page)break;await sleep(100);
 }
 if(!page)throw Error("EDGE_PAGE_NOT_FOUND");
 ws=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((ok,no)=>{ws.addEventListener("open",ok,{once:true});
                             ws.addEventListener("error",no,{once:true})});
 let id=0;const pending=new Map();
 ws.addEventListener("message",event=>{
  let msg;try{msg=JSON.parse(String(event.data))}catch{return}
  const p=pending.get(msg.id);if(!p)return;
  clearTimeout(p.timeout);pending.delete(msg.id);
  msg.error?p.reject(Error(msg.error.message)):p.resolve(msg.result);
 });
 function cdp(method,params={}){
  return new Promise((resolve,reject)=>{
   const next=++id,timeout=setTimeout(()=>{
    pending.delete(next);reject(Error("CDP_TIMEOUT_"+method));
   },17000);
   pending.set(next,{resolve,reject,timeout});
   ws.send(JSON.stringify({id:next,method,params}));
  });
 }
 const ev=async expression=>{
  const r=await cdp("Runtime.evaluate",{expression,
         awaitPromise:true,returnByValue:true});
  if(r.exceptionDetails)throw Error("PAGE_SCRIPT_EXCEPTION");
  return r.result.value;
 };
 await cdp("Runtime.enable");await cdp("Page.enable");
 const ready=async suffix=>{
  for(let i=0;i<110;i++){
   const ok=await ev(`location.pathname===${JSON.stringify(suffix)}
     && document.readyState==="complete"`);
   if(ok)return true;
   await sleep(110);
  }
  return false;
 };
 if(!await ready("/demo"))throw Error("DEMO_NOT_READY");
 const nav=await ev(`({
  why:!!document.querySelector('nav[aria-label="EvidenceTrail views"] a[href="/why"]'),
  proof:!!document.querySelector('nav[aria-label="EvidenceTrail views"] a[href="/proof"]'),
  simulation:document.querySelector('.rail-foot')?.textContent
 })`);
 if(!nav.why||!nav.proof||!nav.simulation.includes("Offline sample"))
  throw Error("MAIN_NAVIGATION_OR_SAMPLE_LABEL_MISSING");
 console.log("PROOF_EDGE_DEMO_NAV_PRESENT");
 for(const width of [375,1440]){
  await cdp('Emulation.setDeviceMetricsOverride',{width,height:960,deviceScaleFactor:1,mobile:false});
  if(!await ev(`document.documentElement.scrollWidth<=innerWidth+1 && !!document.querySelector('a[aria-current="page"][href="/demo"]')`))throw Error('TIMELINE_REFLOW_FAILED_'+width);
  const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await writeFile(join(ROOT,'acceptance','logs','ui-redesign','timeline-'+width+'.png'),Buffer.from(shot.data,'base64'));
 }
 await ev(`document.querySelector('nav[aria-label="EvidenceTrail views"] a[href="/why"]').click()`);
 if(!await ready("/why"))throw Error("WHY_NAVIGATION_NOT_READY");
 let loaded=false;
 for(let i=0;i<110;i++){
  loaded=await ev(`document.getElementById("status")?.textContent===
      "Verified local source-pinned replay"`);
  if(loaded)break;
  await sleep(120);
 }
 if(!loaded)throw Error("WHY_REPLAY_NOT_COMPUTED");
 const value=await ev(`document.getElementById("claims")?.textContent`);
 if(!value.includes("100 mph")||!value.includes("51 counties"))
  throw Error("WHY_PIVOTAL_CLAIMS_NOT_RENDERED");
 console.log("PROOF_EDGE_WHY_100_MPH_51_COUNTIES_PASS");
 await ev(`location.href="/proof?utm_source=chatgpt.com"`);
 if(!await ready("/proof"))throw Error("TRACKED_PROOF_ROUTE_FAILED");
 const proof=await ev(`({
  title:document.title,
  model:document.body.textContent.includes("nvidia/nemotron-3.5-lightning-30b-a3b"),
  realCall:document.body.textContent.includes("One actual accepted HTTPS chat completion"),
  humanZero:document.body.textContent.includes("Independent analyst n = 0"),
  scope:document.body.textContent.includes("No sponsor prize eligibility has been certified"),
  links:[...document.querySelectorAll("nav a")].map(a=>a.getAttribute("href"))
 })`);
 if(!proof.model||!proof.realCall||!proof.humanZero||!proof.scope
    ||!proof.links.includes("/why"))
  throw Error("PROOF_REGISTER_HONESTY_OR_NAV_FAILED");
 for(const width of [375,1440]){
  await cdp('Emulation.setDeviceMetricsOverride',{width,height:960,deviceScaleFactor:1,mobile:false});
  if(!await ev(`document.documentElement.scrollWidth<=innerWidth+1 && !!document.querySelector('a[aria-current="page"][href="/proof"]')`))throw Error('PROOF_REFLOW_FAILED_'+width);
  const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await writeFile(join(ROOT,'acceptance','logs','ui-redesign','proof-'+width+'.png'),Buffer.from(shot.data,'base64'));
 }
 const image=await cdp("Page.captureScreenshot",{format:"png",
                                      captureBeyondViewport:false});
 const screenshot=join(ROOT,"acceptance","logs","proof-register-edge.png");
 await writeFile(screenshot,Buffer.from(image.data,"base64"));
 console.log("PROOF_EDGE_EVIDENCE_REGISTER_PASS_SCREENSHOT",screenshot);
 console.log("PROOF_EDGE_ALL_PASS_NO_VENDOR_OR_HUMAN");
}catch(error){
 console.error("PROOF_EDGE_FAIL",error.message);
 process.exitCode=2;
}finally{
 try{ws?.close()}catch{}
 try{edge?.kill()}catch{}
 try{server.kill()}catch{}
}
