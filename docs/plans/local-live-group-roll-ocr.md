# Local live Group Roll OCR plan

Date: 2026-08-09

## Scope boundary

Keep the existing manual Streamlit advisor as the always-available fallback. Add an optional,
Windows-local observer that captures only the Dota window, recognises the complete Group Roll
screen, fills the advisor, and reruns the existing current-screen calculation. It must never control
Dota, Steam, the mouse, the keyboard, or client memory.

## Stages and acceptance

1. Capture and observation contract
   - Minimum change: verify `dota2.exe`, resolve its exact Windows monitor handle, capture that DirectX
     display through DXcam, then apply the stable-frame gate, per-field confidence and local ignored
     cache.
   - Accept when a non-target Dota screen is rejected without changing advisor inputs.
2. Structured OCR
   - Minimum change: finite English/Chinese vocabulary from the current client snapshot; no open
     text interpretation.
   - Accept when all 31 required fields form a valid `GroupRollState`; any missing, conflicting, or
     low-confidence field blocks automatic calculation.
   - Calibration: locate the three aligned Banner headings at 1280 pixels, crop the Fantasy region,
     then upscale it to 2560 pixels for detailed OCR. This keeps full-screen Dota chrome from making
     Tier and Trait text too small.
3. Advisor integration
   - Minimum change: one opt-in, one-shot capture button and status panel above the unchanged manual
     form. Clicking arms the next stable target screen; confirmed or incomplete target OCR stops
     automatically, while minimized, covered and non-target states keep waiting and remain cancelable.
   - Accept when a confirmed observation fills all inputs and recalculates, while an incomplete
     observation fills confirmed fields only and leaves manual correction available. A single-monitor
     browser/Dota Alt+Tab flow must not terminate early or read the browser into the form.
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
