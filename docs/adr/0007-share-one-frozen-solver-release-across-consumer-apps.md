# Share one Frozen Solver Release across consumer apps

The public manual app and the Windows local-OCR app will remain in one repository and consume the
same immutable Frozen Solver Release. Maintainer builds may use the governed raw, processed and run
evidence, but consumer runtimes may only validate and read the tracked release; a missing or invalid
release fails closed instead of downloading data or rebuilding locally. This avoids two drifting
solvers and keeps the 188 GB evidence archive outside Git while preserving identical advice for an
identical confirmed screen state.

## Considered Options

- Separate repositories were rejected because the meaningful boundary is build-time evidence versus
  consumer runtime, not manual input versus OCR input.
- Shipping processed data or reconstructing on first run was rejected because it is unnecessarily
  large, slow and capable of producing machine-dependent results.

## Consequences

Both consumer entrypoints must pass clean-clone tests without `data/` or `artifacts/`. OCR remains a
Windows-only input adapter and may cache user screenshots locally, but it cannot carry a separate Rule
snapshot or solver context. Updating governed evidence requires publishing a new content-addressed
release and moving the reviewed current pointer.
