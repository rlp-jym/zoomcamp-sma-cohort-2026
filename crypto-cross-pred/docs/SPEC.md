# Cross-Sectional Return Prediction for Crypto Futures — Spec

**Title:** Cross-Sectional Return Prediction for Crypto Futures
**Course:** DataTalksClub — Stock Markets Analytics Zoomcamp (2026 cohort)
**Status:** Specification / design locked, implementation not started
**Related docs:** [project-criteria.md](../project-criteria.md) · [DECISIONS.md](./DECISIONS.md) · [TASKS.md](./TASKS.md) · [AGENTS.md](../AGENTS.md)

---

## 1. Problem statement and objective

Most course projects predict weekly returns for a handful of large-cap US stocks using
Yahoo Finance. This project instead asks:

> Can hourly derivatives-market data (funding rates, open interest, long/short ratios,
> liquidations) predict the **relative** 24-hour performance of crypto perpetual futures,
> well enough that a market-neutral long-short strategy survives realistic trading costs?

**Objective.** Not a profitable strategy. The goal is a **reusable research template** for
cross-sectional return prediction, with the crypto case as its first fully documented run.
Profitability is a reported outcome, not a target (D-22).

The system:

1. Downloads hourly market + derivatives data for 150–250 Binance USDⓈ-M perpetuals,
   plus daily macro context from FRED.
2. Builds a single unified feature table with 60+ engineered features.
3. Trains a regression model (cross-sectional excess return) and a classifier
   (probability of landing in the top quintile).
4. Simulates three progressively sophisticated trading strategies with realistic costs.
5. Runs daily via CI, publishes predictions to a public dashboard, and alerts via Telegram.

**What "template" means concretely.** The only market-specific component is the data
adapter (source → unified schema). Features, labels, validation, simulation, reporting and
automation read only the unified schema and are driven by `config.yaml`. Reusing the
pipeline for another market means writing one adapter and editing one config file (§9.1).

**Value of the solution:**

- A peer can open the Streamlit app and see today's ranked picks, backtest equity curves,
  and recent out-of-sample performance without running anything locally.
- A reader can lift the protocol — splits, sealed holdout, experiment log, verdict states —
  for their own project, whatever the market.
- A negative result is a complete deliverable: it removes a hypothesis with evidence
  instead of leaving it open.

---

## 2. Target score and rubric mapping

| # | Criterion | Pts | How this project earns it |
|---|---|---|---|
| 1 | Problem description | 4 | README with context + goal; new problem definition (hourly, cross-sectional, crypto perps, derivatives features); SOTA step-by-step writeup with findings |
| 2 | Data sources | 4 | Lecture source (FRED macro) + new source (Binance USDⓈ-M, Fear & Greed); 20+ new features with descriptions; >1M records (150+ symbols × hourly × 1yr+) |
| 3 | Transformations + EDA | 3 | Unified dataframe, explicit `TO_PREDICT` / `NUMERIC` / `DUMMIES` sets; 5+ derived feature groups; correlation + IC analysis, per-symbol breakdown |
| 4 | Modeling | 5 | RandomForest (lecture model) + Ridge (second) + XGBoost (new); Optuna tuning; probability-threshold decision rules |
| 5 | Trading simulation | 8 | sim0 rule baseline, sim1 vector long-only, sim2 vector long-short, sim3 exact iterative with risk management; benchmarks + CAGR/Sharpe/MaxDD/rolling returns; per-ticker and per-month error analysis |
| 6 | Automation | 5 | Notebooks exported to `.py`, one orchestration notebook; `uv` deps; GitHub Actions cron; file-mode vs download-mode; incremental loading to HF Datasets |
| 7 | Bonus | 7 | Modular code, Binance testnet orders, Telegram monitoring, Docker, cloud deploy, subjective |

**Realistic target: 30–34 / 36.** Every bolded minimum is covered.

---

## 3. Research protocol

The rationale behind these rules is recorded in [DECISIONS.md](./DECISIONS.md) (D-22…D-32).
This section is normative.

### 3.1 Data splits

```
2021-01 ──────────────────────── 2025-10 │ 2025-11 ── 2026-10
              dev period                   │   sealed holdout
```

- **Dev period (2021-01 → 2025-10):** purged walk-forward, monthly retrain (§6). Iterate here.
- **Sealed holdout (2025-11 → 2026-10):** evaluated exactly once, at the end. No feature,
  hyperparameter, or decision threshold is chosen using it.
