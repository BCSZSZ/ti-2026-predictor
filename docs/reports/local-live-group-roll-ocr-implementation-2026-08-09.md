# Local live Group Roll OCR implementation report

Date: 2026-08-09
Last updated: 2026-08-10

## Outcome

The local `Group Roll 实时顾问` now has an optional one-shot Dota-window observer. The original dropdown
form remains the default and works with OCR disabled. When the observer confirms a complete stable
screen, it fills the local form and automatically calls the existing current-screen recommendation
and Title calculation, then stops. It never applies an operation inside Dota.

## Implemented boundary

- Read-only Windows capture of the physical display containing the window titled `Dota 2`, after
  verifying that the owning executable is exactly `dota2.exe`.
- Exact `HMONITOR` to DXcam-output matching, with Windows Graphics Capture first and DXGI fallback;
  Chrome and the local advisor may remain on a different display.
- Two-frame stability gate and meaningful-change deduplication before OCR.
- Finite English/Chinese vocabulary tied to the current client snapshot.
- Explicit language contract `("en", "zh-Hans")`: English is primary and Simplified Chinese is the
  supported fallback; both cover roles, Stats, qualities, Traits, offers and remaining Rolls.
- Per-field evidence and confidence for 31 required fields.
- Legal color/Stat, duplicate-Stat, distinct-offer and full-state validation.
- Partial fill only for confirmed fields; no automatic calculation from an incomplete observation.
- Latest target screenshot and JSON only, under the ignored local cache; no image history.
- Opt-in Streamlit one-shot button, wait/cancel status, missing-field list, automatic fill and
  recalculation. Clicking arms the next stable target page, which supports a same-monitor Alt+Tab
  workflow without keeping a permanent watcher enabled.
- One persistent sleeping worker owns the Windows capture lifecycle. Every click wakes that same
  thread; after the request it releases capture resources on the owner thread and sleeps without
  taking screenshots.
- The live controls exist only on local Windows. Linux or hosted Streamlit keeps the original manual
  form and does not expose a nonfunctional capture button.

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
- Starting a one-shot request while a non-target Dota screen was present displayed “已经看到 Dota，
  但还不是完整的 Group Roll 页面；继续等待” and left the manual form usable.
- Canceling the pending request displayed the canceled state and preserved the form.
- A state-machine regression test confirms that minimized/covered capture and a non-target Dota page
  keep a one-shot request armed, while the next incomplete or confirmed target page stops it exactly
  once.
- A lifecycle regression test confirms that a slow OCR pass cannot overwrite the stopped state or
  create a second worker after a rapid cancel/rearm sequence. Two sequential one-shot requests also
  confirm that capture and release stay on the same worker thread.
- The user-supplied 2560×1440 full Dota client screenshot passed the real RapidOCR engine end to end:
  31/31 fields, the exact nine visible Emblems, offer `(10, 25, 28)`, and 33 remaining Rolls.
- The full-screen locator ignored the separate `SUPPORT` text in Dota's left navigation, cropped the
  three aligned Banners, enlarged the detailed region, joined `WATCHERS / TAKEN` and
  `TORMENTOR / KILLS`, and associated each Tier and Trait with the Stat card immediately above it.
- Final project suite after the one-shot interaction update: 189 tests collected, 188 passed and one
  pre-existing intentional skip. The repeated-request fix adds regression coverage for sequential
  one-shot use, immediate cancel/rearm and Streamlit widget updates; final project-suite evidence is
  recorded in the 2026-08-10 closeout below.

## Dual-monitor defect postmortem

The original `Pillow.ImageGrab(window=hwnd)` path returned a black image for Dota's DirectX surface.
The monitor-based GDI fallback could capture the desktop beneath Dota instead, so a two-display setup
appeared to monitor Chrome or never recognise a complete page. The replacement resolves the Dota
window's PID, rejects title collisions from any executable other than `dota2.exe`, obtains the exact
Windows monitor handle, and selects the DXcam output with that same handle. A minimized Dota window
now fails explicitly instead of silently reading another display.

The live hardware smoke check confirmed that the correct `dota2.exe` window is found and that a
minimized window is rejected with an actionable message. The user-provided real full-screen capture
closes the OCR-layout gap at 31/31. The user then confirmed that live capture filled the page
correctly, closing the remaining real-client execution-state check.

## Repeated-request native crash postmortem

The second one-shot request could hang and terminate the Streamlit Python process. Windows Error
Reporting identified an access violation (`0xc0000005`) in
`_winrt_windows_graphics_capture_interop.cp312-win_amd64.pyd`. The cached `LiveRollMonitor` retained
one `DotaMonitorCapturer`, but the former lifecycle created a fresh Python worker for every click.
That moved WinRT capture creation, release and later recreation across different OS threads.

An isolated probe reproduced the failure: 100 create/release cycles on one thread passed, while a
first request on one thread followed by a second request on another thread crashed consistently.
The corresponding DXGI cross-thread probe passed. OBS was not the cause: it started after the
reported hang, the original crash did not load an OBS hook DLL, and same-thread WinRT capture passed
while OBS was recording.

The minimum correction keeps the one-shot user interaction but changes the internal ownership:

- one cached worker thread is created lazily and retained;
- each click assigns a new request ID and wakes that worker;
- capture and release both occur on the same owner thread;
- after completion or cancellation, capture resources close and the worker sleeps;
- a canceled or superseded slow OCR result cannot publish over a newer request;
- Streamlit widgets omit their constructor default when Session State already supplies the OCR value,
  removing the separate nonfatal duplicate-default warning.

After the correction, two sequential one-shot requests through the real WinRT capture backend passed
in one process, using one worker object, while OBS was open. Browser QA also passed two consecutive
arm/cancel cycles and a full advisor calculation.

## 2026-08-10 closeout

The final project suite collected 192 tests: 191 passed and one pre-existing intentional skip.
Ruff, all 24 tracked JSON documents, the dependency lock, all 98 installed-package compatibility
checks and `git diff --check` passed. No new Python application crash appeared in Windows Event Log
after the two-request live WinRT acceptance run. The only test warning remains the unrelated existing
NumPy generic-timedelta deprecation in `forecasting.py`.

## Operations and cleanup decision

The OCR profile covers every positive-weight operation in the current Group offer pool. Internal
operation IDs 1–8 have zero Roll weight and are deliberately not treated as visible random offers.
The older screenshot-upload OCR is retained because it is a separate manual draft workflow, not a
superseded production path.
