# EvidenceTrail product demo

Language: English. Target: about 2–3 minutes; final media duration comes from ffprobe. The browser walkthrough starts with an offline sample and ends with a genuine local Nightshift browser request for a fictional warehouse case. It is not combined with the Zetaris, H-MEM or NVIDIA sponsor executions.

| Segment | Genuine local action | Narration purpose |
| --- | --- | --- |
| Opening | WHY at 11:00 UTC; current claims visible | Define the analyst's problem and show source-bound 100 mph / 51 counties |
| Source dependence | Select FL-EO-24-215 removal | Show 51 → 35 counties and the named replacement |
| Historical uncertainty | Select Strict, run | Show abstention and missing original-availability evidence |
| Joint dependence | Load fictional warehouse; withdraw both STOCK-CHECK and STOCK-LEDGER | Show why one-source testing misses 25 → 12 pallets; same issuer, fictional |
| Source entry | Open guided case editor and source fields | Show typed quantities, dates, preview and review; preserve original case until adoption |
| Evidence update | Use the tested local source-entry/update behavior | Explain that a reviewed source can change a claim at the same clock; future evidence cannot enter early |
| Evidence boundaries | Proof register; separate sponsor statement | Explain real prior SQL/H-MEM/direct NVIDIA executions, the later separate Nightshift adapter probe, and n=0 analyst study |
| Nightshift local case | Show the captured browser flow: the checked opt-in, local request, rejected model response, and deterministic 25 → 12 fallback | Show one real `meterless/local` request and the quality gate rejecting malformed prose. EvidenceTrail keeps the computed values. State that route identity is self-reported and separate from the earlier CLI structural acceptance |

Use actual browser actions and check displayed values before capturing. Do not insert a mock provider response. Synthesized narration is a presentation aid, not a participant testimonial. Keep source IDs legible; hide credentials and personal windows by capturing only a fresh local browser profile.

## Nightshift segment capture notes

The 26 Oct CLI full-case run is summarized in `notes/113_NIGHTSHIFT_FULL_CASE_LOCAL_SUCCESS_2026-10-26.md`. A later browser run used the added prose-shape guard and returned `EXPLANATION_SHAPE_INVALID`; the UI retained a deterministic fallback. Its genuine headed Edge capture is `submission/media/EvidenceTrail_Nightshift_Live_Browser_20261026.webm`; the final cut uses a 30-second slice plus a designed summary card that matches the browser result. Do not display the token, environment setup, clipboard, or Runtime settings. The designed end card is not captured UI.

The recorded browser result can be shown without calling the model again. Do not repeat a model call solely to capture footage. The earlier structurally accepted CLI result remains separately recorded; its prose semantics are unverified.

```powershell
py -3 run_case_investigation.py --example warehouse --withdraw STOCK-CHECK STOCK-LEDGER --local-nightshift --receipt acceptance/logs/nightshift-local-demo-capture.json
```

Do not repeat the call just to substantiate the recorded run. Do not claim the generated prose was semantically verified, that the reported model route was independently attested, or that the fictional case is external evidence.