- **"dev OOS"** = the aggregate of the walk-forward out-of-sample months.
  **"Test"** is reserved for the sealed holdout (D-31).

### 3.2 Iteration policy

- Every run has a stated reason: a hypothesis, a bug fix, a cost-model correction, a new
  feature family. "Try something and see" is not a reason.
- Every run is logged (§3.3).
- **Two-strike rule:** an idea that fails twice is dropped with a one-line reason (D-28).
- Tuning toward a specific number is out of policy — including toward profitability.

### 3.3 Experiment log

`experiments.md`, append-only, one row per run:

```
run_id | date | change | reason | dev OOS metric | verdict | keep/drop
```

The log is part of the deliverable: it is the evidence that iteration was method, not
fishing.

### 3.4 Plausibility guardrails

Expected ranges for 24h cross-sectional crypto prediction:

| Metric | Plausible | Investigate |
|---|---|---|
| Rank IC (dev OOS) | 0.01 – 0.05 | > 0.10 |
| Net Sharpe (sim3) | 0 – 2 | > 3 |
| Precision@top-decile | 0.20 – 0.30 | > 0.45 |

A result outside the plausible range triggers a **leakage audit first** (D-27).

### 3.5 Success criteria and stopping rule

Written into the header of `experiments.md` **before the first modelling run**:

> The derivatives-positioning hypothesis is **supported** only if the sealed holdout shows
> rank IC ≥ 0.02 with t-stat ≥ 2 **and** sim3 net Sharpe > 0 after 6 bps round-trip.
> Otherwise the verdict is **falsified** (adequate power, no effect) or **inconclusive**
> (below minimum detectable effect, or costs dominate).

Verdict states and their meaning: see [DECISIONS.md](./DECISIONS.md) §5.

**Secondary test — does the model add anything?** `sim0` is a rule-based baseline (§7). The
ML strategy is only *additive* if sim3 beats sim0 on net Sharpe. This is reported next to
the verdict but does not change it: a supported hypothesis that still loses to a simple
rule is supported, and is worth writing down.

### 3.6 Live is not a free test set

Once the app runs on live data, live performance is for **reporting and alerting**. The
retrain schedule is fixed (monthly walk-forward). Reacting to live metrics by hand would
turn live data into another validation set — the same selection-overfitting problem, with
capital attached (D-29).

---

## 4. Data design

### 4.1 Sources

| Source | What | Access | Notes |
|---|---|---|---|
| Binance USDⓈ-M REST (`fapi.binance.com`) | klines, funding rate, open interest, long/short ratio, taker volume, liquidations | Free, no key for market data | 1,500-bar pagination limit; some endpoints need key |
| Binance public data dumps (`data.binance.vision`) | Monthly ZIP archives of klines / funding / OI | Free, no key, no geo-block | Primary backfill path; much faster than API pagination |
| alternative.me | Crypto Fear & Greed index | Free, no key | Daily, forward-fill to hourly |
| FRED (`fred.stlouisfed.org`) | `VIXCLS` (VIX), `DGS10` (10Y yield), `DFF` (policy rate), `DTWEXBGS` (dollar), `BAMLH0A0HYM2` (high-yield OAS) | Free, no key via `pandas-datareader` | Daily, weekday-only; forward-fill with a **1-day lag** |

**Backfill strategy:** bulk dumps for history → REST API for the incremental tail.
This also derisks regional API blocking, since the dumps are plain HTTPS on a CDN.

### 4.2 Unified schema (one row = one symbol × one hour)

```
symbol            str       contract symbol, e.g. BTCUSDT
ts                datetime  UTC, bar open time, hourly
open high low close volume      float   from klines
quote_volume      float
trades            int
taker_buy_volume  float
taker_buy_quote_volume float
funding_rate      float     current funding rate (8h cadence, forward-filled)
open_interest     float
ls_ratio_account  float     long/short account ratio
ls_ratio_position float     long/short position ratio
liq_long_volume   float     liquidations, long side
liq_short_volume  float     liquidations, short side
fng               float     Fear & Greed, 0-100
vix               float     CBOE VIX close (lagged 1 day)
dgs10             float     10Y Treasury yield, % (lagged 1 day)
dff               float     Effective fed funds rate, % (lagged 1 day)
dxy               float     Broad dollar index (lagged 1 day)
hy_oas            float     ICE BofA US High Yield option-adjusted spread, % (lagged 1 day)
```

