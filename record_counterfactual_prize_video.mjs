/**
 * Genuine 3-minute Counterfactual Evidence Lab recording, research-only.
 * Uses only localhost sample server + isolated headless Microsoft Edge CDP.
 * Does NOT read credentials, use owner Edge profile, call any sponsor model,
 * submit/publicize content, or claim a real 2024 forecast.
 *
 * Windows MAIN-PC, Node 24 + Python 3 + Microsoft Edge + ffmpeg/ffprobe:
 *   node --check record_counterfactual_prize_video.mjs
 *   node record_counterfactual_prize_video.mjs --shots
 *   node record_counterfactual_prize_video.mjs --record
 *
 * Output stays ignored in acceptance/logs/prize-video-local/SESSION/.
 * --shots saves genuine scene images; --record makes SILENT REVIEW MP4.
 * Requires owner's manual review/voiceover before public submission.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const HOST = "http://127.0.0.1:8079";
const URL = HOST + "/demo";
const FPS = 8;
const SECONDS = 180;
const WIDTH = 1440, HEIGHT = 900;
const SCHEDULE = [0, 13, 40, 59, 91, 126, 152, 169, 180];
const CAPTIONS = [
  ["The Agent That Can Explain Why",
   "OFFLINE historical Yagi research replay. This is not a real disaster warning."],
  ["16:30 — the agent abstains",
   "No eligible district-named bulletin. INSUFFICIENT EVIDENCE is the correct result."],
  ["Time is not proof of publication",
   "A later report cannot be backdated from its observation time."],
  ["16:45 — one report becomes eligible",
   "SIMULATED WARN uses a dated bulletin AND explicitly FICTIONAL capacity."],
  ["Remove either pivotal source",
   "Two-source minimum. Removing the bulletin OR fictional capacity makes the rule abstain."],
  ["Strict as-of proof disagrees",
   "Unproven first-publication time means INSUFFICIENT EVIDENCE."],
  ["What really ran?",
   "Local Zetaris REST and official H-MEM reference were exercised separately."],
  ["What remains unverified?",
   "No accepted NVIDIA/Nebius decision; Nightshift and organizer eligibility unverified."]
];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const argv = process.argv.slice(2);
if (argv.length !== 1 || !["--shots", "--record"].includes(argv[0])) {
  throw new Error("USAGE: node record_counterfactual_prize_video.mjs --shots|--record");
}
if (!existsSync(EDGE)) throw new Error("ISOLATED_EDGE_EXECUTABLE_MISSING");
const MODE = argv[0];
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const OUTPUT = join(ROOT, "acceptance", "logs", "prize-video-local", stamp + "-" + MODE.slice(2));
const PROFILE = join(OUTPUT, "isolated-edge-profile");
const FRAMES = join(OUTPUT, "frames");
const VIDEO = join(OUTPUT, "EvidenceTrail_Counterfactual_DEMO_SILENT_REVIEW.mp4");
const envKeys = [
  "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "COMSPEC",
  "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
  "HOMEDRIVE", "HOMEPATH"
];
const safeEnv = {};
for (const key of envKeys) if (process.env[key]) safeEnv[key] = process.env[key];
Object.assign(safeEnv, {
  SAMPLE_MODE: "true",
  EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED: "false",
  EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT: "false",
  EVIDENCETRAIL_NVIDIA_35_VL_APPROVED: "false",
  EVIDENCETRAIL_NEBIUS_ENABLED: "false",
  EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT: "false",
  EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED: "false",
  PYTHONDONTWRITEBYTECODE: "1",
  PYTHONIOENCODING: "utf-8"
});
await mkdir(FRAMES, { recursive: true });
let server = null, edge = null, ws = null, serial = 0;
const pending = new Map();

function launch(cmd, args) {
  return spawn(cmd, args, {
    cwd: ROOT, windowsHide: true, stdio: "ignore", env: safeEnv
  });
}
async function healthCheck() {
  for (let i = 0; i < 85; i++) {
    if (server.exitCode !== null) throw new Error("LOCAL_SAMPLE_SERVER_EXITED");
    try {
      const res = await fetch(HOST + "/health", {
        signal: AbortSignal.timeout(1000)
      });
      const data = await res.json();
      if (res.ok && data.sample_mode_only === true) return;
    } catch {}
    await sleep(130);
  }
  throw new Error("LOCAL_SAMPLE_SERVER_HEALTH_NOT_VERIFIED");
}
async function portOfIsolatedEdge() {
  for (let i = 0; i < 100; i++) {
    if (edge.exitCode !== null) throw new Error("ISOLATED_EDGE_EXITED");
    try {
      const port = Number((await readFile(join(PROFILE, "DevToolsActivePort"), "utf8")).split(/\r?\n/)[0]);
      if (port > 0 && port <= 65535) return port;
    } catch {}
    await sleep(140);
  }
  throw new Error("EDGE_REMOTE_PORT_NOT_FOUND");
}
async function connect(port) {
  let page;
  for (let i = 0; i < 80; i++) {
    const tabs = await fetch("http://127.0.0.1:" + port + "/json/list")
      .then(r => r.json()).catch(() => []);
    page = tabs.find(t => t.type === "page" && t.url.startsWith(URL));
    if (page) break;
    await sleep(140);
  }
  if (!page) throw new Error("ISOLATED_DEMO_TAB_NOT_FOUND");
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP_CONNECT_TIMEOUT")), 8000);
    ws.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(timer); reject(new Error("CDP_CONNECT_FAILED")); }, { once: true });
  });
  ws.addEventListener("message", ev => {
    let v;
    try { v = JSON.parse(String(ev.data)); } catch { return; }
    const p = pending.get(v.id);
    if (!p) return;
    pending.delete(v.id);
    clearTimeout(p.timer);
    if (v.error) p.reject(new Error("CDP_REJECTED_" + p.name));
    else p.resolve(v.result);
  });
}
function rpc(name, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => {
      pending.delete(id); reject(new Error("CDP_TIMEOUT_" + name));
    }, 18000);
    pending.set(id, { name, timer, resolve, reject });
    ws.send(JSON.stringify({ id, method: name, params }));
  });
}
async function evaluate(expression, awaitPromise = false) {
  const value = await rpc("Runtime.evaluate", {
    expression, returnByValue: true, awaitPromise
  });
  if (value.exceptionDetails) throw new Error("DEMO_BROWSER_JS_FAILED");
  return value.result?.value;
}
async function ready() {
  for (let i = 0; i < 80; i++) {
    if (await evaluate(
      "document.readyState==='complete' && !!document.getElementById('mode') && " +
      "!!document.getElementById('when') && !!document.getElementById('counter') && " +
      "!!document.getElementById('counter-heading')"
    ).catch(() => false)) return;
    await sleep(150);
  }
  throw new Error("COUNTERFACTUAL_UI_NOT_READY");
}
async function showCaption(scene) {
  const lines = JSON.stringify(CAPTIONS[scene]);
  await evaluate("(function(){const lines=" + lines + ";" +
    "let box=document.getElementById('prize-capture-caption');" +
    "if(!box){box=document.createElement('div');box.id='prize-capture-caption';" +
    "box.style.cssText='position:fixed;bottom:0;left:0;right:0;z-index:999999;" +
    "background:rgba(14,31,40,.94);color:white;border-top:3px solid #b75c35;" +
    "padding:12px 28px;box-sizing:border-box;pointer-events:none;" +
    "font:15px/1.4 system-ui,sans-serif';document.body.appendChild(box);}" +
    "box.replaceChildren();const head=document.createElement('strong');" +
    "head.textContent=lines[0];head.style.fontSize='21px';box.appendChild(head);" +
    "const para=document.createElement('div');para.textContent=lines[1];" +
    "para.style.fontSize='14px';para.style.marginTop='2px';box.appendChild(para);" +
    "})()");
}
async function counter(mode, clock) {
  await evaluate("(function(){document.getElementById('mode').value=" +
    JSON.stringify(mode) + ";document.getElementById('when').value=" +
    JSON.stringify(clock) + ";document.getElementById('counter').click()})()");
  const status = await evaluate(
    "new Promise((resolve,reject)=>{let n=0;" +
    "const timer=setInterval(()=>{n++;const t=document.getElementById('counterStatus').textContent;" +
    "if(t.startsWith('PASS')){clearInterval(timer);resolve(t);}" +
    "else if(t.startsWith('Counterfactual analysis failed')||n>120){" +
    "clearInterval(timer);reject(Error('NO_CONFIRMED_LOCAL_PIPELINE'));}},100)})", true
  );
  if (!String(status).startsWith("PASS")) throw new Error("COUNTERFACTUAL_PIPELINE_NOT_PASS");
  const data = await evaluate("({verdict:document.getElementById('verdict').dataset.code," +
    "witness:document.getElementById('cfWitness').textContent," +
    "ablations:document.getElementById('cfAblations').textContent," +
    "policy:document.getElementById('cfPolicyInfo').textContent," +
    "requirements:document.getElementById('cfRequirements').textContent})");
  const warn = mode === "REPORTED_DATELINE_REPLAY" && clock.endsWith("16:45");
  if (data.verdict !== (warn ? "WARN" : "INSUFFICIENT_EVIDENCE")) {
    throw new Error("UNEXPECTED_COMPUTED_VERDICT");
  }
  if (warn) {
    if (!data.witness.includes("Exact minimum set: 2") ||
        !data.ablations.includes("GOV-2024-09-08-1637") ||
        !data.ablations.includes("SYN-CAP-YAGI-ALPHA-LUCYEN") ||
        !data.ablations.includes("PIVOTAL") ||
        !data.requirements.includes("MISSING REAL SITE POPULATION")) {
      throw new Error("PIVOTAL_WITNESSES_NOT_VERIFIED");
    }
  } else if (mode === "STRICT_AS_OF_2024") {
    if (!data.requirements.includes("HISTORICAL AVAILABILITY NOT AUTHENTICATED") ||
        !data.witness.includes("No sufficient WARN set")) {
      throw new Error("STRICT_MODE_EVIDENCE_GATE_MISSING");
    }
  } else if (!data.requirements.includes("MISSING DISTRICT NAMED BULLETIN")) {
    throw new Error("EARLY_ABSTENTION_MISSING_REASON");
  }
  return data;
}
async function scroll(target) {
  const expression = target === "top" ? "window.scrollTo({top:0,behavior:'instant'})" :
    "document.getElementById(" + JSON.stringify(target) +
    ").scrollIntoView({block:'start',behavior:'instant'})";
  await evaluate(expression);
}
async function scene(index) {
  if (index === 0) await scroll("top");
  if (index === 1) {
    await counter("REPORTED_DATELINE_REPLAY", "2024-09-08T16:30");
    await scroll("counter-heading");
  }
  if (index === 2) await scroll("counter-heading");
  if (index === 3) {
    await counter("REPORTED_DATELINE_REPLAY", "2024-09-08T16:45");
    await scroll("counter-heading");
  }
  if (index === 4) {
    await scroll("cfAblations");
  }
  if (index === 5) {
    await counter("STRICT_AS_OF_2024", "2024-09-08T16:45");
    await scroll("counter-heading");
  }
  if (index === 6) {
    await rpc("Page.navigate", { url: HOST + "/proof" });
    await sleep(600);
    for (let i = 0; i < 45; i++) {
      const title = await evaluate("document.title").catch(() => "");
      if (String(title).includes("Local integration evidence")) break;
      await sleep(100);
    }
    const title = await evaluate("document.title");
    if (!String(title).includes("Local integration evidence")) {
      throw new Error("LOCAL_SPONSOR_PROOF_PAGE_MISSING");
    }
    await scroll("top");
  }
  if (index === 7) await scroll("top");
  await showCaption(index);
}
async function capture(path) {
  const reply = await rpc("Page.captureScreenshot", {
    format: "jpeg", quality: 80, captureBeyondViewport: false, fromSurface: true
  });
  const data = Buffer.from(reply.data, "base64");
  if (data.length < 10_000) throw new Error("FRAME_NOT_RENDERED");
  await writeFile(path, data);
}
async function runProcess(bin, args) {
  await new Promise((resolve, reject) => {
    const proc = spawn(bin, args, {
      cwd: ROOT, env: safeEnv, windowsHide: true, stdio: "ignore"
    });
    proc.once("error", () => reject(new Error("LOCAL_ENCODER_MISSING")));
    proc.once("exit", code => code === 0 ? resolve() : reject(new Error("LOCAL_ENCODER_FAILED")));
  });
}
async function encodeVideo() {
  await runProcess("ffmpeg", [
    "-n", "-hide_banner", "-loglevel", "error",
    "-framerate", String(FPS), "-i", join(FRAMES, "frame-%05d.jpg"),
    "-vf", "fps=24,format=yuv420p", "-c:v", "libx264",
    "-preset", "veryfast", "-crf", "22", "-movflags", "+faststart", VIDEO
  ]);
  const size = (await stat(VIDEO)).size;
  if (size < 100_000) throw new Error("ENCODED_VIDEO_TOO_SMALL");
  console.log("SILENT_DRAFT_CREATED", VIDEO, "bytes", size);
  console.log("DURATION_SECONDS_EXPECTED", SECONDS, "NOT_INDEPENDENTLY_VERIFIED");
}
try {
  server = launch("py", ["-3", "-m", "evidencetrail", "serve",
    "--host", "127.0.0.1", "--port", "8079"]);
  await healthCheck();
  edge = launch(EDGE, [
    "--headless=new", "--no-first-run", "--disable-extensions",
    "--disable-sync", "--disable-background-networking", "--hide-scrollbars",
    "--remote-debugging-port=0", "--user-data-dir=" + PROFILE,
    "--window-size=" + WIDTH + "," + HEIGHT, URL
  ]);
  await connect(await portOfIsolatedEdge());
  await rpc("Page.enable");
  await rpc("Runtime.enable");
  await rpc("Emulation.setDeviceMetricsOverride", {
    width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false
  });
  await ready();
  console.log("OFFLINE_SAMPLE_EDGE_RESEARCH_ONLY", MODE);
  if (MODE === "--shots") {
    for (let i = 0; i < CAPTIONS.length; i++) {
      await scene(i); await sleep(250);
      await capture(join(OUTPUT, "scene-" + i + ".jpg"));
      console.log("REAL_UI_SCENE_CAPTURED", i);
    }
    console.log("SHOT_REVIEW_ONLY", OUTPUT);
  } else {
    let lastScene = -1;
    const base = Date.now();
    for (let frame = 0; frame < SECONDS * FPS; frame++) {
      const second = frame / FPS;
      const desired = SCHEDULE.findIndex((s, i) =>
        i < SCHEDULE.length - 1 && second >= s && second < SCHEDULE[i + 1]);
      if (desired < 0) throw new Error("INVALID_VIDEO_STORYBOARD");
      if (desired !== lastScene) {
        await scene(desired);
        lastScene = desired;
        console.log("VERIFIED_LIVE_SCENE", desired, "second", second);
      }
      await capture(join(FRAMES, "frame-" +
        String(frame).padStart(5, "0") + ".jpg"));
      const next = base + (frame + 1) * 1000 / FPS;
      if (Date.now() < next) await sleep(next - Date.now());
    }
    await encodeVideo();
    await writeFile(join(OUTPUT, "review-status.json"), JSON.stringify({
      kind: "EVIDENCETRAIL_PRIZE_VIDEO_LOCAL_REVIEW_V1",
      sample_only: true,
      raw_live_inference_performed: false,
      sponsor_compliance_verified: false,
      actual_forecast_accuracy_verified: false,
      duration_seconds_expected_not_independently_verified: SECONDS,
      footage: "REAL_LOCALHOST_EDGE_UI_ACTIONS; SILENT REVIEW ONLY",
      output: "EvidenceTrail_Counterfactual_DEMO_SILENT_REVIEW.mp4"
    }, null, 2) + "\n");
  }
} catch (err) {
  console.error("LOCAL_CAPTURE_REFUSED", err.message);
  process.exitCode = 2;
} finally {
  for (const p of pending.values()) clearTimeout(p.timer);
  if (ws && ws.readyState === WebSocket.OPEN) ws.close();
  if (edge) edge.kill();
  if (server) server.kill();
}
