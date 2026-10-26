# EvidenceTrail — current submission packet

Prepared 26 October 2026 for Track 02, **The Agent That Can Explain Why**.

**Local review package prepared; nothing published or sent to HackOS. Eligibility remains unresolved.** This document supersedes the 24 October working descriptions and form copy. It does not certify sponsor compliance or create a submission.

See the current [internal prize-readiness review](PRIZE_REVIEW_2026-10-26.md) for the ranked remaining risks and the updated Nightshift evidence boundary.

## Form copy

- Project title: **EvidenceTrail — Investigate What Changes a Claim**
- Tagline, if a field is offered: **Trace a conclusion to its sources, test its dependencies, and know when to abstain.**
- Primary track: **02 — The Agent That Can Explain Why**
- Team last verified in the earlier authenticated session: **ShenJun93, solo**. Confirm the intended roster before creating the first submission; that action locks composition.
- Description: paste [submission/description.txt](submission/description.txt). The old 1,756-character description is obsolete.
- GitHub candidate: `https://github.com/ShenJun93/evidencetrail-open-agent-2026`. GitHub metadata rechecked 26 Oct: **private, size 0, default branch main**; this checkout has no configured Git remote. It is not judge-accessible.
- Video/deck: use the local review assets listed below after viewing them. No public video or deck URL has been created. Do not paste localhost or invent a share URL.

## Problem and user

Incident researchers and evidence reviewers need to explain why a conclusion was justified at a particular time. A later document or repeated source can make a retrospective explanation look stronger than the evidence available at the decision boundary.

The first useful job is an analyst's review: select the clock and policy, see the chosen claim and its source, test what changes when that source is missing, then identify the next evidence check. The WHY screen now opens with a visual source-to-claim map: source nodes are labeled admitted/not admitted at the selected clock, the rule-selected claim names its source, and choosing a node previews the exact withdrawal effect. This is a more visual explanation of the existing deterministic result, not a new confidence score or source-authentication signal. Broader compliance/insurance applications remain possible directions, not validated customer deployments.

## Implemented solution

EvidenceTrail validates the full source batch against declared identity/value/excerpt expectations before time filtering. It separates reported issue/date replay from strict historical availability. Exact source-withdrawal and bounded subset search expose numeric changes, lost claims and citation-only changes separately. Conflicting latest declarations cause abstention.

The new local workbench supports source entry, review-before-adoption, typed JSON import, joint source tests and addition of reviewed evidence while preserving original records. Before and after share the captured clock and policy. Exported evidence requests describe analyst work still to do; they are not autonomous collection receipts. Drafts remain in page memory, without browser persistence.

The main demo shows Milton **100 mph / 51 counties**, withdrawal **51 → 35**, later NOAA withdrawal **155 → 125**, and Strict abstention. A separate visibly fictional warehouse shows **25 → 12 pallets only after both current records are withdrawn**. Its two records share an issuer and do not establish independent corroboration.

## Architecture and AI contribution

```
Browser source entry / typed case / curated sample
    → full-batch identity, excerpt-pin and declared-value checks
    → source-clock and evidence-policy filter
    → typed claim selection or explicit abstention
    → single/joint withdrawal analysis + same-clock evidence update
    → source explanation, missing-evidence plan and local export

Separate sponsor execution paths:
Zetaris fixed local SQL tables → checked source rows → deterministic evidence gate
Official H-MEM reference → persistent retrieval + scenario/time postfilters
Direct NVIDIA Lightning → bounded JSON proposal → numeric/citation checks
Nightshift adapter → one real local chat completion and matched Runtime receipt
```

The browser computation is deterministic, keyless and local. The separate model path proposes bounded structured content; deterministic checks retain authority over admissible sources and selected values. The one earlier direct NVIDIA answer does not prove Nightshift integration or semantic correctness of every free-text word.

Python 3.11+ standard library and vanilla HTML/CSS/JavaScript power the local app. Node and Edge are optional browser-test tools. No build system, third-party font or API key is required to explore the sample.

## Sponsor explanation

