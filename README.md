# GOOGL_AI: Options Scalping Agent

An automated options trading agent utilizing real-time Schwab data to map Gamma Exposure (GEX) topography, classify market regimes, and construct high-expectancy defined-risk vertical spreads.

## Engineering Roadmap: Production Readiness

### Phase 1: Core Foundation & Data Sanitization
* **Clean `RegimeState` Model:** Remove duplicate `primary_pin_strike` and `volatility_wall_strike` declarations. Convert `is_tradeable` to a standard field or pure property to prevent conflicts, and add `PINNED_BEARISH` to the literal type array[cite: 5].
* **Date Handling:** Standardize Date to Expiry (DTE) calculations using `date.today()` instead of relying on delayed or stale quote timestamps to prevent negative DTE logic errors[cite: 5].
* **Liquidity Gating:** Update the minimum liquidity check in `classify_regime` to count only the contracts that actively contribute to the GEX profile (`len(profile.sorted_strikes)`), rather than the raw chain length[cite: 5].

### Phase 2: Robust Structure Generation
* **Dynamic Strike Matching:** Upgrade `structure_builder.py` to select the *nearest liquid strike* to the identified walls and flip lines, eliminating the brittle exact-match requirement that frequently fails on 0-3 DTE chains[cite: 5].
* **Adaptive Wing Width:** Replace hardcoded `$5` spread widths with dynamic targeting based on the next available strike, target delta, or target credit threshold[cite: 5].
* **Leg-Level Liquidity Filters:** Enforce strict Open Interest (OI), volume, and Bid/Ask spread width filters on the specific legs selected for construction[cite: 5].
* **Omnidirectional Breakouts:** Implement the missing bullish breakout logic (buying call debit spreads when the underlying price breaks above the gamma flip line)[cite: 5].

### Phase 3: Expectancy & Risk Integration
* **Risk/Premium Normalization:** Ensure Credit and Debit spreads uniformly calculate net premium and max risk so mathematical expectancy and R-multiples evaluate accurately across all strategies[cite: 5].
* **Portfolio Sizing:** Update `evaluate_and_rank` to return properly formatted `ScoredPlay` objects that calculate position sizing based on a strict percentage of total account risk, rather than raw expectancy rank[cite: 5].

### Phase 4: Real IV & Trade Management
* **Live IV Rank:** Replace mocked IV parameters with a rolling 1-year historical IV High/Low pulled from `yfinance` or a local cache to accurately feed the `RegimeState` classifier[cite: 5].
* **Explicit Exit Triggers:** Embed strict exit parameters into the webhook alert payload, including Time Stops (target exit time/DTE), Profit Targets (e.g., 50-70% of max credit), and Invalidation Levels (spot price breaching the GEX wall)[cite: 5].