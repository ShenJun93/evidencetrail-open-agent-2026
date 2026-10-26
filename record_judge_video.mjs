/**
 * Record the running EvidenceTrail demo in isolated headless Edge through CDP.
 * Node 24 native WebSocket. Browser session holds NO personal profile, API keys,
 * extensions or Windows desktop frames. Only local /demo and /run are accessed.
 * node record_judge_video.mjs --shots
 * node record_judge_video.mjs --record
 * Output ignored under acceptance/logs/judge-video-20261023/.
 * Captioned silent DRAFT; no public submission or sponsor acceptance implied.
 */
import {spawn} from "node:child_process";
import {existsSync} from "node:fs";
import {mkdir,readFile,writeFile,stat} from "node:fs/promises";
import {join,dirname} from "node:path";
import {fileURLToPath} from "node:url";
const ROOT=dirname(fileURLToPath(import.meta.url));
const OUT=join(ROOT,"acceptance","logs","judge-video-20261023");
const EDGE="C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const URL="http://127.0.0.1:8077/demo";
const FPS=8,SECONDS=96,WIDTH=1440,HEIGHT=810;
const sleep=n=>new Promise(ok=>setTimeout(ok,n));
if(process.argv.length!==3||!["--shots","--record"].includes(process.argv[2]))throw Error("USAGE: --shots|--record");
if(!existsSync(EDGE))throw Error("EDGE_MISSING");
const health=await fetch("http://127.0.0.1:8077/health",{signal:AbortSignal.timeout(4000)}).then(r=>r.json());
if(!health.sample_mode_only)throw Error("DEMO_NOT_SAMPLE_LOCKED");
await mkdir(OUT,{recursive:true});
const profile=join(OUT,"video-isolated-edge-profile-"+process.argv[2].slice(2)+"-"+Date.now());
if(existsSync(join(profile,"DevToolsActivePort")))throw Error("CAPTURE_PROFILE_ALREADY_USED");
const edge=spawn(EDGE,["--headless=new","--no-first-run","--disable-extensions","--disable-sync","--disable-background-networking","--hide-scrollbars","--remote-debugging-port=0","--user-data-dir="+profile,"--window-size="+WIDTH+","+HEIGHT,URL],{stdio:"ignore",windowsHide:true});
let ws=null,id=0;
const waiting=new Map();
async function waitPort(){
 for(let i=0;i<100;i++){
  if(edge.exitCode!==null)throw Error("EDGE_EXITED");
  try{const x=(await readFile(join(profile,"DevToolsActivePort"),"utf8")).split(/\r?\n/)[0];if(Number(x)>0)return Number(x);}catch{}
  await sleep(160);
 }
 throw Error("CDP_PORT_MISSING");
}
async function connect(port){
 let page;
 for(let i=0;i<70;i++){
  try{const tabs=await fetch("http://127.0.0.1:"+port+"/json/list").then(r=>r.json());
      page=tabs.find(x=>x.type==="page"&&x.url.startsWith(URL));if(page)break;}catch{}
  await sleep(160);
 }
 if(!page)throw Error("CDP_TARGET_MISSING");
 ws=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((ok,bad)=>{
  const timer=setTimeout(()=>bad(Error("CDP_SOCKET_TIMEOUT")),7000);
  ws.addEventListener("open",()=>{clearTimeout(timer);ok();},{once:true});
  ws.addEventListener("error",()=>{clearTimeout(timer);bad(Error("CDP_SOCKET_ERROR"));},{once:true});
 });
 ws.addEventListener("message",ev=>{
  let m;try{m=JSON.parse(String(ev.data));}catch{return;}
  const p=waiting.get(m.id);if(!p)return;
  waiting.delete(m.id);clearTimeout(p.timer);
  if(m.error)p.bad(Error("CDP_"+p.method+"_"+m.error.message));
  else p.ok(m.result);
 });
}
function rpc(method,params={}){
 return new Promise((ok,bad)=>{
  const next=++id;
  const timer=setTimeout(()=>{waiting.delete(next);bad(Error("TIMEOUT_"+method));},15000);
  waiting.set(next,{method,ok,bad,timer});
  ws.send(JSON.stringify({id:next,method,params}));
 });
}
async function runjs(expression,awaitPromise=false){
 const m=await rpc("Runtime.evaluate",{expression,returnByValue:true,awaitPromise});
 if(m.exceptionDetails)throw Error("JS_EVAL_EXCEPTION_"+(m.exceptionDetails.text||""));
 return m.result?.value;
}
const CAPTIONS=[
 ["The future is not evidence","Yagi 2024 • Retrospective research • OFFLINE SAMPLE"],
 ["Freeze the clock at 16:30","It reports gauges measured at 15:00 but carries a displayed 16:37 publication dateline."],
 ["A 16:37 source is withheld","The computed verdict is INSUFFICIENT_EVIDENCE. See the source-exclusion receipt."],
 ["Now advance to 16:45","The new district article enters the eligible set. Research-only SIMULATED WARN."],
 ["The answer changes for a reason","Compare computes a newly eligible source, not a hardcoded clock switch."],
 ["Strict 2024 proof still fails","Without authenticated original article bytes, the correct answer is to abstain."],
 ["Do not confuse demo with sponsor PASS","Offline calls are samples. Live local Zetaris and H-MEM were proven separately. Nightshift is unverified."],
 ["What ran — and what did not","Zetaris: local REST 2/2. Official H-MEM: 1 recalled. Nightshift live: NOT VERIFIED."]
];
const START=[0,9,21,33,45,59,71,83,96];
async function title(i){
 const v=JSON.stringify(CAPTIONS[i]);
 await runjs("(function(){let box=document.getElementById('et-caption');if(!box){box=document.createElement('div');box.id='et-caption';box.style.cssText='position:fixed;bottom:0;left:0;right:0;z-index:999999;min-height:80px;background:rgba(25,39,40,.95);color:white;border-top:3px solid #b75c35;padding:12px 40px;box-sizing:border-box;font:15px/1.4 system-ui,sans-serif;pointer-events:none';document.body.appendChild(box);}let lines="+v+";box.replaceChildren();let a=document.createElement('strong');a.textContent=lines[0];a.style.fontSize='18px';box.appendChild(a);let b=document.createElement('div');b.textContent=lines[1];b.style.opacity='.83';b.style.fontSize='13px';box.appendChild(b);})()");
}
async function waitResult(id){
 await runjs("new Promise((ok,bad)=>{const start=Date.now();const timer=setInterval(()=>{const s=document.getElementById('"+id+"').textContent;if(s.startsWith('Pipeline executed')||s.includes('newly admitted source IDs:')){clearInterval(timer);ok(true);}else if(s.startsWith('Request failed')||Date.now()-start>11000){clearInterval(timer);bad(Error('NO_REAL_HTTP_RESULT'));}},85);})",true);
}
async function caseRun(when,strict=false){
 await runjs("(function(){document.getElementById('mode').value="+JSON.stringify(strict?"STRICT_AS_OF_2024":"REPORTED_DATELINE_REPLAY")+";document.querySelector('[data-clock=\""+when+"\"]').click();document.getElementById('run').click();})()");
 await waitResult("status");
 const x=await runjs("({verdict:document.getElementById('verdict').dataset.code,gate:document.getElementById('gateLabel').textContent,label:document.getElementById('label').textContent})");
 const expected=(!strict&&when.includes("16:45"))?"WARN":"INSUFFICIENT_EVIDENCE";
 if(x.verdict.trim()!==expected||!x.label.includes("OFFLINE SAMPLE"))throw Error("INCONSISTENT_LIVE_RESULT_"+JSON.stringify(x));
 console.log("COMPUTED",when,strict?"STRICT":"REPORTED",x.verdict.trim(),x.gate);
}
async function compare(){
 await runjs("document.getElementById('mode').value='REPORTED_DATELINE_REPLAY';document.getElementById('compare').click()");
 await waitResult("compareBox");
 const x=await runjs("document.getElementById('compareBox').textContent");
 if(!x.includes("GOV-2024-09-08-1637"))throw Error("COMPARE_NOT_COMPUTED");
 console.log("REAL_COMPARE",x.slice(0,200));
}
async function scroll(y){await runjs("window.scrollTo({top:"+y+",behavior:'instant'})");}
async function scene(i){
 await title(i);
 if(i===0)await scroll(0);
 if(i===1){await caseRun("2024-09-08T16:30");await scroll(150);}
 if(i===2)await scroll(410);
 if(i===3){await scroll(140);await caseRun("2024-09-08T16:45");}
 if(i===4){await scroll(150);await compare();}
 if(i===5){await caseRun("2024-09-08T16:45",true);await scroll(160);}
 if(i===6)await scroll(540);
 if(i===7){await rpc("Page.navigate",{url:"http://127.0.0.1:8077/proof"});await sleep(500);await title(i);await scroll(0);const name=await runjs("document.title");if(!String(name).includes("Local integration evidence"))throw Error("PROOF_PAGE_MISSING");}
}
async function shot(path){
 const ret=await rpc("Page.captureScreenshot",{format:"jpeg",quality:84,fromSurface:true,captureBeyondViewport:false});
 const bytes=Buffer.from(ret.data,"base64");if(bytes.length<10000)throw Error("EMPTY_CAPTURE");
 await writeFile(path,bytes);
}
async function encode(){
 const out=join(OUT,"EvidenceTrail_Track02_Actual_Demo_DRAFT_v3_2026-10-23.mp4");
 console.log("FFMPEG_ENCODE_START");
 await new Promise((ok,bad)=>{
  const f=spawn("ffmpeg",["-y","-hide_banner","-loglevel","error","-framerate",String(FPS),"-i",join(OUT,"frame-%05d.jpg"),"-vf","fps=24,format=yuv420p","-c:v","libx264","-preset","veryfast","-crf","22","-movflags","+faststart",out],{stdio:["ignore","ignore","pipe"],windowsHide:true});
  let err="";f.stderr.on("data",d=>err+=d.toString().slice(0,300));
  f.on("error",bad);f.on("exit",code=>code===0?ok():bad(Error("FFMPEG_EXIT_"+code+":"+err.slice(-300))));
 });
 const info=await stat(out);if(info.size<100000)throw Error("OUTPUT_VIDEO_TOO_SMALL");
 console.log("VIDEO_CREATED",out,"bytes",info.size,"silent_captioned",true);
}
try{
 const port=await waitPort();await connect(port);await rpc("Page.enable");await rpc("Runtime.enable");
 await rpc("Emulation.setDeviceMetricsOverride",{width:WIDTH,height:HEIGHT,deviceScaleFactor:1,mobile:false});
 const name=await runjs("document.title");if(!String(name).startsWith("EvidenceTrail"))throw Error("WRONG_TARGET");
 console.log("RECORDING_ONLY_LOCAL_APP",name,process.argv[2]);
 if(process.argv[2]==="--shots"){
  for(let i=0;i<CAPTIONS.length;i++){await scene(i);await sleep(200);await shot(join(OUT,"scene-"+i+".jpg"));console.log("SCENE_SAVED",i);}
 }else{
  let which=-1;const base=Date.now();
  for(let frame=0;frame<SECONDS*FPS;frame++){
   const sec=frame/FPS;const wanted=START.findIndex((v,i)=>i<START.length-1&&sec>=v&&sec<START[i+1]);
   if(wanted!==which){which=wanted;await scene(which);console.log("SCENE",which,"TIME",sec);}
   await shot(join(OUT,"frame-"+String(frame).padStart(5,"0")+".jpg"));
   const next=base+(frame+1)*(1000/FPS);if(Date.now()<next)await sleep(next-Date.now());
   if(frame>0&&frame%160===0)console.log("CAPTURED_FRAMES",frame);
  }
  await encode();
 }
 console.log("CAPTURE_SUCCESS");
}catch(e){console.error("CAPTURE_FAILURE",e.message);process.exitCode=1;
}finally{
 for(const p of waiting.values())clearTimeout(p.timer);
 if(ws&&ws.readyState===WebSocket.OPEN)ws.close();
 edge.kill();
}
