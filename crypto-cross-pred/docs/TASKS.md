# Tasks — implementation plan

Derived from [SPEC.md](./SPEC.md) and [DECISIONS.md](./DECISIONS.md). Work top to bottom;
each phase is verifiable on its own.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done
Each task lists **Done when** = the acceptance test.

**Build order:** 0 Scaffold → 1 Data → 2 Transform → 3 EDA → 4 Models → 5 Simulation →
6 Automation → 7 Deploy → 8 Bonus → 9 Writeup

---

## Phase 0 — Scaffold

| ID | Task | Done when | Commit |
|---|---|---|---|
| P0-01 | **[DECISION] Project root.** Originally standalone `crypto-cross-pred/pyproject.toml`; **now a `uv` workspace member** with the root owning `.venv` and `uv.lock` (D-40 supersedes D-18) | Decision recorded in DECISIONS.md §3 | 5a85911 |
| P0-02 | Create `crypto-cross-pred/pyproject.toml` (`requires-python = ">=3.12"`) with groups: `core` (pandas, numpy, scikit-learn, optuna, pyarrow, duckdb, requests, pydantic-settings, pyyaml, pandas-datareader, tqdm, huggingface-hub), `dev` (ruff, pytest), `notebook` (jupyter, nbconvert, matplotlib), `app` (streamlit, plotly), `bonus` (python-telegram-bot or just requests) | `uv sync --all-packages --all-groups` succeeds; `uv.lock` committed at the repo root | 683ec82 |
| P0-03 | Create package tree `src/crypto_cross_pred/{io,data,models,sim,report}` with `__init__.py` stubs | `uv run python -c "import crypto_cross_pred"` works | 683ec82 |
| P0-04 | `config/config.yaml` + `src/crypto_cross_pred/config.py` (pydantic-settings): universe filters, date range, horizon, thresholds, cost bps, paths, HF repo | `uv run python -m crypto_cross_pred.cli config` prints resolved config | d1226a1 |
| P0-05 | `src/crypto_cross_pred/cli.py` with subcommands `download, transform, features, train, predict, simulate, notify, all` (stubs raising `NotImplementedError`) | `--help` lists all commands | 6d957e2 |
| P0-06 | `src/crypto_cross_pred/contracts.py`: unified schema constant + `TO_PREDICT_REG`, `TO_PREDICT_CLF`, `NUMERIC`, `DUMMIES`, `CATEGORICAL` | Imported successfully; single source of truth | dcb068a |
| P0-07 | `.gitignore` for `data/`, `.env`, `*.parquet`, `mlruns/`, `.venv/`, **`project-criteria.md`**; `.env.example` with empty secrets | `git status` clean after a pipeline run; `project-criteria.md` untracked | 25a6c7d, 98c1779 |
| P0-08 | `tests/test_contracts.py` (schema completeness), `tests/test_config.py` | `uv run pytest -q` passes | 9891c17 |
| P0-09 | Ruff config; `ci.yml` at the **repo root** `.github/workflows/` (lint + tests on push to develop/main, `paths: crypto-cross-pred/**`) | CI green on first push | 05dc9ae |
| P0-10 | `experiments.md`: pre-registered hypothesis, success criteria, plausible metric ranges, empty run table (SPEC §3.5) | File committed **before** the first modelling run | 9498a94 |
| P0-11 | `DECISIONS.md` seeded with D-01…D-35 | Every open decision lists the task it blocks | 25a6c7d, 05dc9ae |
| P0-12 | `.gitattributes`: `* text=auto`, LF for md/py/yml/toml/ipynb | No CRLF churn warnings on commit | 05dc9ae |
| P0-13 | Branch protection on `main`: require the `ci` check (GitHub UI) | Direct pushes to `main` blocked; `develop` stays unprotected | n/a (repo setting) |
| P0-14 | `notebooks/` directory + kernel, and one export path (`nbconvert`) reused by P3-07, P4-12, P5-10, P6-06 | A one-cell notebook exports to `.py` and the script runs headless | 628c163 |
| P0-15 | `SPEC` §8.1 artifact schemas + `contracts.py` constants (`PREDICTION_COLUMNS`, `SIM_EQUITY_COLUMNS`, `WEIGHT_COLUMNS`); reconcile `p_top` / `pred_reg` naming | Pipeline and app agree on column names before either is written | 1dad72b |
| P0-16 | `io/artifacts.py`: discovery, `summarize_dataset`, `load_predictions`, `load_sim_curves`; every loader tolerates missing files | Tests cover empty directories and latest-file selection | 828546b |
| P0-17 | `cli status`: artifact availability table (files, rows, latest file) | Prints a table on an empty project without raising | c64f38b |
| P0-18 | `app/streamlit_app.py` v0: status, dataset, predictions, simulation panels with empty states; **read-only** | `AppTest` renders with no artifacts and no exception | a161570, 6494466 |

