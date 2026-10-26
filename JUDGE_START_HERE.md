# EvidenceTrail — Judge start here

Product walkthrough updated 26 October 2026. This replaces the historical checkpoint stream previously on this page. See [the competition audit dated 24 October](PRIZE_AUDIT_2026-10-24.md) for its score baseline, defects, verification and rule authority.

**Current entry materials:** [submission packet](SUBMISSION_PACKET.md), [form description](submission/description.txt), [editable deck](submission/media/EvidenceTrail_Track02_Deck_EvidenceMap_20261026.pptx), [current 2:03 demo](submission/media/EvidenceTrail_Track02_Product_Demo_EvidenceMap_20261026.mp4), [upload manifest](submission/UPLOAD_MANIFEST_20261026.md), and [public README](submission/PUBLIC_README.md). The latest local judge replay passed 580 Python tests, 20 chronology checks, six Edge scenarios and the WHY Evidence Map interaction. It ran on dirty HEAD `fff6ab8`; `.env.local` and the Meterless vendor checkout were present, so it is not a clean keyless source replay. The runner reports no key-file read or sponsor call. The Nightshift CLI passed structural checks only; a separate browser request failed the output-shape guard and preserved the deterministic result. Route identity and prose semantics remain unverified; human impact is unmeasured.

**EvidenceTrail explains which sources support a claim, which are unavailable, and which combinations of missing sources change the conclusion.** Reviewers can import a new typed case and rerun the same checks. Intended users are incident researchers and evidence reviewers. It is a bounded research tool, not an operational disaster service.

## Three-minute product walkthrough

Requires Python 3.11+; the interactive app has no third-party Python dependencies or API keys. From the repository root:

    py -3 -m evidencetrail serve --host 127.0.0.1 --port 8765

On systems without the Windows launcher, use `python` in place of `py -3`.