Primary key: `(symbol, ts)`. Stored as partitioned parquet on HF Datasets.

### 4.3 Feature families (60+ features)

**Price / volume (per symbol)**
`ret_1h, ret_4h, ret_24h, ret_7d, log_volume, volume_z_24h, volume_ratio_24h_7d,
taker_buy_ratio, taker_buy_ratio_ma_24h, trades_z_24h, avg_trade_size,
hl_range, parkinson_vol_24h, realized_vol_24h, vol_ratio_24h_7d,
close_to_high_24h, close_to_low_24h, dist_high_30d, dist_low_30d,
rsi_14, macd_hist, ma_ratio_24h, ma_ratio_7d, skew_24h, kurt_24h, autocorr_1h_24h`

**Derivatives**
`funding_rate, funding_ma_8, funding_z_7d, funding_cum_24h,
oi_change_1h, oi_change_24h, oi_z_7d, oi_to_volume,
ls_ratio_account, ls_ratio_position, ls_ratio_z_7d,
liq_long_vol_24h, liq_short_vol_24h, liq_imbalance, liq_z_7d`

**Cross-sectional (computed per timestamp across the universe)**
`cs_rank_ret_24h, cs_rank_vol_24h, cs_rank_funding, cs_rank_oi_change,
cs_z_ret_24h, cs_demeaned_ret_24h, beta_to_btc_7d, corr_to_btc_7d, resid_mom_24h`

**Market-wide**
`btc_ret_1h, btc_ret_24h, btc_realized_vol_24h, market_breadth,
market_dispersion, avg_funding_all, fng, fng_change_7d, fng_z_30d`

**Macro regime (FRED, daily, lagged 1 day)**
`vix_level, vix_z_30d, vix_change_1d, yield_10y, yield_change_5d,
term_spread (DGS10 - DFF), dxy_ret_5d,
hy_oas_level, hy_oas_z_30d, hy_oas_change_5d,
macro_risk_off` (dummy: VIX above its 30d median **and** HY OAS widening)

**Dummies / categorical**
`symbol` (target-encoded or top-N + other), `hour_of_day` (sin/cos or one-hot),
`day_of_week`, `is_weekend`, `vol_regime` (low/mid/high terciles),
`funding_regime` (negative/neutral/high)

> Rubric needs 20+ new features; this list is ~60. Only features that survive
> correlation/importance screening get shipped — document what was dropped and why.

### 4.4 Labels

Computed at time `t`, using only data up to `t` for features and data after `t` for labels:

```
fwd_ret_24h        = close[t+24] / close[t] - 1
cs_excess_ret_24h  = fwd_ret_24h - mean_across_universe(fwd_ret_24h at t+24)
TO_PREDICT_REG     = cs_excess_ret_24h
TO_PREDICT_CLF     = 1 if cs_excess_ret_24h >= cross_sectional_p80(t+24) else 0
```

The 80th-percentile threshold is computed per timestamp, so the class balance is
stable at ~20% positives by construction. Last 24 rows per symbol are dropped.

---

## 5. Modeling

| Model | Role | Notes |
|---|---|---|
| Ridge | Baseline / sanity floor | Standardized numerics, one-hot dummies; establishes the IC a linear model can reach |
| RandomForest | Lecture requirement | `n_estimators` 300–800, `max_depth` tuned, `min_samples_leaf` tuned |
| XGBoost | "New model" | `hist` tree method, early stopping on the validation fold |

Each model is trained twice: once for `TO_PREDICT_REG`, once for `TO_PREDICT_CLF`.

**Tuning:** Optuna, 30–50 trials per model on the earliest validation window, objective =
mean rank IC (regression) / AUC (classification). Tuning is done **once** on a dev window,
not inside the walk-forward loop (to keep runtime sane); hyperparameters are then frozen
for all walk-forward folds. Document this choice.

**Decision rules (rubric 4.3):**
- Long when `p_top_quintile >= 0.25` and `pred_excess_return > 0`
- Short when `p_top_quintile <= 0.05` and `pred_excess_return < 0`
- Position size scales with `p_top_quintile` (conviction weighting)

---

## 6. Validation (dev period)

**Purged walk-forward, monthly retrain, 24h embargo.** This loop runs on the dev period
only; the sealed holdout (§3.1) is a single run and is never part of it.