**Rubric:** 6.2 (deps), 7.1 (modular code), 7.3 (dashboard — partial, deployment completes it)

---

## Phase 1 — Data acquisition

| ID | Task | Done when | Commit |
|---|---|---|---|
| P1-01 | `io/binance.py`: exchangeInfo loader → filter to `PERPETUAL`, `USDT` quote, `TRADING` status | Returns symbol list with `onboardDate` | f399288 |
| P1-02 | Universe selection: 150–250 symbols by liquidity (quote volume) + min history ≥18 months; persist `config/universe.json` | Universe file has 150–250 symbols, each with history stats | f399288 |
| P1-03 | Bulk backfill via `data.binance.vision` monthly ZIPs (klines, funding, OI) | One symbol backfilled 2021→now without REST pagination | 9c7abbd, 9e55173 |
| P1-04 | REST downloader with 1,500-bar pagination, retry/backoff, rate-limit awareness | Paginates a full year for one symbol; no duplicate/missing hours | 9c7abbd |
| P1-05 | Liquidation + long/short ratio + taker volume endpoints | Each dataset lands in `raw/` | acba47e, 9c7abbd, a9c2c52 |
| P1-06 | Fear & Greed loader (alternative.me), daily → parquet | 2018→now available | 418cc91 |
| P1-07 | `io/storage.py`: atomic parquet write, partition by symbol, read-max-ts helper | Idempotent rewrite; corrupt write impossible on crash | d75c255 |
| P1-08 | `io/huggingface.py`: upload/download dataset snapshots, public read | Snapshot uploads; fresh clone can download it | fde39be |
| P1-09 | Incremental mode: fetch only `max(ts)+1h → now` per symbol, upsert | Second run downloads a handful of bars, not full history | 7e8d131 |
| P1-10 | Data quality report: row counts, date coverage per symbol, NaN rates, gaps | Report printed + saved; excluded symbols listed with reasons | 34c3b4b |
| P1-11 | `io/fred.py`: `VIXCLS`, `DGS10`, `DFF`, `DTWEXBGS`, `BAA10Y` → parquet, weekday-only, explicit 1-day lag rule | Series align to UTC hourly with no same-day value | 418cc91 |
| P1-12 | **Final top-up on 2026-11-07**: klines, funding and metrics for 2026-10-01 → 2026-10-31, then freeze. The October monthly archive is published by then | Data ends exactly at `data_end`; quality report shows no gap after 2026-09-30 | |

**Rubric:** 2.1, 2.3, 2.4, 6.4, 6.5

---

## Phase 2 — Transform, features, labels

