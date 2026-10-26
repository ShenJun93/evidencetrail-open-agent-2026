# EvidenceTrail — skeptical competition audit, 24 October 2026

**Verdict: useful, reproducible research software; not yet supported as a first-place submission.** Main gaps remain genuine Nightshift execution/admission and independently observed user benefit. No winning probability is inferred. This is the implementing assistant's review, not an independent judge panel or external security certification.

Baseline: branch `work/evidencetrail-20261022`, HEAD `656088d0ee063dfec00eb49dbc72886927c11688`. Owner changes in README, `.env.example`, tracked acceptance outputs and untracked notes/configuration were present. They were preserved; commits stage only audit changes. No push, publication, external message, installer execution, new paid/model call or HackOS submission.

## Judge scorecard

These are conservative reviewer estimates conditional on admission, not awarded points. Potential assumes successful external evidence and delivery; it is **not achieved**. Confidence in scores is medium; confidence in the absence of verified human/Nightshift evidence is high.

| Criterion | Initial | Final supported | Conditional potential | Evidence, lost points, and leading-entry standard |
|---|---:|---:|---:|---|
| Impact /30 | 13 | 13 | 22 | Important evidence-review problem; actual user is an incident researcher/reviewer. No external analyst task outcomes, time savings or error reduction: n=0. A leading entry would show independently observed task improvements against a fair reference workflow. Internal gold cases do not earn field-impact credit. |
| Technical /20 | 14 | 16 | 18 | Reproducible collector→decision→auditor pipeline, memory postfilter, bounded requery and source-pinned claims. Fixed model-prose laundering and ambiguous latest claims. Still mostly deterministic orchestration; WHY is a separate deterministic analysis, not a demonstrated Nightshift reasoning loop. A leader would show useful novel-input investigation and a real sponsor-backed completion with recovery. |
| Innovation /15 | 11 | 11 | 12 | Strongest differentiator: source withdrawal produces exact typed before/after claims and replacement citations under a declared clock policy. Firewall, ledger, issuer tracking and memory auditing strengthen that one proposition; they are not six independent inventions. Most are bounded deterministic checks, not general semantic entailment or causal inference. A leader would transfer the method to independently selected unseen records. |
| Demo /15 | 10 | 11 | 14 | Actual Edge interactions and keyless cold replay; clearer three-minute WHY path and failure state. Missing complete real Nightshift segment; old video is not proof of current end-to-end behavior. A leader would demonstrate one coherent real task in under four minutes, including sponsor execution. |
| Product UX /10 | 7 | 8 | 9 | Existing controls show exact removal effects; now name unavailable sources, missing proof and next evidence action, with result clock and stale-result clearing. Still several views and a seven-record fixed browser corpus. A leader would support ordinary analyst tasks and demonstrate usability with independent users. |
| Sponsor Tech /10 | 5 | 5 | 9 | Real local Zetaris SQL, separately documented official H-MEM reference use and one earlier direct NVIDIA response. Runtime adapter/transport fixtures cannot establish Nightshift. No new sponsor credit for offline tests or the unchanged prior inference. A leader would show each required integration doing substantive work in the same app task. |
| **Total /100** | **60** | **64** | **84** | The four supported points reflect engineering/clarity, not fabricated impact or admission. |

## Current official requirements and authority

Read live on 24 October using public web retrieval and the existing authenticated Edge session. No onboarding checkbox, submission, survey answer, or message was submitted.

