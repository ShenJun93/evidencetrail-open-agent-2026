// EvidenceTrail opt-in bridge to the Meterless H-MEM TypeScript reference.
// This is NOT the Nightshift runtime and NOT a conformance certificate.
// Runs ONLY on explicit HMEM_ENGINE_MODE=official_reference opt-in.
// Interpreter: node --import tsx <this-file>; cwd is the reference checkout.
// No installer, download, network, or background server is started here.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

type Request = {
  op: "status" | "add" | "query" | "ledger";
  persistDir: string;
  content?: string;
  source?: string;
  missionId?: string;
  goalRunId?: string;
  tags?: string[];
  text?: string;
  topN?: number;
  memoryId?: string;
};

function requireText(value: unknown, key: string, max = 4096): string {
  if (typeof value !== "string" || !value.trim() || value.length > max) {
    throw new Error(key + " must be a nonempty bounded string");
  }
  return value;
}
function safeRecord(memory: Record<string, unknown>): Record<string, unknown> {
  const { embedding: _embedding, ...safe } = memory;
  return safe;
}
async function main(): Promise<void> {
  const raw = fs.readFileSync(0, "utf8");
  if (Buffer.byteLength(raw, "utf8") > 64 * 1024) {
    throw new Error("H-MEM bridge input exceeds 64 KiB");
  }
  const req = JSON.parse(raw) as Request;
  if (!req || !["status", "add", "query", "ledger"].includes(req.op)) {
    throw new Error("unsupported H-MEM bridge operation");
  }
  const persistDir = path.resolve(requireText(req.persistDir, "persistDir", 1024));
  const referenceIndex = path.resolve(process.cwd(), "src", "index.ts");
  if (!fs.existsSync(referenceIndex) ||
      path.basename(process.cwd()).toLowerCase() !== "reference") {
    throw new Error("official H-MEM reference checkout not present");
  }
  // Code loaded only from owner-configured local vendor checkout.
  const { HMEM } = await import(pathToFileURL(referenceIndex).href);
  if (typeof HMEM !== "function") {
    throw new Error("official H-MEM module does not export HMEM");
  }
  const engine = new HMEM({ persistDir, actor: "evidencetrail" });
  const base = {
    ok: true, implementation: "meterless-official-ts-reference",
    conformance: "NOT_RUN_BY_BRIDGE",
  };
  if (req.op === "status") {
    process.stdout.write(JSON.stringify({
      ...base,
      memoryCount: engine.store.all().length,
      ledgerLen: engine.ledger.all().length,
    }) + "\n");
    return;
  }
  if (req.op === "add") {
    const content = requireText(req.content, "content", 8192);
    const source = requireText(req.source, "source", 256);
    const tags = req.tags ?? [];
    if (!Array.isArray(tags) || tags.some(t => typeof t !== "string" || t.length > 256)
        || tags.length > 48) {
      throw new Error("invalid tags");
    }
    const record = engine.add({
      content, source, type: "factual", layer: "working",
      tags, missionId: req.missionId, goalRunId: req.goalRunId,
    });
    const ledgerEntries = engine.ledger.history(record.id);
    if (!ledgerEntries.some((item: { action: string }) => item.action === "create")) {
      throw new Error("missing required H-MEM create audit entry");
    }
    process.stdout.write(JSON.stringify({
      ...base,
      record: safeRecord(record),
      ledgerLen: engine.ledger.all().length,
      createLedgerCount: ledgerEntries.length,
    }) + "\n");
    return;
  }
  if (req.op === "query") {
    const q = requireText(req.text, "text", 4096);
    const topN = Math.max(1, Math.min(8, Math.floor(req.topN ?? 8)));
    // Upstream has no historical as-of filter; Python must postfilter recall.
    const result = engine.query(q, { topN, threshold: 0 });
    engine.store.persist();
    const hits = result.memories.map(
      ({ memory, relevance }: { memory: Record<string, unknown>; relevance: number }) =>
        ({ ...safeRecord(memory), score: relevance })
    );
    process.stdout.write(JSON.stringify({
      ...base, hits, upstreamAsOfFilter: "NONE_UPSTREAM",
      trace: result.trace, ledgerLen: engine.ledger.all().length,
    }) + "\n");
    return;
  }
  const history = req.memoryId
    ? engine.ledger.history(requireText(req.memoryId, "memoryId", 128))
    : engine.ledger.all();
  process.stdout.write(JSON.stringify({
    ...base,
    ledgerLen: engine.ledger.all().length,
    actions: history.slice(-100).map(
      (entry: { memoryId: string; action: string; timestamp: number }) => ({
        memoryId: entry.memoryId, action: entry.action,
        timestamp: entry.timestamp,
      })
    ),
  }) + "\n");
}
main().catch((error: unknown) => {
  // Never emit memory payloads, credential values or stdin as diagnostics.
  const name = error instanceof Error ? error.name : "Error";
  process.stderr.write("evidencetrail H-MEM bridge " + name + "\n");
  process.exitCode = 2;
});