```
for each month M in dev out-of-sample range:
    train      = all rows with ts <= start(M) - 24h
    validation = rows in [start(M), end(M)]     # early stopping only
    dev_oos    = next month
    purge      = drop the 24h immediately before each boundary
    retrain on expanding window
```

`dev_oos` months are not a test set — they are looked at repeatedly while iterating (§3.2).

**Why:** labels span 24 hours, so rows within 24h of a split boundary leak the future
into training. Purging + embargo is the standard fix (López de Prado).

**Metrics:** Spearman IC, rank IC, IC decay over horizon, decile spread, precision@top-decile,
AUC, RMSE, and per-symbol / per-month breakdowns.

**Leakage checklist (enforced in review):**
- All features computed from data `<= t`; no `shift(-n)` except in label code
- Cross-sectional stats computed within the same timestamp only
- Scaling/imputation fitted on train fold only
- Symbol target-encoding computed inside the fold, never globally
- Funding rates forward-filled, never backward-filled
- Macro series lagged 1 day before joining; no same-day FRED value at an hourly timestamp
- Decision thresholds chosen on dev only, never on the holdout (D-32)

---

## 7. Trading simulation

Daily rebalance at 00:00 UTC. Costs: **4 bps taker per side**, plus funding paid/received
every 8h on open positions, plus a configurable slippage assumption (default 2 bps).

| Sim | Type | Description |
|---|---|---|
| `sim0_` | Vectorized | **Rule baseline, no model.** Long the 20 most-negative funding rates, short the 20 most-positive, equal weight, daily rebalance |
| `sim1_` | Vectorized | Long-only, equal weight, top decile by predicted excess return |
| `sim2_` | Vectorized | Long top decile / short bottom decile, equal weight, dollar-neutral |
| `sim3_` | Exact (`iterrows`-style) | Reinvested capital, prob-weighted sizing, vol targeting (~15% annualized), per-position stop-loss, max concurrent positions, funding + cost accounting |

`sim0` exists to answer the question the course itself asks: does the model beat a simple
hand-written rule using the same data and the same costs? It uses only funding rates known
at decision time, and it must be built **before** sim1/sim2 so all four share one cost model
and rebalance timing.

**Benchmarks:** BTC buy-and-hold, equal-weight all-perp basket (daily rebalanced), cash (0%).

**Reported metrics:** CAGR, Sharpe, Sortino, max drawdown, Calmar, rolling 90d returns,
turnover, win rate, average holding period, exposure, per-year breakdown.

**Deep analysis (rubric 5.8):** precision by symbol, by month, by vol regime, by funding
regime; inspect the worst predictions; list concrete improvement ideas derived from findings.

---

## 8. Automation & deployment

**CLI (`src/crypto_cross_pred/cli.py`)** — one entry point per stage plus `all`:

```
download | transform | features | train | predict | simulate | notify | all
```

**Two regimes (rubric 6.4):**
- `--source hf` — pull a prebuilt dataset snapshot from HF Datasets (fast, reproducible, no refresh)
- `--source binance` — download fresh data, incremental from the last stored timestamp

**Incremental loading (rubric 6.5):** per symbol, read the max stored `ts`, fetch only the
missing range, upsert into the parquet partition, push to HF. No full rewrites.

**Cron:** GitHub Actions, daily at 00:15 UTC — download → transform → predict → simulate →
publish → notify. Public repo ⇒ unlimited free minutes.

**Deployment:** Dockerfile for local/CI parity; Streamlit Community Cloud for the public app,
reading the latest artifacts from HF Datasets.

**Bonus:** Telegram alerts (daily picks, PnL, drift warnings); Binance **testnet** order
placement (paper only, no real funds).

---

## 9. Repository layout