| Technology | Actual role and evidence | Boundary |
| --- | --- | --- |
| Zetaris | Two authenticated loopback SELECTs consumed 4 NOAA/NHC and 3 Florida metadata records; fixed-table CLI has no sample fallback | Separate recorded execution; current browser sample makes no SQL request |
| Meterless H-MEM | Official TypeScript reference add/query across processes with scenario/time isolation | Separate engine execution; clean Python sample uses its disclosed fallback |
| NVIDIA | One accepted direct `nvidia/nemotron-3.5-lightning-30b-a3b` completion, 796 reported tokens, from admissible Zetaris-selected inputs | Direct route; not Nemotron-through-Nightshift proof |
| Nightshift | The 26 Oct CLI run returned `STRUCTURE_ACCEPTED_PROSE_UNVERIFIED` for a fictional `25 → 12` case. A later opt-in browser request failed output-shape validation and the UI showed a deterministic source-bound fallback; the updated video contains that actual flow ([CLI run note](notes/113_NIGHTSHIFT_FULL_CASE_LOCAL_SUCCESS_2026-10-26.md), [browser run note](notes/114_NIGHTSHIFT_BROWSER_UI_RUN_2026-10-26.md)) | Runtime route is self-reported; CLI prose semantics unverified; browser proposal rejected. Fictional/offline cases only, no combined Zetaris/H-MEM/NVIDIA execution or organizer clearance |
| Development tools | Codex implemented and reviewed current work, ran local tests and prepared this packet; earlier Cursor/other-agent work remains disclosed | No claim that one coding tool authored the entire repository |

The optional `run_case_investigation.py --local-nightshift` path asks
`meterless/local` to propose a short explanation for one deterministic
before/after claim. On 26 Oct, one fictional warehouse request returned
`STRUCTURE_ACCEPTED_PROSE_UNVERIFIED`; claim fields were copied from the
deterministic report, not authored by the model. An earlier attempt returned
HTTP 400 while the lane was parked for VRAM. The accepted result does not
verify prose semantics or independently attest the reported local route.

The distinctive contribution is applying the same evidence firewall to SQL-returned records, memory retrieval and model proposals, then exposing exact source dependencies. This is implemented behavior; its analyst time-saving value remains a hypothesis.

## Evidence and limitations

- Product source **bc0d37d**: 568 Python tests PASS on the owner machine; isolated Edge workflows PASS. Fresh detached keyless checkout passed WHY/workbench and proof/navigation, including 375/768/1440px, keyboard, draft preservation and textarea reflow. The original six Edge scenarios also passed. All are engineering checks, not human studies.
- Current local worktree: **580 Python tests, 20/20 chronology, 6 Edge scenarios, and WHY Evidence Map interaction PASS** in the 26 Oct keyless judge replay. Sanitized report: [`acceptance/logs/judge-coldstart-replay.json`](acceptance/logs/judge-coldstart-replay.json). It ran on dirty HEAD `fff6ab8`; `.env.local` and the Meterless vendor checkout were present, so it is not a clean keyless source replay. Runner reports no key-file read and no external sponsor calls. These are same-machine engineering checks, not independent or cross-platform results.
- Guided workbench core **d99de16**: separate earlier clean cold replay, 566 Python + 20 chronology + six original Edge scenarios PASS, plus WHY/workbench/navigation.
- Earlier sponsor execution: the [claim ledger](submission/CLAIM_LEDGER.md) records dates, model identity, SQL source counts and limits, summarized from local notes 97/99 and the prior H-MEM integration evidence. Raw ignored runtime receipts stay private.
- Declared pins establish local consistency, not independent source truth or entailment. Original 2024 first-publication timestamps/source bytes remain unauthenticated. Date-only cutoffs are conservative policy bounds.
- Imported cases are bounded to 12 sources/rules and 60,000 UTF-8 bytes. Natural-language questions provide context; typed claim rules determine computation. Group search is inclusion-minimal within declared size 1–3, not an exhaustive unbounded proof.
- **Independent analyst n=0**. No measured time saved, field impact, forecast accuracy, external benchmark superiority or organizer eligibility clearance is claimed.

## Pre-existing components and licenses

Research framing, planning and source investigation began before 22 October and are disclosed as pre-existing. The first reachable repository commit is dated 22 Oct 2026 09:37:59 ICT, after the 07:00 ICT opening; Git dates alone do not prove all underlying work originated then. Source ablation, generic case investigation, reviewed source updates and the new UI are later recorded additions. Third-party official H-MEM reference code and public government reference material are not original EvidenceTrail inventions. Fictional capacity/warehouse inputs are labeled. Review `LICENSE` and dependency notices before publication.

## Local review assets

Review copies of the deck, current video and screenshots are in `submission/media/`; generated originals remain under ignored `acceptance/logs/`. Recommended video: `EvidenceTrail_Track02_Product_Demo_EvidenceMap_20261026.mp4`. It contains a genuine browser capture of the separate local Nightshift request and a clearly labeled Evidence Map end card. The 3:21 and 1:33 cuts are superseded. The available SRT captions belong to the older 3:21 cut and must not be paired with the recommended video.

