# EvidenceTrail

EvidenceTrail helps reviewers investigate which source changes a claim and when the evidence is insufficient. It is a research tool, with a local interactive demo and separate sponsor execution paths.

## Run the keyless product

Python 3.11+ is sufficient; no third-party Python package or API key is needed for the sample.

```sh
python -m evidencetrail serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/why`. Windows users can use `py -3` instead of `python`.

1. At 11:00 UTC the Milton sample selects **100 mph** and **51 counties**, with source IDs.
2. Simulate removing `FL-EO-24-215`: **51 → 35 counties**.
3. At 15:00 UTC, remove `NHC-AL142024-PUBLIC-010`: **155 → 125 mph**.
4. Run Strict policy: abstain and inspect missing original-availability evidence.
5. Try the fictional warehouse: removing both current records changes **25 → 12 pallets**.
6. Create or import a case, review source entries and add evidence at the same captured clock.

`/demo` shows the publication/observation timeline. `/proof` separates earlier real sponsor executions from the current offline browser computation. The default sample never fetches source URLs or calls a model. The separate, explicitly opted-in local Nightshift browser path has a genuine recorded request; on 26 Oct its prose failed shape validation and the UI retained a deterministic fallback.

## How it works

Full-batch identity and declared excerpt/value checks precede the source-clock filter. Typed rules select an admissible claim or abstain. Exact source-removal experiments and bounded group search report which values/citations change. Guided previews require explicit review; editing invalidates the preview. New evidence preserves existing records and compares at one clock/policy. The question is context; typed rules determine computation.

## Reproduce checks

```sh
python -m unittest discover -s tests -p 'test_*.py' -q
node demo/verify_why_browser.mjs
node demo/verify_proof_register_browser.mjs
```

Browser tests use built-in Node APIs and an isolated Microsoft Edge at the configured Windows path. The application itself has no Node dependency. Full cold acceptance is available through `run_judge_coldstart.py`; use a disposable checkout because it writes generated acceptance artifacts.

The latest 26 Oct judge replay passed 580 Python tests, 20 chronology checks, six original Edge scenarios, and the WHY Evidence Map interaction. The sanitized run receipt remains in the owner's local acceptance folder and is not included in the source candidate. The run used a dirty worktree with ignored `.env.local` and the Meterless vendor checkout present. The runner reports no key-file read or sponsor request, but this is not a clean keyless source replay. Earlier clean-checkout runs cover different source snapshots. These are automated engineering checks on one computer, not a user study.

## Sponsor execution boundaries

Earlier recorded runs consumed two authenticated local Zetaris query results (4 NOAA/NHC + 3 Florida metadata records), exercised the official Meterless H-MEM reference across processes, and obtained one direct NVIDIA Nemotron Lightning response. On 26 Oct, the optional EvidenceTrail full-case CLI completed one local Nightshift chat request for a fictional warehouse case; its response structure passed deterministic checks, while the model's prose remains unverified. The reported route was `local-runtime/llama-3.2-1b-instruct`, not independently attested. These are distinct executions. The final live-UI cut shows a separate local Nightshift browser request; its model prose was rejected by the output-shape guard and the deterministic fallback remained in force. This is not a unified sponsor pipeline. Sponsor eligibility is unresolved. Direct NVIDIA is not evidence of Nemotron through Nightshift.

The optional local-source CLI and live adapters have explicit approval/configuration gates and no fixture fallback on live failure. Do not place credentials in the browser or commit `.env.local`. No live provider call is needed for judge exploration.

## Evidence limits and provenance

Source pins check declared consistency; they do not independently authenticate publisher bytes or semantic entailment. Historical original first-publication availability remains unproved. Date-only clocks use a conservative policy cutoff. Warehouse/capacity records are visibly fictional. Source withdrawal is a controlled computation, not real-world causation. Independent analyst n=0; no measured time saved or field forecast accuracy is claimed.

Research/planning began before the build window. Third-party H-MEM reference components, government source material and fictional fixtures are disclosed separately. Reachable Git timestamps do not independently certify originality. See the repository license, the [judge walkthrough](../JUDGE_START_HERE.md), [current packet](../SUBMISSION_PACKET.md) and [claim ledger](CLAIM_LEDGER.md).