| ID | Task | Done when | Commit |
|---|---|---|---|
| P2-01 | `data/transform.py`: raw sources → unified schema (SPEC §4.2), dedupe on `(symbol, ts)`, UTC index | One dataframe; schema test passes | |
| P2-02 | Align funding (8h), F&G (daily), and FRED macro (daily, lagged 1 day) to hourly by forward-fill only | No backward fill; no same-day macro value; assert monotonic `ts` | |
| P2-03 | `data/features.py`: price/volume family (~26 features) | Feature count + no-lookahead test passes | |
| P2-04 | Derivatives family (~15 features) | Same | |
| P2-05 | Cross-sectional family (~9 features) computed per timestamp | Assert stats computed within same `ts` | |
| P2-06 | Market-wide + BTC-relative family (~9 features) | Same | |
| P2-07 | Dummies/categoricals: hour, weekday, weekend, vol regime, funding regime, symbol encoding | Encoders fit inside fold (see P4-02) | |
| P2-08 | `data/labels.py`: `fwd_ret_24h`, `cs_excess_ret_24h`, `TO_PREDICT_REG`, `TO_PREDICT_CLF` | Last 24 rows/symbol dropped; positive rate ≈ 20% | |
| P2-09 | Write `processed/dataset_{date}.parquet` + push to HF | File loads from HF in a fresh process | |
| P2-10 | `tests/test_no_leakage.py`: shuffle-future test, timestamp monotonicity, and no same-day macro values | Test fails if any feature uses `t+1` or a same-day FRED value | |
| P2-11 | Macro regime family (~11 features) incl. `term_spread` and `macro_risk_off` dummy | Feature count + no-lookahead test passes | |

**Rubric:** 3.1, 3.2, 2.2

---

## Phase 3 — EDA

| ID | Task | Done when | Commit |
|---|---|---|---|
| P3-01 | `notebooks/01_eda.ipynb`: dataset overview, coverage, missingness heatmap | Runs start-to-finish on HF snapshot | |
| P3-02 | Distribution of `TO_PREDICT_REG` / `TO_PREDICT_CLF` overall and by symbol | Plots + written findings | |
| P3-03 | Correlation matrix + top correlated features vs. target | Table ranked by absolute correlation | |
| P3-04 | Univariate IC (Spearman) per feature, with confidence intervals | Ranked feature table saved | |
| P3-05 | Regime analysis: IC by vol regime, funding regime, macro regime, month, BTC trend | Findings noted (feeds strategy filters) | |
| P3-06 | Feature selection: drop near-constant / highly collinear / low-IC features; record decisions | Final feature list written to SPEC.md §4.3 | |
| P3-07 | Export notebook to `scripts/01_eda.py` (or `nbconvert`) | Script runs headless | |
| P3-08 | Power check: minimum detectable rank IC given universe size, history, and overlapping 24h labels; record in `experiments.md` | MDE stated; the verdict rule in SPEC §3.5 is achievable, or the hypothesis is revised before modelling | |

**Rubric:** 3.3, 5.8, 1.4

---

## Phase 4 — Modeling

| ID | Task | Done when | Commit |
|---|---|---|---|
| P4-01 | `models/validate.py`: purged walk-forward, monthly retrain, 24h purge+embargo — **dev period only** (2021-01 → 2025-10) | Fold boundaries asserted; no overlap between the train label window and the dev_oos month; holdout never loaded | |
| P4-02 | Fold-local preprocessing pipeline (impute, scale, target-encode) | Pipeline fitted on the train fold only; the validation fold proves it | |
| P4-03 | **Ridge** on `cs_excess_ret_24h` (standardized numerics), `alpha` tuned — establishes the linear IC floor and is the regression half of the study | Rank IC recorded as the floor | |
| P4-04 | **DecisionTree** for both targets (`DecisionTreeRegressor` + `DecisionTreeClassifier`), `max_depth` sweep as in module 3; one plotted tree + feature importance | Predictions for both targets; importances written to the report | |
| P4-05 | **RandomForest** for both targets (`RandomForestRegressor` + `RandomForestClassifier`), `n_estimators` / `max_depth` sweep as in module 4 | Beats or matches the single tree on rank IC | |
| P4-06 | **LogisticRegression** classifier on top-quintile membership, scaled features | Calibrated-ish probabilities; AUC recorded as the linear classifier floor | |
| P4-07 | **Regression vs classification study**: same folds, features and universe; compare rank IC (regression) against AUC + precision@top-decile (classification); decide which drives sim3 sizing | Finding written to `experiments.md`; the choice is stated in SPEC §5 | |
| P4-08 | `models/tuning.py`: Optuna, 30–50 trials, objective = rank IC / AUC, on a dev window only | Best params saved to `config/params.json`; tuning outside WF loop | |
| P4-09 | Walk-forward run across all folds; store per-fold metrics + OOS predictions | `predictions/{date}.parquet` with `pred_reg`, `pred_clf`, `p_top` | |
| P4-10 | Metrics report: rank IC, IC decay, decile spread, precision@top-decile, AUC, per-symbol and per-month breakdown | Table + plots in notebook 02 | |
| P4-11 | Decision rules implemented: conviction thresholds and sizing (SPEC §5) | Unit test on synthetic probs | |
| P4-12 | `notebooks/02_modeling.ipynb` + exported script | Runs headless | |
| P4-13 | Log every modelling run in `experiments.md`: change, reason, dev OOS metric, verdict, keep/drop | One row per run; two-strike rule applied | |

