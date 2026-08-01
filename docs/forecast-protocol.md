# Forecast protocol

1. Freeze an explicit UTC `as_of` and rule snapshot.
2. Validate tournament manifest, roster intervals and data coverage.
3. Train only on information publicly available by `as_of`, using rolling time splits.
4. Calibrate series probabilities and compare with 50% and Elo baselines.
5. Run joint tournament simulations with a fixed seed.
6. Optimize three coherent submissions: expected points, top-10 proxy and top-100 proxy.
7. Persist the full run and execute the audit before labeling any output publishable.

The UI may explain model output but may not replace it with an LLM opinion.