```
crypto-cross-pred/
├── README.md                   # problem + value
├── AGENTS.md                   # working rules (root, so agents find it)
├── .gitignore                  # includes project-criteria.md
├── experiments.md              # append-only run log (§3.3)
├── docs/
│   ├── SPEC.md                 # what the system must do (this file)
│   ├── DECISIONS.md            # why; decision log + rejected alternatives
│   └── TASKS.md                # build plan
├── pyproject.toml              # standalone uv project (see D-18)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── config/config.yaml
├── .github/workflows/pipeline.yml, ci.yml
├── src/crypto_cross_pred/
│   ├── config.py
│   ├── io/          binance.py, fred.py, huggingface.py, storage.py
│   ├── data/        download.py, transform.py, features.py, labels.py
│   ├── models/      validate.py, tuning.py, train.py, predict.py
│   ├── sim/         vector.py, exact.py, metrics.py
│   ├── report/      plots.py, telegram.py, broker.py
│   └── cli.py
├── notebooks/       01_eda.ipynb, 02_modeling.ipynb, 03_simulation.ipynb
├── app/streamlit_app.py
├── tests/
└── data/            # gitignored: raw/ interim/ processed/ artifacts/
```

### 9.1 Adapter boundary

The only permitted abstraction (D-30):

| Layer | Market-specific? |
|---|---|
| `io/` data adapter (source → unified schema §4.2) | **Yes** |
| `data/` features, labels | No |
| `models/` validation, tuning, train, predict | No |
| `sim/` simulation, metrics | No |
| `report/` plots, alerts, broker | No |
| `app/` dashboard | No |

Adding a market means one adapter plus one `config.yaml` entry. No changes to `models/` or
`sim/`. Everything downstream reads only the unified schema.

---

## 10. Contracts (do not drift)

1. **Schema** — the column set in §4.2 is the only allowed interchange format between stages.
2. **Feature sets** — `TO_PREDICT_REG`, `TO_PREDICT_CLF`, `NUMERIC`, `DUMMIES`, `CATEGORICAL`
   are exported from exactly one module and imported everywhere (notebooks included).
3. **Artifact naming** — `raw/{source}/{symbol}.parquet`,
   `processed/dataset_{YYYY-MM-DD}.parquet`, `predictions/{YYYY-MM-DD}.parquet`,
   `sim/{strategy}_{YYYY-MM-DD}.parquet`.
4. **UTC everywhere.** No naive timestamps cross a module boundary.

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Binance 1,500-bar pagination | Slow/incomplete backfill | Use `data.binance.vision` monthly dumps for history, REST only for the tail |
| Funding/OI history depth varies by symbol | Shorter usable date range | Filter universe by min history (e.g. ≥18 months); document excluded symbols |
| Delisted symbols → survivorship bias | Optimistic backtest | Include symbols that later delisted where data exists; state the limitation explicitly |
| Overlapping 24h labels | Leakage, inflated IC | Purged walk-forward + 24h embargo |
| Costs/funding eat the edge | Strategy looks unprofitable | Report gross and net; restrict to high-conviction trades; show cost sensitivity table |
| Binance API geo-blocking | Download fails locally | Dumps-first architecture; document the fallback |
| HF upload requires token | CI failure | `HF_TOKEN` as repo secret; public read for the app |
| Selection overfitting (analyst iterates on dev OOS) | Inflated expectations | Experiment log + two-strike rule + sealed holdout (§3) |
| Live monitoring turns into hand-tuning | Live becomes a test set | Fixed retrain schedule; alerts are reporting only (§3.6) |
| FRED revisions (current vintage ≠ live vintage) | Mild lookahead in the backtest | Lag 1 day; state the limitation; ALFRED vintages noted as out of scope |
| FRED weekday-only, crypto 24/7 | Weekend/holiday gaps | Forward-fill across gaps; never interpolate |
| Scope creep (LSTM, sentiment) | Unfinished project | Explicitly out of scope in §12 |

---

## 12. Out of scope

- LSTM / deep sequence models (deliberately excluded — D-09)
- News or social sentiment scraping (API rate-limit risk)
- On-chain metrics (only covers BTC/ETH, creates systematic missingness)
- Real-money trading
- US index / commodity futures
- Any paid data source or paid hosting

---

## 13. Cost constraint

Every component must remain free:

| Component | Free tier |
|---|---|
| Binance market data + dumps | Free, no key |
| alternative.me F&G | Free, no key |
| FRED macro series | Free, no key via `pandas-datareader` |
| GitHub repo + Actions | Public repo ⇒ unlimited minutes |
| Hugging Face Datasets | Free, public datasets effectively unlimited |
| Streamlit Community Cloud | Free for public apps |
| Telegram Bot API | Free |
| Binance testnet | Free, no funds |

**Reuse:** the pipeline is config-driven. Changing the horizon, universe, or cost
assumptions requires no code changes. See the "Reuse" section of the README for the
config-swap demonstration (D-30).
