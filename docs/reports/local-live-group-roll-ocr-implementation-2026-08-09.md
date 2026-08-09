# Local live Group Roll OCR implementation report

Date: 2026-08-09

## Outcome

The local `Group Roll 实时顾问` now has an optional live Dota-window observer. The original dropdown
form remains the default and works with OCR disabled. When the observer confirms a complete stable
screen, it fills the local form and automatically calls the existing current-screen recommendation
and Title calculation. It never applies an operation inside Dota.

## Implemented boundary

- Read-only Windows capture of the window titled `Dota 2`.
- Two-frame stability gate and meaningful-change deduplication before OCR.
- Finite English/Chinese vocabulary tied to the current client snapshot.
- Explicit language contract `("en", "zh-Hans")`: English is primary and Simplified Chinese is the
  supported fallback; both cover roles, Stats, qualities, Traits, offers and remaining Rolls.
- Per-field evidence and confidence for 31 required fields.
- Legal color/Stat, duplicate-Stat, distinct-offer and full-state validation.
- Partial fill only for confirmed fields; no automatic calculation from an incomplete observation.
- Latest target screenshot and JSON only, under the ignored local cache; no image history.
- Opt-in Streamlit toggle, live status, missing-field list, automatic fill and recalculation.
- The live controls exist only on local Windows. Linux or hosted Streamlit keeps the original manual
  form and does not expose a nonfunctional capture toggle.

## Acceptance evidence

- Structured complete fixture creates a valid state and maps all 31 advisor widgets.
- Complete English and Simplified Chinese token screens both create the same legal state in regression
  tests.
- A rendered 2560×1440 complete screen passed the real RapidOCR engine end to end: 31/31 fields,
  legal state, offer `(9, 23, 17)`, and 37 remaining Rolls. Downscaling the same sample to 1920 lost
  one small `Tier I` label, so the production profile keeps a 2560-pixel OCR width (about six seconds
  in the local smoke run).
- A separate 2560×1440 Simplified Chinese pixel screen also passed RapidOCR end to end with 31/31
  fields and the same legal state, rather than relying only on pre-tokenised Chinese parser input.
- Weak, conflicting or missing evidence produces `incomplete` and blocks automatic calculation.
- A real 2560×1440 Dota match screen produced `not_target` with zero advisor fields.
- Starting the browser toggle while that match screen was present displayed “当前不是完整的 Group
  Roll 页面；继续监视” and left the manual form usable.
- Turning monitoring off displayed the stopped state and preserved the form.
- A lifecycle regression test confirms that a slow OCR pass cannot overwrite the stopped state or
  create a second worker after a rapid off/on sequence.
- Final project suite: 184 tests collected, 183 passed and one pre-existing intentional skip; Ruff,
  JSON parsing, offer-profile parity and `git diff --check` passed. The only warning is the existing
  NumPy generic-timedelta deprecation in `forecasting.py`.

## Known validation gap

The live process was not on the Group Roll screen during implementation, so exact OCR recall against
one real current-client Roll screen remains the final calibration check. The client source layout,
localisations and rule snapshot were inspected, and synthetic structured coverage passes, but this
does not replace a real-screen acceptance sample. Until that check passes, a complete-looking OCR
result still receives the same legality and confidence gates, and the user can keep OCR disabled or
correct the form manually.

## Operations and cleanup decision

The OCR profile covers every positive-weight operation in the current Group offer pool. Internal
operation IDs 1–8 have zero Roll weight and are deliberately not treated as visible random offers.
The older screenshot-upload OCR is retained because it is a separate manual draft workflow, not a
superseded production path.
