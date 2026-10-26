# EvidenceTrail

EvidenceTrail helps incident researchers review which dated sources support a typed claim, what evidence is unavailable, and how a result changes when a source is removed. It is a local research tool, not an operational incident or weather service.

## Run the keyless demo

Python 3.11+ is sufficient for the sample. From the repository root:

```powershell
py -3 -m evidencetrail serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/why`.

1. Review the Evidence Map: NOAA #8 supports the 100 mph claim; Florida EO #215 supports the 51-county claim at the selected clock.
2. Preview removing Florida EO #215. The simulated claim changes from 51 to 35 counties and names the replacement source.
3. Switch to 15:00 UTC and test the later NOAA advisory; removing it changes 155 to 125 mph.
4. Select Strict policy to see an abstention when original-availability evidence is missing.
5. Try the fictional warehouse case. Removing either record alone preserves 25 pallets; removing both changes the result to 12.

The demo does not fetch source URLs or call a model by default. Source pins check declared consistency; they do not independently authenticate publisher bytes or prove semantic entailment. Source removal is a controlled computation, not a real-world causal finding. The warehouse case is fictional.

## Architecture and sponsor boundaries

Typed evidence rules and deterministic checks control claim selection, source admission and abstention. Optional model proposals cannot change the computed result and may be rejected by deterministic validation.

The project has recorded separate executions involving Zetaris, the official Meterless H-MEM reference, direct NVIDIA, and local Nightshift. They are not one combined sponsor pipeline. The Nightshift CLI proposal passed structural checks only; its prose and self-reported route are unverified. A separate browser request failed shape validation and retained the deterministic result. Sponsor eligibility remains unresolved.

## Engineering evidence and limits

The latest 26 Oct local judge replay passed 580 Python tests, 20 chronology checks, six Edge scenarios and the WHY Evidence Map interaction. It ran on a dirty worktree with `.env.local` and the Meterless vendor checkout present; the runner reports no key-file read or sponsor request, but this is not a clean keyless replay. These are same-machine engineering checks, not independent validation. Analyst impact is unmeasured (n=0).

Historical source availability is not independently proved. Research and planning began before the build window; third-party H-MEM reference code and public government material are disclosed in the source archive.

## Download the reviewed source

The public repository carries the exact 192-file allowlisted source candidate as [a ZIP archive](submission/EvidenceTrail_Track02_SOURCE_REVIEW_20261026.zip). The archive includes the submission packet, public-facing README, claim ledger, tests, and implementation. It excludes local environment files, vendor checkouts, caches, raw receipts, and acceptance logs.

## Reproduce checks

```powershell
py -3 -m unittest discover -s tests -p 'test_*.py' -q
node demo/verify_why_browser.mjs
node demo/verify_proof_register_browser.mjs
```

The full cold-acceptance runner writes generated files; run it in a disposable checkout. Browser verification currently targets the configured Windows Edge installation. No cross-platform or complete accessibility certification is claimed.

See [LICENSE](LICENSE) and review the disclosed third-party components before redistribution.

