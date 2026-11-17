# Discover gate: prohibited venture stopped by the code safety screen (scenario B)

- Idea (scripted demo input): "An app that gives university students personalised crypto investment signals and guaranteed returns."
- Create project: HTTP 201
- Safety status: **BLOCK**
- Finding: financial_crypto_exclusion: The core function involves trading, lending, investing advice, tokens, or handling/managing users' money.
- Finding: income_promise_dependency: The idea sells or markets itself on a promise of income or a guaranteed outcome.
- Refine: HTTP 200; brief stored with model = `NOT_CALLED_SAFETY_BLOCK`
- Attempt to run Discover afterwards: HTTP 403 (refused)

The model is never asked about a blocked idea; the rules are code (backend/app/safety.py).