| Source | Verified requirement and authority limit |
|---|---|
| [Public event, expanded Rules 4–7](https://hackathon.genai.works/event/open-agent-hackathon-2026#rules) | Build 22 Oct 00:00 UTC–27 Oct 23:45 UTC; 1–5 people; one primary track; declare pre-existing product work; Zetaris and Meterless required; Cursor optional; use NVIDIA where useful. Video 1–4 minutes, deck, repository and sponsor explanation. Rubric remains 30/20/15/15/10/10. |
| [Academy overview](https://academy.genai.works/courses/open-agent-hackathon-2026/details) | Describes Data=Zetaris, Build=Meterless Engine, Power=Nightshift/Nemotron. The current rendered page did not expose the older direct-NVIDIA FAQ cited in prior notes. |
| [Authenticated Official Rules preview, Updated Oct 24](https://hackathon.genai.works/resources?id=01a08ff1-54cc-709a-bfe7-6b34452b676b) | Sections 8.1 and 16 require working Engine + primary Nightshift and warn about disqualification; 15.2 requires Nemotron through Nightshift for the NVIDIA award. **The preview itself says “Draft status” and identifies the event-page rules as binding.** Do not omit this qualification or claim this preview overrides that page. |
| [Authenticated Submission Requirements, Updated Oct 24](https://hackathon.genai.works/resources?id=01a08ff1-54c3-70c5-b262-31e75dfd1e60) | Sections 3.1/4 require a real app request through Nightshift in the demo and primary Nightshift plus an actual Meterless Engine. Public GitHub source, setup/usage/dependencies, deck and sponsor explanation required. It defers conflicts to event-page rules. |
| [Authenticated Technical Execution Requirements](https://hackathon.genai.works/resources?id=01a08ff1-54b1-7670-9441-a1e73ff43a6e) and [Disqualification Checklist](https://hackathon.genai.works/resources?id=01a08ff1-54d4-7755-a317-3c4167175ef8) | Both retain primary Nightshift and real-request trace guidance. Technical document explicitly describes itself as recommended practice unless binding rules say otherwise; checklist is preparation guidance. Both defer to event-page rules. Docker is recommended, not a verified universal mandate. |

**Decision:** Nightshift remains an admission-blocking risk, supported by current authenticated requirements, not merely old chat history. Public Meterless wording is broader but supplies no explicit waiver of the detailed Nightshift condition. No organizer ruling accepting H-MEM + direct NVIDIA alone has been obtained. Neither assume automatic qualification nor claim an organizer has already disqualified this entry.

Deadline is **28 October 2026, 06:45 Asia/Saigon**. Public event Rule 4 and authenticated requirements agree on submission close. Some ancillary dates differ between documents; do not substitute those for the verified cutoff. Public eligibility is 16+, one account/person, teams 1–5; organizer/judging-sponsor employees cannot receive cash. Owner eligibility beyond the recorded account/team has not been independently established.

Reachable Git root code commit is `cc51cd5`, author time 22 Oct 09:37:59 ICT, after opening. Commit timestamps are local history evidence, not a cryptographic authorship attestation. Declare earlier research/data and third-party H-MEM reference code; do not imply all work was newly authored in Cursor. Main checkout currently has no Git remote; public source and final submission are not established.

## Critical weaknesses and reproducible adversarial findings

| Priority | Reproducer / baseline failure | Implemented result or remaining limit |
|---|---|---|
| P0 | Current authenticated submission guidance requires app→Nightshift→result; verified application completions remain 0. | Cannot close with adapter code, direct NVIDIA, a spoofed localhost response or internal tests. Trusted runtime/organizer action required. |
| P1 | `ModelExplanationBoundaryTests`: valid WARN + eligible source ID + invented authenticated-byte/evacuation rationale. Baseline DecisionAgent exposes that rationale; an empty citation list erases actual supporting citations and Auditor can accept it. | All providers preserve reducer explanation and actual citations. Model may agree or veto; disagreement clears positive-claim citations. No general NLP verification is claimed. Both injected/default-constructor branches covered. |
| P1 | `ConflictingClaimTests`: pinned LAB-A=7 and LAB-Z=99 at the same latest clock. Baseline chooses 99 by lexical ID. Date-only documents can share a gate with unknown revision order. | Abstain for the conflicting claim, name conflict sources, retain unrelated valid claims. Never fall back to an older convenient value. Removing either contender is explicitly a simulated resolution, not truth. |
| P1 | `WhyProofBoundaryTests`: change a rule unit or a pinned issue clock while keeping excerpt hashes/as-of. Baseline emits the same input-policy digest. | Digest includes full pins, rules and policy version. It is still an unsigned consistency digest, not publisher authentication. |
| P1 | Successful live WHY CLI previously prints `sponsor_called=false`; a second-query failure forgets the first successful query. | Wrapper now records completed local SQL queries separately from `model_called=false`, preserves partial receipts, and reports unknown sponsor-call state if a failed live attempt has no completion. Original receipts preserved. |
| P2 | WHY displays old selected claims after a new replay fails. Existing UI also hides structured source exclusions and gives no next-evidence action. | Clear old results when replay begins; show result clock, exclusions, reason-specific evidence needs. Isolated Edge failure injection verifies the old conclusion is absent and removal disabled. |
| P2 | Source-review export omits `studies/analyst_participant.html` at runtime. Actual extracted ZIP acceptance then exposes a second omission: the Milton registration helper cannot be imported (521 tests, 1 import error). | Export four exact study source/protocol files, `register_zetaris_milton_filestore.py` and this audit. Do not allow participant responses, registry or generated packets. The failed archive remains unchanged. |
| P2 | Original browser harness uses fixed port 8079, risking a different running checkout or a port collision. Occupied-port negative control fails with `SAMPLE_SERVER_NO_HEALTH`. | Child server binds port 0 and reports its own port before health/UI checks. Same six scenarios PASS with port 8079 occupied and zero requests to that wrong server. This does not retrospectively identify the cause of the earlier unrecorded Edge error. |

Run the named regressions with `py -3 -m unittest tests.test_prize_audit_regressions -v`; export regression: `py -3 -m unittest tests.test_submission_source_audit -v`. The core attack tests were run before fixes and failed for the claimed behavior; the UI regression failed against original markup with `WHY_MISSING_EVIDENCE_EXPLANATION_ABSENT` before passing the restored implementation. Injected tests are not vendor receipts.

Other adversarial boundaries inspected: initial full-batch ID/URL/excerpt collision checks precede filtering; excerpt-byte hash mismatches are rejected; manifest pins reject forged precise issue clocks, numeric claims and issuer identities; future/retrospective documents cannot be promoted using observation or URL clocks; memory is postfiltered by mission, scenario, source and prior clock. Existing chronology, alias, requery-laundering, vendor-failure and spoofed-runtime suites were rerun.

**Limits not repaired by more tests:** distinct URLs or issuer labels do not establish witness independence; syndication needs curator lineage. A curator can still supply false source assertions/pins. Reported issue, valid, observation, receipt and first-publication clocks differ. Four GDACS relay witnesses do not authenticate original availability or add NOAA issuers. The strict generic ledger always abstains pending an external-attestation verifier; the separate Yagi archive module has narrower evidence semantics. Single-source deletion is not exhaustive coalition attribution or causal impact. The auditor checks citation membership/hash/chronology, not every semantic claim in arbitrary source paraphrases. Live Meterless failure can still use the explicitly labeled deterministic fallback; do not call it verified model reasoning. HTTP server is local SAMPLE_ONLY, not a deployed production service.

## Ranked backlog by expected judging value

Estimates are planning judgments, not awarded points; admission overrides point arithmetic.

| Rank | Task | Estimated value / effort | Risk, dependency, verification, confidence |
|---|---|---|---|
| 1 | Trusted actual Nightshift completion or explicit organizer acceptance of alternative | Admission; potentially +2–4 Sponsor and demo value / runtime-dependent, hours to days | High external dependency. Owner approval for billed requests/outgoing questions. Verify real process/route/result, Engine and Zetaris participation in one task. High confidence it matters; low confidence access can be obtained promptly. |
| 2 | Execute existing voluntary analyst pilot | Potential +5–9 Impact / recruitment + several hours | Requires actual independent adults and observer evidence, not automation. Fair reference view, counterbalance, predeclared scoring; report descriptive outcomes and limitations. Medium-low confidence in positive results; do not assume them. |
| 3 | Close explanation/conflict/digest/receipt bugs | Achieved +2 Technical / several focused changes | Low risk; full suite plus real local SQL, negative controls and cold replay. High confidence in bounded fixes. Implemented. |
| 4 | Make existing WHY journey explicit and clear stale results; repair source export dependency | Achieved +1 Demo, +1 UX / small existing-page and export changes | Low risk. Actual isolated Edge and clean source checks; no outside approval. Implemented. |
| 5 | Independently selected unseen case + externally attested publication body/time | Potential +1–3 Technical/Innovation / uncertain hours to days | External archive may not exist. Need admissible capture and verifier integration; no self-signed evidence. Medium confidence in value, low in availability. |
| 6 | Owner-reviewed public source, current video/deck, actual HackOS receipt | Required deliverables / hours after admission path is concrete | Explicit release/submission authorization needed. Public access/privacy/licensing and final receipt checks; no automatic publication. High confidence. |

Do **not** implement a new interface, extra sponsor adapters, a nominal Runtime-v5 migration, more cherry-picked gold cases, generated participant responses, repeated unapproved cloud calls, or another video draft before the top two external gaps. No score increase is awarded merely for test/file/commit counts.

## Implemented files

- `evidencetrail/agents/decision.py`: same trusted explanation/citation boundary for Meterless, NVIDIA and Nebius; clear citations on veto.
- `evidencetrail/claim_ledger.py`: same-latest-clock value conflict abstention, partial-result status and source IDs.
- `evidencetrail/why_counterfactual.py`: conflict reasons, excluded sources, next evidence actions; digest binds full policy inputs.
- `run_why_source_counterfactual.py`: truthful completed SQL/model boundaries, including partial failure.
- `demo/why.html`, `demo/verify_why_browser.mjs`: missing-evidence UI, exact clock, failure clearing and real Edge regression.
- `verify_counterfactual_browser.mjs`: browser test uses its own child server's ephemeral port; does not trust an existing listener at 8079.
- `run_submission_source_audit.py`, `tests/test_submission_source_audit.py`: exact study/registration dependency export, private response exclusion.
- `demo/proof.html`, `tests/test_proof_register_current.py`: replace stale replay claims with exact verified baseline/core evidence.
- `JUDGE_START_HERE.md`, `SUBMISSION_READY_START_HERE.md`: replace outdated checkpoint streams with current walkthrough and release gates. README gets only a current-review pointer; the owner's existing changes remain unstaged.
- `tests/test_prize_audit_regressions.py`: 14 targeted adversarial tests. This document is the canonical scorecard and review.

## Verification

Runtime: permitted loopback/full-suite execution used Python **3.14.7**, Node **24.20.0** and Microsoft Edge on the same Windows host. Sandbox-only focused checks used Python **3.13.15**. Scripts inspected before running. Sandbox TEMP/loopback restrictions caused initial environmental failures; reruns used a writable ignored audit TEMP and permitted loopback execution. No security check in product code was disabled.

| Source / command | Observed evidence |
|---|---|
| Fresh `git worktree add --detach .../baseline-clean 656088d0...`; `py -3 run_judge_coldstart.py` | PASS: 510 Python, 20 chronology, 6 isolated Edge. Clean before tests; no `.env.local` or vendor; `clean_keyless_source_replay=true`. Same host, not an independent human evaluation. |
| Core source `c1d81ab`; complete Python discovery | 524 PASS before core commit; 31 focused tests PASS after final receipt fix. No new model/vendor inference. |
| `node demo/verify_why_browser.mjs` | PASS: 100/51, missing evidence/result clock, 51→35, 155→125, Strict missing attestation, failure clears stale conclusion. Separate from cold runner's six scenarios. |
| `py -3 run_why_source_counterfactual.py --live --approve-local-zetaris --receipt acceptance/logs/prize-audit-20261024/why-local-zetaris-c1d81ab.json` (sanitized child environment) | PASS on **2 actual authenticated local SELECTs**, 7 source removals / 2 changed claims, 7 clock boundaries / 7 changes. `sponsor_called=true`, `model_called=false`, completed SQL=2. Manually curated metadata, not government live feeds. |
| Earlier pre-fix live WHY verification | Also 2 actual local SELECTs; old receipt-call flag defect preserved in `why-local-zetaris.json`. Total this audit: **4 local read-only SELECTs**, 0 new model calls. |
| `py -3 run_nvidia_claim_boundary_audit.py --output acceptance/logs/prize-audit-20261024/legacy-nvidia-audit.json` | Prior receipt matches the earlier one direct NVIDIA completion. Ambiguous authentication phrasing quarantined. No new NVIDIA/Zetaris calls; original response envelope cannot be independently reauthenticated from that local file. |
| `git diff --check` | PASS, nonfatal Windows line-ending notices only. |

Final observed results (all receipts/screenshots remain ignored; no generated acceptance output committed):

| Exact revision / reproduction | Result |
|---|---|
| `b172ceef014973a4abcee688001593746a5dec09`, fresh detached `acceptance/logs/prize-audit-20261024/isolated-final`; `py -3 run_judge_coldstart.py` | **PASS: 525 Python / 20 chronology / 6 isolated Edge**, all exits 0. Clean before tests, key file/vendor absent, `clean_keyless_source_replay=true`. Runner deliberately leaves `independent_clean_checkout_proven=false`; checkout creation was separately executed by this assistant, on the same host. Receipt SHA-256 `1f95ec968c267f7db8dd292cce4fcdda9829fbf5f598da76ef8dc0632b6aef9a`. |
| `0d3b93b5fdc37cfb258d5b169034e1507691dd50`; separate `node demo/verify_why_browser.mjs` and `node demo/verify_proof_register_browser.mjs` | Both PASS. These are additional UI workflows, not included in the cold runner's six scenarios. No product/UI source changed between this revision and `b172cee`; only the six-scenario browser harness changed. |
| `0d3b93b5...`; `py -3 run_submission_source_audit.py --archive --receipt acceptance/logs/prize-audit-source-export.json`; extract ZIP into new `acceptance/logs/prize-audit-20261024/source-replay-complete`; run `py -3 run_acceptance.py` with sanitized environment | **PASS: 525 tests, 0 failures/errors, 3 sample cases** from exported source, no key file. 172 selected files; 0 known-secret-pattern blockers; **6 files still need privacy review**. ZIP SHA-256 `5305f0517cb414969a1b24addefc79ee68ded571f5dfaeda9fc756b7d3064613`. This private candidate predates the final harness change; it is not published or approved as a final release. |
| Preserved failures | Earlier `ae8bdc0` ZIP: 521 tests / 1 missing-module error before registration-helper fix. First `0d3b93b5` cold receipt: Python/chronology PASS but Edge FAIL; original stderr was not retained by the runner. Same-source standalone Edge retry passed all six; cause remains unknown. Failing cold receipt SHA-256 `6226b93eb13ea289fd867547b3f65c3b9fc0a680bb6f45bd0d1c4a11153a41f8`. No failure receipt was edited into PASS. |
| Old-port adversarial control | Original harness on occupied 8079 fails `SAMPLE_SERVER_NO_HEALTH`. Replacement binds port 61401 in that test and passes all six UI scenarios with **0 requests** to the wrong server. Negative-control log: `acceptance/logs/prize-audit-20261024/fixed-port-negative-control.txt`. |

The final reporting commit changes only this document; verified executable source is `b172cee`. Reproduce using a **new unused** worktree path: `git worktree add --detach <unused-path> b172ceef014973a4abcee688001593746a5dec09`, then run `py -3 run_judge_coldstart.py` there. For this restricted Windows execution environment, TEMP/TMP were set to the writable ignored audit temp directory; ordinary owner execution may use the normal writable OS temp directory. The two previous real local SQL verifications occurred at the pre-receipt-fix working revision and core `c1d81ab`, respectively; no additional SQL/model calls were made merely to refresh later Git hashes.

## Second skeptical review and next three actions

The patch strengthens the actual evidence boundary and shows the missing proof, but it does not make the reasoning generally autonomous. A second review caught missing pivot IDs when withdrawal resolves an abstained conflict; `ae8bdc0` fixes that after a failing regression and 54 focused PASS. Extracted-source execution also exposed the registration-helper omission, fixed after 12 focused PASS. One later cold Edge stage failed once without preserved stderr; the identical standalone stage then passed. Its cause remains unknown. Separately, an occupied-port control proved the fixed-port isolation weakness and the new ephemeral-port test passed that control. The generic ledger still needs manually curated typed claims/rules; HTTP WHY accepts only its fixed corpus/clocks. A subsequent latest policy clock can supersede a conflict, which is a selection rule, not semantic reconciliation. The digest is not an external signature. Preserving the deterministic rationale limits the LLM to a checked proposal/veto. No score is added for H-MEM or NVIDIA execution not performed in this audit.

**Still not defensible as a first-place claim:** no independently observed analyst benefit, no verified primary Nightshift app run, no authenticated original-publication proof for Milton, no final public source/video/deck/submission receipt. 64/100 is a review estimate of the working product, not a competition result.

1. Owner obtains a trusted supported Nightshift route or dated explicit organizer admission ruling. Then, with any required billing approval, record one authentic app task and its routed model; do not use a mock/local self-report as vendor identity proof.
2. Owner recruits the existing eight voluntary independent pilot slots following `studies/README.md`, records consent/independence externally, collects real results and runs the existing scorer. Retain n=0 until participants are genuinely observed.
3. Once admission is concrete, review the exact source candidate and three-minute WHY narrative with the owner, publish only with authorization, finalize required assets and submit before **28 Oct 06:45 ICT**. Capture the actual confirmation; a draft is not submission.
