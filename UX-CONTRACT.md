# EvidenceTrail UI contract

The local API and pure case modules own business behavior. This file records its UI consequences, not new evidence policy.

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Select/Listbox | Native HTML select, shared `demo/ui.css` | This contract | Platform popup and keyboard | `demo/verify_why_browser.mjs` |
| Date | Typed exact ISO instant; native date for printed day | `evidencetrail/case_workbench.py` | Timezone required; date-only plus explicit offset | Same browser suite |
| Form | `demo/case-workbench.js`, source-row template | `case_workbench.py` refusal codes | Create / append / reviewed preview | Same browser suite |
| Scrollbar | `demo/ui.css` | DESIGN.md | Document and table overflow | Same browser suite |
| Feedback | Existing inline live regions | `demo/why.html` controller | Pending / error / result / abstain | Same browser suite |
| Case lifecycle | Local controller and API | `case_investigator.py`, `api.py` | Preview then adopt; JSON import/export | Same browser suite |

## Business sources and UI consequences

- Permission/data lifecycle: `api.py` exposes bounded local JSON routes. No source URL fetch, SQL, model or external publication is triggered by a browser action. No browser storage or telemetry is introduced.
- Evidence policy: `why_counterfactual.py` and `case_investigator.py` own chronology, pin checks, conflicts and abstention. UI never interprets a pin as external authentication.
- Draft lifecycle: `case_workbench.py` preserves old source records and compares before/after at the same clock/policy. Input edits invalidate review. Cancel hides the draft; reopening the same editor restores its inputs until another case is adopted or the page is left. Page departure with an open edited draft gets a native browser unload guard (not a product dialog).
- Deletion: removal here is a conditional simulation or removal of an unadopted source entry. No publisher record is deleted. There is no account, billing, production permission or remote CRUD workflow.
- Research/legal wording: existing caveats in `demo/why.html` and `demo/proof.html` remain visible; redesign does not change their scope.

## Flow ledger

Create → source entries → local preview → operator reviews → adopt. Append → captured current clock and policy → local preview → review → adopt comparison. Errors retain inputs, link their field, focus the first visible invalid field and allow retry. Cancel returns focus to its opener and retains separate create/append drafts until the active case is replaced. A restored append draft captures the current boundary again and requires fresh preview/review. Textareas grow on input and container reflow, with scroll overflow as a safe fallback. Latest request wins; stale responses cannot repopulate results. Existing browser tests exercise import, strict abstention, source withdrawal, future evidence, invalid dates, preview races and server failure.

Navigation uses ordinary named route links and section anchors. All three routes expose current-page state. No draft content appears in a URL. All controls and exact timestamps remain reachable on a phone and with a keyboard. No full WCAG or human usability certification is claimed.