**Rubric:** 4.1, 4.2, 4.3, 4.4, 4.5

---

## Phase 5 — Trading simulation

| ID | Task | Done when | Commit |
|---|---|---|---|
| P5-01 | `sim/metrics.py`: CAGR, Sharpe, Sortino, MaxDD, Calmar, rolling returns, turnover, hit rate | Unit tests against hand-computed values | |
| P5-02 | Cost model: taker 4bps/side + slippage 2bps + funding every 8h | Cost applied to every trade; funding sign correct for shorts | |
| P5-03 | `sim/vector.py` **sim0**: funding-carry rule, no model — long 20 most-negative funding, short 20 most-positive, equal weight, daily rebalance | `sim0_` fields in predictions; uses only funding known at decision time | |
| P5-04 | `sim/vector.py` sim1: long-only top decile, equal weight, daily rebalance | Equity curve + metrics; `sim1_` fields in predictions | |
| P5-05 | `sim/vector.py` sim2: long-short top/bottom decile, dollar-neutral | `sim2_` fields; net exposure ≈ 0 | |
| P5-06 | `sim/exact.py` sim3: iterative, reinvested capital, prob-weighted sizing, vol target 15%, stop-loss, max positions | Capital conservation test passes; no lookahead in fills | |
| P5-07 | Benchmarks: BTC HODL, equal-weight basket, cash | All three plotted on the same axis | |
| P5-08 | Profitability writeup: gross vs net, cost sensitivity table, CAGR/Sharpe/MaxDD vs benchmarks, **and sim3 vs sim0** | Clear statement of whether the edge survives and whether ML beats the rule | |
| P5-09 | Deep analysis: precision by symbol/month/regime; debug worst predictions; improvement ideas | Section in notebook 03 | |
| P5-10 | `notebooks/03_simulation.ipynb` + exported script | Runs headless | |
| P5-11 | Freeze all choices (features, params, thresholds) and run the **sealed holdout once** (2025-11 → 2026-10) | Run id logged; nothing changed afterwards based on the result | |
| P5-12 | Verdict writeup: supported / falsified / inconclusive, with reasoning and the next idea | Matches the pre-registered criteria (SPEC §3.5) | |

**Rubric:** 5.1–5.8

---

## Phase 6 — Automation

| ID | Task | Done when | Commit |
|---|---|---|---|
| P6-01 | `cli.py all` orchestrates download → transform → features → train → predict → simulate → notify | Single command reproduces everything | |
| P6-02 | `--source hf` regime: read prebuilt snapshot, skip download/transform | Completes without network writes | |
| P6-03 | `--source binance` regime: incremental download to latest bar | Second run is fast (incremental) | |
| P6-04 | `pipeline.yml` at the **repo root** `.github/workflows/`: **re-enable the commented-out `schedule:` block** (disabled until `cli all` works), keep `workflow_dispatch`, `working-directory: crypto-cross-pred` | Manual trigger produces artifacts; the nightly run is green | |
| P6-05 | Artifact publishing from CI (HF upload) + run summary in Actions UI | Latest prediction file visible on HF after run | |
| P6-06 | Orchestration notebook (`notebooks/00_pipeline.ipynb`) calling `src/` functions | Demonstrates end-to-end, exports to script | |
| P6-07 | `README.md` install + run instructions (uv, env vars, both regimes, cron) | A fresh clone can follow it | |