The WHY screen includes a visual source-to-claim Evidence Map and selectable withdrawal preview. The latest Edge E2E captured it as `submission/media/01-conclusion.png`; the refreshed deck and video candidate include this view.

- `submission/media/EvidenceTrail_Track02_Deck_EvidenceMap_20261026.pptx` and `.pdf`: refreshed 8-slide English deck with the Evidence Map and 580-test replay count, while retaining the browser rejection/fallback and human-impact and sponsor boundaries.
- `submission/media/EvidenceTrail_Track02_Product_Demo.mp4`: **201.02 seconds (3:21)**, H.264/AAC, English synthesized narration and burned-in captions. This historical cut says 568 tests and claims Nightshift proof is incomplete; **do not upload it**. Captions are retained for provenance in `submission/media/EvidenceTrail_Demo_Captions.srt`.
- `submission/media/EvidenceTrail_Track02_Remotion_Nightshift_20261026.mp4`: **93.013 seconds (1:33)**, 1920×1080 H.264/AAC. Its final card summarizes the 26 Oct full-case local Nightshift receipt; it is explicitly a designed receipt summary, not screen footage of the live request. Full decode passed. This is not the latest cut; use the LiveUI variant if a video is needed, after owner review.
- `submission/media/EvidenceTrail_Track02_Product_Demo_EvidenceMap_20261026.mp4`: refreshed 2:03 cut with actual browser footage of the local Nightshift request, deterministic quality-gate fallback, and the current Evidence Map end card. The end card is designed media, not captured UI.
- `submission/media/01-conclusion.png` through `08-proof.png`: supporting product screenshots. `01-conclusion.png` now shows the latest Edge-captured source-to-claim Evidence Map; other screenshots retain their earlier capture dates.
- Screenshots: conclusion/source removal, Strict abstention, joint withdrawal and the responsive workbench.
- Local source candidate: `submission/EvidenceTrail_Track02_SOURCE_REVIEW_20261026.zip`, based on `fff6ab8` plus 15 explicit current code/document overlays. Its report is `submission/source-candidate-review-20261026.json`. The bounded text scan found no known-pattern blockers and three synthetic NVIDIA test-token warnings; privacy, licensing and release review are still required. The ZIP has not been published or submitted.

## Judge replay

```
py -3 -m evidencetrail serve --host 127.0.0.1 --port 8765
# Open http://127.0.0.1:8765/why
py -3 -m unittest discover -s tests -p 'test_*.py' -q
node demo/verify_why_browser.mjs
node demo/verify_proof_register_browser.mjs
```

Use `python` instead of `py -3` on non-Windows systems. Browser tests currently require the configured Windows Edge path; no cross-browser/hardware or complete WCAG certification is claimed. Run `run_judge_coldstart.py` in a disposable checkout because it writes generated acceptance outputs. The [judge walkthrough](JUDGE_START_HERE.md) gives exact source IDs and expected changes.

## Release checklist and priority

1. **Human-review media.** Review the refreshed deck and video, including audio/captions and the browser rejection/fallback. Exact authenticated Track 02 guidance and eligibility still need verification.
2. **Review the exact source candidate and make the GitHub repo judge-accessible.** It is currently private and empty. Review secrets, privacy, licenses and pre-existing declarations; publishing/push is a separate external step, not performed here.
3. **Watch the video and deck, then supply accessible assets.** Genuine screen footage is now included and under four minutes. Confirm solo roster, exact live form and sponsor disclosure, then submit through HackOS and preserve its confirmation before the deadline.

Independent pilot results would strengthen Impact but are not represented here as a separate official admission requirement. The owner has no volunteers yet and chose product work first. Do not manufacture participants or delay the required deliverables to invent impact.

## Rule authority checked 26 October

[Public event page and expanded rules](https://hackathon.genai.works/event/open-agent-hackathon-2026#rules): Track 02 asks for agents that investigate across multiple data sources and produce evidence-backed answers or recommendations. Public judging weights are Impact 30, Technical 20, Innovation 15, Demo 15, Product & UX 10, Sponsor Tech 10. The Wildcard expressly requires Zetaris and Meterless.

Deadline: **27 Oct 2026 23:45 UTC = 28 Oct 2026 06:45 Vietnam time**. The current Edge session was signed out, so authenticated resource/form state was not rechecked; exact field lengths and Nightshift-specific wording retain the dated 24 Oct observation, not a claim of a fresh authenticated check. The candidate GitHub repository was last observed private and empty. No Devpost project is created: this event uses HackOS.
