# Local live Group Roll OCR plan

Date: 2026-08-09

## Scope boundary

Keep the existing manual Streamlit advisor as the always-available fallback. Add an optional,
Windows-local observer that captures only the Dota window, recognises the complete Group Roll
screen, fills the advisor, and reruns the existing current-screen calculation. It must never control
Dota, Steam, the mouse, the keyboard, or client memory.

## Stages and acceptance

1. Capture and observation contract
   - Minimum change: window capture, stable-frame gate, per-field confidence, local ignored cache.
   - Accept when a non-target Dota screen is rejected without changing advisor inputs.
2. Structured OCR
   - Minimum change: finite English/Chinese vocabulary from the current client snapshot; no open
     text interpretation.
   - Accept when all 31 required fields form a valid `GroupRollState`; any missing, conflicting, or
     low-confidence field blocks automatic calculation.
   - Calibration: retain up to 2560 pixels of source width because a 1920-pixel downscale lost a
     small Tier label in end-to-end OCR, while 2560 confirmed all 31 rendered fields.
3. Advisor integration
   - Minimum change: one opt-in toggle and status panel above the unchanged manual form.
   - Accept when a confirmed observation fills all inputs and recalculates, while an incomplete
     observation fills confirmed fields only and leaves manual correction available.
4. Project review and closeout
   - Acceptance: focused OCR/UI tests, full regression tests, lint, deterministic parse, local visual
     QA, and an explicit real-client validation status. Retain the older upload/screenshot OCR path
     because it still covers a different manual workflow.

## Reproducibility inputs

- OCR profile: `config/ocr/fantasy-group-roll-screen-v1.json`
- Client build: `6891:10893022`
- Rule snapshot SHA-256: `a6265cd07001e2a7710f23622f3bbe855b32d61445f17f4c941578c53a3275dc`
- Every observation records UTC capture time, image SHA-256, viewport, profile ID, per-field evidence,
  confidence, status, and a semantic observation hash.