**Rubric:** 6.1, 6.2, 6.3, 6.4, 6.5

---

## Phase 7 — Deployment

| ID | Task | Done when | Commit |
|---|---|---|---|
| P7-01 | `Dockerfile` (multi-stage, uv-based, non-root) | `docker build` + `docker run ... cli --help` works | |
| P7-02 | `docker-compose.yml` (pipeline service + app service) | `docker compose up` serves the app | |
| P7-03 | Extend the dashboard (P0-18): benchmark comparison, model-health panel, HF-snapshot source instead of local files | Loads from HF snapshot; no local data needed | |
| P7-04 | Deploy to Streamlit Community Cloud (public app); app-root dependencies resolve there (app-local `requirements.txt` or pyproject) | Public URL renders with real data | |
| P7-05 | `.dockerignore`, image size sane (<1.5GB) | Build time recorded | |

**Rubric:** 7.4, 7.5

---

## Phase 8 — Bonus

| ID | Task | Done when | Commit |
|---|---|---|---|
| P8-01 | `report/telegram.py`: send daily picks, PnL, drift warnings (Markdown) | Message arrives on phone from CI run | |
| P8-02 | Monitoring alerts: IC < 0, zero trades, stale data, download failure. Alerts are **reporting only**; retraining stays on the fixed monthly schedule (SPEC §3.6) | Each condition triggers a distinct message; no manual tuning path | |
| P8-03 | `report/broker.py`: Binance **testnet** client, position sizing from sim3, order placement + status | Testnet order filled; no real funds touched | |
| P8-04 | Secrets wired into GitHub Actions | No secret in logs | |
| P8-05 | Document bonus features in README (how to enable, how to test) | Reviewer can follow without help | |

**Rubric:** 7.2, 7.3

---

## Phase 9 — Writeup

| ID | Task | Done when | Commit |
|---|---|---|---|
| P9-01 | README problem statement + end goal + who uses it | Satisfies 1.1 + 1.2 | |
| P9-02 | README step-by-step: data → transform → features → models → sim → automation, with findings and difficulties | Satisfies 1.4 | |
| P9-03 | Data sources section: every source, every feature, description table (20+ new features) | Satisfies 2.2 | |
| P9-04 | Results section: benchmark comparison, CAGR/Sharpe/MaxDD, honest limitations | Satisfies 5.4, 5.7 | |
| P9-05 | Reproducibility: exact command list, env vars, runtime estimates | Fresh clone works | |
| P9-06 | Data link on HF + statement that no data is in the repo | Satisfies submission rule | |
| P9-07 | Final rubric self-audit against `project-criteria.md` | Every claimed point has a file/section reference | |
| P9-08 | "Reuse" section in README: edit config → run one command, with the config-swap rerun table | A reader can change horizon or universe without touching code (D-30) | |
| P9-09 | Results narrative covers iteration honestly: what was tried, what was dropped, what the verdict means | `experiments.md` linked and complete | |
| P9-10 | README "Design and decisions" section linking `docs/`, plus the AI-assistance disclosure | Reviewer reaches the spec and decision record in one click | |

---

## Rubric coverage tracker

| Criterion | Points | Phase(s) | Status |
|---|---|---|---|
| 1. Problem description | 4 | 9 | `[ ]` |
| 2. Data sources | 4 | 1, 2 | `[ ]` |
| 3. Transformations + EDA | 3 | 2, 3 | `[ ]` |
| 4. Modeling | 5 | 4 | `[ ]` |
| 5. Trading simulation | 8 | 5 | `[ ]` |
| 6. Automation | 5 | 0, 6 | `[ ]` |
| 7. Bonus | 7 | 7, 8 | `[ ]` |

---

## Open decisions

Moved to [DECISIONS.md](./DECISIONS.md) §3. Only `D-18` blocks work (P0-02); the rest can
be resolved when their phase starts.