1. Open [Milton WHY](http://127.0.0.1:8765/why). The 11:00 UTC replay selects NOAA #8 = **100 mph** and Florida EO #215 = **51 counties**. These are different claim types from two issuer families, not independent corroboration of one fact.
2. Remove **FL-EO-24-215** in the selector: the order claim changes **51 → 35 counties**, with the replacement source named. No publisher document or database row is actually removed.
3. Select **15:00 UTC**, click **Explain WHY**, then remove **NHC-AL142024-PUBLIC-010**: **155 → 125 mph**. Removing a future/non-pivotal source at an earlier clock leaves the selected claim unchanged.
4. Choose **Strict** and click **Explain WHY**: abstention, with the missing original-availability attestation and next evidence requirement shown. This generic ledger currently cannot admit an external attestation; collecting one also requires a verifier integration.
5. Read **Evidence still needed** and expand unavailable sources. The page shows the exact result clock. A failed replay clears the previous conclusion.
6. Open [the evidence register](http://127.0.0.1:8765/proof), then [Yagi timeline](http://127.0.0.1:8765/demo) for the earlier publication/observation trap, memory audit, and source-independence challenge.

All browser calculations are **offline samples**. The Yagi capacity record is explicitly **FICTIONAL**. The Milton corpus consists of seven manually curated NOAA/Florida reference records, not a runtime government feed or authenticated original 2024 page capture. Single-source removal measures this computation's sensitivity, not real-world causation.

## Challenge it with an unseen case

On [the same WHY screen](http://127.0.0.1:8765/why), click **Try fictional warehouse**. The current claim is **25 pallets**. Removing either `STOCK-CHECK` or `STOCK-LEDGER` alone preserves 25; removing both changes it to **12**. The investigator discovers this two-source dependency by evaluating six admissible-source subsets. These two fictional records have the same issuer and do not establish independent corroboration.

Click **Create a case** to enter source records without editing JSON. Supply a title, question and aware review clock; each source declares a quantity, claim group, issuing organization, unit, publisher, reference and excerpt. Choose either an exact issue time with timezone or a printed local date plus its UTC offset. The date-only cutoff is a conservative policy bound, never a fabricated publication hour. Original government references and fictional exercises are explicitly distinguished.

Click **Preview evidence**. Read the exact entries, their admission clocks and exclusions, then confirm review and choose **Use reviewed case**. Editing any entry invalidates its preview; a late response cannot authorize newer edits. Hashes/pins generated from these entries check local consistency only. Neither the source URL nor the excerpt's meaning is independently verified. The question describes the task; typed claim rules define the computation.

Choose **Add evidence** to review a new source. The original records and pins remain intact. Before and after are recomputed at the same captured clock and policy, with changed claims/citations and executed checks visible. In the actual fictional browser regression, a new admissible record changes **74 → 92 pallets**; a future record preserves 92; a naive clock is refused. A conflicting latest record causes abstention. This is an operator evidence update, **not autonomous collection or a SQL/model request**.

**Next evidence check** offers claim-specific missing-evidence guidance, **Download evidence request** exports a plan for an analyst, and **Download investigation record** preserves the case, current investigation and latest operator update locally. The plan is not an executed query; the record is not a digital signature or participant attestation.

Advanced users can still **Download case pack** and use **Import a case JSON**. Schema `evidencetrail.case.v1` contains case identity/title/question, aware `as_of_utc`, `rules`, `sources` and separate `pins`. The downloadable example is the schema reference. When editing JSON directly, explicitly update the expected value and excerpt SHA-256 as appropriate; the import route never silently regenerates existing pins.

Use an arbitrary aware ISO clock, choose a search depth of 1–3, and test a joint withdrawal. Depth 1 explicitly reports **at least 2**, without claiming that larger groups were searched. Strict mode abstains. Tampering with a future source is refused before withdrawal analysis; neither hiding nor withdrawing it repairs the original case. Imports are bounded to 12 sources, 12 rules and 60,000 UTF-8 bytes. No URL fetching, credentials, model requests or imported-case persistence occurs through this HTTP route.

The same computation is available from the repository root:

    py -3 run_case_investigation.py --example warehouse --withdraw STOCK-CHECK STOCK-LEDGER --receipt acceptance/logs/my-investigation.json
    py -3 run_case_investigation.py --case my.case.json --search-depth 3 --receipt acceptance/logs/my-import.json

For an explicitly opted-in local Nightshift proposal, add `--local-nightshift` and set
`METERLESS_RUNTIME_TOKEN` in the process environment. The CLI requests only
`meterless/local`, checks the returned claim key, values and source IDs against
the deterministic investigation, and labels the prose as unverified. A failed
Runtime request leaves the verdict intact. On 26 Oct the full-case fictional
warehouse request completed and the returned proposal structure passed; the
prose is still unverified and the self-reported local route is not independent
vendor attestation. An earlier attempt returned HTTP 400 while the lane was
parked for VRAM. Neither run changes the deterministic verdict. A separate recorded browser request was rejected by the shape guard and appears in the current LiveUI cut; it does not demonstrate accepted model prose.

Receipt overwrite is refused. An optional `--local-zetaris --approve-local-zetaris` CLI source reads the two fixed loopback tables using existing local configuration, checks returned rows against curated metadata, and discloses completed SQL separately from model calls. It has no fixture fallback. This option is separate from the offline browser workflow and is not a Nightshift integration.

## Reproduce the checks

For Python acceptance + 20 chronology cases + 6 existing isolated Edge scenarios, use Windows with Node 22+ and Microsoft Edge at the path in the harness:

    py -3 run_judge_coldstart.py

The runner writes generated acceptance outputs and ignored logs in the checkout where it runs. Use a disposable clean checkout to preserve existing outputs. It strips vendor credentials and does not read `.env.local`. `--skip-edge` explicitly reports PARTIAL, not a full browser PASS.

Separate checks for WHY (including unseen file import, joint withdrawal, fractional clocks, delayed-response isolation and failed-replay cleanup) and navigation, not included in the runner's six scenarios:

    node demo/verify_why_browser.mjs
    node demo/verify_proof_register_browser.mjs

For Python-only verification:

    py -3 -m unittest discover -s tests -p 'test_*.py' -q

The 14 new audit regressions cover untrusted model explanations, conflicting latest claims (including date-only records), policy digest binding and honest partial SQL receipts. They use injected transports and fictional records, never vendor execution or human participants.

The subsequent Open Case upgrade adds 25 Python regressions for arbitrary typed cases, bounded subset search, input trust and local HTTP/CLI behavior. Browser regressions import an unseen 73-pallet case through the actual file input. These automated cases are engineering evidence, not independent participant results.

The guided workbench adds 16 Python regressions plus actual Edge authoring, review/edit invalidation, same-clock evidence comparison, delayed-preview rejection and date-only form entry. It reuses the same ledger and exposes pure local `/case-draft` and `/case-evidence` endpoints. Human impact remains unmeasured; the owner chose product work first because independent volunteers are not yet available.

## What has actually run

| Evidence | Supported conclusion |
|---|---|
| Latest local judge replay, 26 Oct: 580 Python tests, 20/20 chronology, six Edge scenarios and WHY Evidence Map interaction PASS | Dirty worktree at HEAD `fff6ab8`; ignored `.env.local` and Meterless vendor were present. Runner reports no key-file read or sponsor call; this is not a clean keyless source replay. Same-machine engineering checks, not a user study |
| Guided workbench core `d99de16960cea7f321e05a41112e3b243e3350df`: fresh detached keyless checkout, 566 Python, 20 chronology, 6 original Edge scenarios PASS; separate WHY/workbench and proof-register Edge PASS | Source entry, reviewed previews, exact/date-only clocks, same-clock source additions and stale-preview isolation ran from committed source; same machine, no human impact or sponsor completion claim |
| Private source ZIP from `d99de16`: 180 selected files, zero known secret-pattern blockers; extracted workbench core's 13 tests PASS | Both new runtime assets are included and the exported authoring engine executes; six privacy-review files remain, no publication authorized |
| Open Case core `41689557aeffe12a039d2c4fd631e9b9a1757913`: fresh detached checkout, 550 Python, 20 chronology, 6 isolated Edge PASS; separate WHY/open-case and proof-register Edge checks PASS | Keyless committed-source replay, including real file import, joint withdrawal, fractional source-clock boundaries and overlapping-load isolation; same computer, not human validation |
| Private source ZIP from `4168955`: 176 selected files, zero known secret-pattern blockers; extracted open-case CLI PASS | The exported upgrade runs offline; six files still require privacy review and publication remains unauthorized |
| Fresh detached baseline `656088d0`: 510 Python, 20 chronology, 6 isolated Edge PASS | Clean, keyless offline reproducibility; same computer, not external human validation |
| Audited core `c1d81ab`: 524 Python PASS; local WHY SQL replay PASS | Implemented evidence gates; two completed authenticated loopback Zetaris SELECTs consumed 4 NOAA + 3 Florida rows |
| One earlier NVIDIA direct Lightning completion, documented in note 99 | One exact-model vendor response; predates the generic ledger/WHY; does not prove Nightshift or all free-text semantics |
| Prior official TypeScript H-MEM processing | Separate local engine integration; the keyless runner uses a Python fallback, not the official engine |
| Nightshift EvidenceTrail adapter completion, 25 Oct | **1 verified local request**: `meterless/auto` reached Llama 3.2 1B on a ready local lane; matched Nightshift receipt `rcpt_req_io484m5c`. This is an adapter probe, not an end-to-end browser verdict or organizer acceptance. |
| Nightshift full-case CLI, 26 Oct | **1 local chat request; proposal structure accepted** for a fictional warehouse case; deterministic value remained 12. Runtime self-reported `local-runtime/llama-3.2-1b-instruct`; prose semantics and route identity are unverified. No organizer acceptance. |
| Nightshift browser request, 26 Oct | Genuine opt-in browser request shown in the current 2:03 demo; prose rejected by output-shape guard and deterministic result retained | Separate from CLI run; fictional/offline case; route self-reported, prose rejected, no organizer acceptance |
| Independent human analyst study | **n = 0** |

The preceding audit's verification and score baseline are in [the audit verification table](PRIZE_AUDIT_2026-10-24.md#verification). The Open Case row above records the subsequent upgrade; that historical numeric score has not been recalibrated.

## Competition admission remains blocked by evidence

Deadline: **27 October 2026 23:45 UTC = 28 October 06:45 Vietnam time**. The [public event rules](https://hackathon.genai.works/event/open-agent-hackathon-2026#rules) require Zetaris and Meterless and make Cursor optional; they do not explicitly specify Nightshift as the primary route. A dated authenticated HackOS guide observed on 24 October appeared to require Nightshift as primary and a real app request in the demo. The authenticated form has not been rechecked, so eligibility remains unresolved. **No organizer waiver or eligibility clearance is established.**

Source publication, final video/deck and HackOS submission need owner authorization. Nothing in this walkthrough performs those actions or calls a paid model.
