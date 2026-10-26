# EvidenceTrail — prospective analyst pilot (not an Impact claim)

**Study status as of 24 October 2026:** implementation ready; **0 independent participants**. The eight prepared HTML respondent packets are local and ignored by Git. There is no recruitment, human result, published causal effect, organizer approval, or external sponsor inference in this kit.

## Preregistered question and design

Question: *Does a chronology-assisted evidence view improve how accurately an independent analyst identifies admissible historical claims and their pivotal citations compared with a transparent source-card reference view?*

A within-person two-task, counterbalanced **interface pilot**, not an operational disaster study. Historical Hurricane Milton 2024 public-source **metadata**, curated from four NOAA/NHC bulletin references and three Florida Governor references, is shown in both conditions. No personal identifying information is collected. The product never recommends real-world evacuation actions.

- **REFERENCE_ONLY:** all seven source cards with the same printed issue clocks, Florida local calendar dates, reported numerical claims and official URLs. Participants must apply the written admission rule themselves. This is a **fair reference-document condition**, not the earlier deliberately incorrect date-blind algorithmic baseline.
- **CHRONOLOGY_ASSISTED:** identical seven source cards *plus* EvidenceTrail's "admitted/not admitted" timeline markers. It does **not** supply the numeric gold answer explicitly, although the marker makes it easier to find.
- Each participant sees one case per condition; the eight repeating assignments counterbalance task identity, condition and presentation order. Four as-of cases: 2024-10-07 03:59 UTC, 04:00, 11:00 and 15:00. Slot 0 through 7 should be assigned in sequence to volunteers. Different tasks appear in the two conditions per participant; practice/case-difficulty bias can still affect results.
- Both conditions explicitly state the printed Florida calendar date is admitted only after its entire local EDT (UTC−04:00) date, and both disclaim authenticated original first-publication. Participants can plainly notice the assistance markers, so this is **not participant-blinded or double-blind**. The hidden gold is kept off respondent pages, and scoring uses a separate private local registry.
- Adult (18+) volunteers not on the EvidenceTrail build team, ideally with evidence-review or research experience, opt in and can withdraw without saving anything. Invite **eight volunteers as a minimum feasibility pilot**, not a statistical sample-size calculation. Report refusals, withdrawals, deviations, duplicate sessions and missing returned packets without hiding them.

**Co-primary descriptive measures** per task: numeric correctness (0–2: NHC mph and Florida emergency-order counties) and exact pivotal source citation IDs (0/1). Secondary: number of future/irrelevant cited IDs and browser-measured task duration (self-reported, not independently validated). Source IDs of separate Florida/NHC claim types cannot be treated as interchangeable. Report per-condition statistics and within-person paired deltas with case/order caveats; **no inferential significance or causal impact claim** from a tiny opportunistic pilot.

## Operator instructions (Windows / MAIN-PC)

Repo: `<local-worktree>`.

Already prepared, **never send the private registry folder**:
- Respondent-only HTML: `acceptance\logs\analyst-study\participants\slot-0.html` through `slot-7.html`.
- Researcher-only hidden registry: `acceptance\logs\analyst-study\private-registry\<random-session-token>.json`. This is NOT the answer key but binds each packet to its issued tasks. Keep it local and restrict access.
- Voluntary responses: `acceptance\logs\analyst-study\responses\` (currently **empty**).
- Zero-human baseline receipt: `acceptance\logs\analyst-study\initial-zero-human-score.json` (status `NO_RESPONSES`, verified independent human n=0).

Give **one HTML file only** to each consenting volunteer, in slot order. They open it locally in Edge and complete two tasks; it needs no localhost server, cloud login, external JavaScript, API key or network access. They then manually return the downloaded `evidencetrail-response-<token>.json` if they wish. Keep all returned files off Git, in the ignored responses directory. Record volunteer independence/consent in a separate offline observer log without names or contact details; the exported answer JSON itself is **not evidence that a human actually participated**.

To prepare an additional slot with a NEW filename and the same PRIVATE registry:

```powershell
py -3 -m evidencetrail.blind_study prepare --slot 8 --out acceptance/logs/analyst-study/participants/slot-8.html --registry acceptance/logs/analyst-study/private-registry
```

After **actual** returned files exist, run (choose a never-used receipt path):

```powershell
py -3 -m evidencetrail.blind_study score --responses acceptance/logs/analyst-study/responses --packets acceptance/logs/analyst-study/private-registry --output acceptance/logs/analyst-study/volunteer-descriptives-001.json
```

The scorer validates the researcher's disk packet digest, one-use anonymous session ID, assignment order, two answers, exact citations and bounded browser timing; refuses malformed, duplicate or mismatched packets; reports a descriptive score for each condition and paired within-person contrast. The scorer **always** reports `independently_verified_human_participants=0` and `human_impact_claim_authorized=false` because file integrity alone does not attest a human. Any later participant impact claim requires distinct genuine observer attestations and careful documentation. Never describe automatically generated JSON as a human response.

## Threats to validity and ethics

The source cards use **curated summaries and printed clocks**, not authenticated 2024 original HTML bytes. The gold answers are developer-authored from source references; reviewers should independently inspect the references before making any externally validated factual claim. Florida's date-only end-of-day admission is a deliberately conservative study policy, **not verified first publication**. Two trials per person are susceptible to learning/practice effects and case complexity differences. Self-reported browser timing can be edited and may include interruptions. A session token and JSON checksum are **local consistency checks**, not digital signatures or remote identity proof. No network evidence is collected, and no model or sponsor endpoint is accessed.

Do not ask for names, emails, disaster exposure, current location, medical information, IP addresses or browser fingerprints. Share only the participant HTML, never a key file, gold rubric, researcher registry or past volunteer responses. Keep volunteer answer files local, share only aggregate descriptors and delete them when the study is complete (recommended within 30 days), unless participants explicitly agree otherwise. A user may withdraw by not returning the output file.

## Machine-executed QA ≠ human evaluation

- `py -3 -m unittest tests.test_blind_study -q` exercises schema, counterbalancing, safe generation and simulated responses.
- `node studies/verify_participant_browser.mjs` uses isolated real Edge sessions for two programmatic consent/task/export flows. These robot responses are immediately **deleted** and never counted in an Impact denominator.
- Initial no-response scoring exits normally and reports **n=0**. Until independent volunteers genuinely participate, **EvidenceTrail has no measured human impact**.

Do not submit or promote an Impact statistic generated from fixtures. The prize deadline does not justify substituting a robot or project developer as an independent participant.
