# index-breadth-momentum — S&P 500 breadth

Predicting SPY with market breadth: what share of the index is actually participating.

## Problem

Market breadth has been a widely known indicator, but its practical use case has been unclear.

## Solution

Build a model that converts breadth data into actionable signals, and test whether those signals can outperform low-risk fixed-interest income.

**End goal:** a long/flat timing rule on SPY built only from constituent breadth, judged against
a 7% annual bar rather than against the index.

**Status: complete through test evaluation. Dashboard and deployment not done.**

| Step | State |
|---|---|
| 1. SPY holdings from SEC EDGAR (1996-2026) | done — 31,078 rows, 62 periods |
| 2. CUSIP/name → ticker | done — 99.5% of index weight resolved |
| 3. Mapped layer with issuer ids | done — `data/mapped/` |
| 4. Daily prices | done — 625 symbols, 2014 onward |
| 5. Reconciliation against real prices | done — 0 rows disagree |
| 6. Constituent table (issuer × day, priced) | done — 1.57M rows |
| 7. Breadth features and 5-day target | done — notebook, 32 features |
| 8. Models, validation, final test | done — baseline, tree, forest, logistic |
| 9. Dashboard / deployment | todo |

## Results

Tuned on validation (2022-04 → 2024-07), then refit on train + validation and scored once on the
untouched test block (2024-07-26 → 2026-11-10). Fees are charged per trade at 0.005R; no tax is
deducted, because both the strategy and the benchmark are pre-tax.

Validation:

| model | trade share | expectancy | CAGR | max DD | Sharpe |
|---|---|---|---|---|---|
| baseline (all above 50d SMA) | 39.2% | 0.174R | 3.28% | −5.23% | 0.01 |
| decision tree | 64.1% | 0.194R | 5.89% | −8.59% | 0.89 |
| **random forest** | **72.6%** | **0.211R** | **7.21%** | **−8.14%** | **1.27** |
| logistic regression | 87.7% | 0.198R | 8.12% | −8.67% | 1.30 |

The forest was chosen for the best expectancy at materially lower exposure than logistic
(72.6% vs 87.7%), which is close to buy-and-hold.

Final model, test only:

| trades | trade share | win rate | profit factor | expectancy | CAGR | max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| 523 | 90.8% | 57.6% | 1.30 | 0.167R | 7.08% | −11.23% | 1.06 |

Ending equity over the test window: **1.184** for the model, **1.167** for the 7% benchmark,
**1.396** for SPY buy-and-hold. SPY's worst drawdown in that window was −18.8%, the model's −11.2%.

The honest reading: it clears the bond bar by a hair and loses to the index by a wide margin,
because the test window is a bull run and the model was long 90.8% of it. Worse, the days it sat
out averaged +0.248R against +0.167R when long — the selection was negative. Leverage does not fix
this: at 2× the drawdown would be about −22%, worse than SPY's −18.8%, so the return only improves
by taking on more risk than the index itself. Full discussion in
[notebook.ipynb](notebook.ipynb), last two cells.

## Data

Two files run the notebook, both attached to the `v0.1-data` release:
`data/constituents/sp500_constituents_daily.parquet` and `data/prices/SPY.parquet`. Nothing large is in git.

Download links, checksums and the rebuild commands: [DATA.md](DATA.md).

## Sources

| source | what it gives | why |
|---|---|---|
| SEC EDGAR N-30D / N-PORT | SPY holdings per period, 1996-2026 | the breadth denominator: who was actually in the index |
| Yahoo daily bars | OHLCV for 625 constituent tickers + SPY | per-name indicators, and the target |
| Yahoo splits | split factors | reconciles reported holdings against adjusted prices |
| OpenFIGI | CUSIP → ticker | joins holdings to prices |

No third-party breadth feeds. Every breadth number in the notebook is computed from the
constituent table above, which is what makes the 1.57M-row dataset necessary rather than decorative.

## Features

32 features, all derived from constituents, plus one target. No SPY moving average, RSI or ATR is
used as an input — SPY appears only inside the label.

| group | columns | idea |
|---|---|---|
| above-SMA breadth | `breadth_sma_5d/20d/60d` | share of issuers above their own moving average |
| overbought / oversold | `breadth_rsi70_*`, `breadth_rsi30_*` | share of issuers with RSI above 70 or below 30 |
| distance from trend | `med_rel_sma_{5,20,60}d_atr` | median distance from SMA, normalised by ATR |
| momentum | `med_rsi_{5,20,60}d` | median issuer RSI |
| volatility | `med_atr_pct_{5,20,60}d` | median ATR as a share of price |
| participation | `breadth_adv_dec_{5,20,60}d` | advance/decline ratio across issuers |
| extremes | `breadth_high_{13,26,52}w`, `breadth_low_*` | share at 13/26/52-week highs and lows |
| breadth momentum | `breadth_sma_*_chg_5d` | 5-day change in breadth itself |
| dispersion | `iqr_rel_sma_{5,20,60}d` | interquartile range of distance from trend |
| turnover | `breadth_turnover_rel_60d` | relative turnover against its own 60-day base |

**Target:** `rr_5d`, the forward 5-day SPY return measured in 20-day ATR units. One unit is the
risk unit R, so a model that returns 0.2R per trade earns 0.2 × ATR on a position sized to 1 ATR
of risk. Labels use `adj_close`; levels use `close`.

## Reproduce

The notebook reads both parquet files straight from the `v0.1-data` release URL, so nothing needs to
be downloaded first. Only the notebook and an environment are required:

```bash
cd index-breadth-momentum
uv sync
uv run jupyter lab notebook.ipynb     # run all cells, top to bottom
```

The notebook is self-contained: features, splits (60/20/20 by date), baseline, both grids, three
models, final refit, and the charts. Runtime is about 40 seconds on a laptop.

To rebuild the dataset from SEC EDGAR instead of using the release, run the pipeline commands in
[Run](#run) below and point the two `pd.read_parquet` calls at the local files. Checksums and rebuild
details: [DATA.md](DATA.md).

## Flow

```
EDGAR submissions index
  -> 77 filings (N-30D 1996-2019, N-PORT 2019+)
  -> parse in memory (text / HTML / XML)
  -> data/holdings/period=YYYY-MM-DD.parquet      append-only, 62 files
        |
        v
  CUSIP -> ticker (OpenFIGI) -> name -> ticker (later filings, SEC list)
  -> config/tickers.csv
  -> data/mapped/period=YYYY-MM-DD.parquet    + ticker, ticker_source, issuer_id
        |
        v
  Yahoo daily bars  -> data/prices/{ticker}.parquet
  Yahoo splits      -> data/splits.parquet
        |
        v
  holding_value/shares vs close x split factor  -> data/verify_report.csv
        |
        v
  as-of join on available_at, issuer level
  -> data/constituents/sp500_constituents_daily.parquet             the constituent table
```

## Run

```bash
cd index-breadth-momentum
uv run python -m breadth.edgar      # holdings      (~2 min, 68 requests)
uv run python -m breadth.tickers    # cusip -> ticker (~10 min first time, cached)
uv run python -m breadth.holdings   # mapped layer  (adds ticker + issuer_id)
uv run python -m breadth.exclusions # ticker-reuse rows -> config/exclusions.csv
uv run python -m breadth.prices     # daily bars    (~5 min)
uv run python -m breadth.verify     # reconciliation
uv run python -m breadth.constituents  # constituent table
uv run pytest -q                    # schema contracts
```

Notebook environment: TA-Lib **0.8.3** installs from wheels (`uv add ta-lib`) and gives
`talib.SMA(close, 200)` with 199 leading NaNs, which is the warm-up behaviour we want.
`pandas_ta`, `ta` and `talipp` also import cleanly if a pure-Python package is preferred.

## Why the study starts in 2015

Yahoo has no price history for delisted tickers (checked: Lehman, Enron, Bear Stearns,
Merrill all return zero rows). Breadth can only be computed on names that still carry a
price series, so usable history is shorter than holdings history.

Measured coverage per snapshot (`data/verify_report.csv`):

| period | `coverage_names` | `coverage_weight` |
|---|---|---|
| 1995-2013 | 0% | 0% — prices not downloaded |
| 2014-09-30 | 65% | 80% |
| **2016-09-30** | **73%** | **87%** |
| 2018-09-30 | 82% | 92% |
| 2019-09-30 | 84% | 94% |
| 2021-03-31 | 90% | 97% |
| 2025-03-31 | 97% | 99% |

`coverage_names` counts holdings; `coverage_weight` counts index weight. They differ
because the missing names are not random.

**Study window: 2015-06-01 onward, 2,880 modelled days.** Weighted breadth is readable from
2014-12-01, equal-weight from 2018-05-29 — each gated on its own denominator at 80%. The first
usable row is 2015-06-01 because the longest features (200-day SMA, 52-week extremes) need their
warm-up. Every row carries `coverage_names`, `coverage_weight`, `weighted_ok` and `equal_weight_ok`,
so the reader can see exactly what backs each date. A stricter 90% subset is a filter away, not the
default — and picking it after seeing the test result would be curve-fitting, so it was not done.

Dates before 2014 stay in the holdings store but are excluded — the dot-com and GFC eras
lose 60-80% of their members.

## Verification

`holding_value / shares` is the price the fund reported. Multiply the Yahoo close by every split
after the period and the two must agree:

| | 2016 | 2020 | 2026 |
|---|---|---|---|
| `coverage_names` | 70% | 88% | 99% |
| `coverage_weight` | 84% | 96% | 99% |
| `match_names` | 70% | 88% | 99% |

17 rows disagreed before exclusions. After `config/exclusions.csv` is applied, **0 rows**
disagree (0.00% of weight). Every excluded row is explained in
[docs/exclusions.md](docs/exclusions.md).

## Notes

- Filings are late (~2 months), so use `available_at`, never `period`, for point-in-time joins.
- Levels use split-adjusted `close`; changes use total-return `adj_close`. Never mix them
  (see [docs/schema.md](docs/schema.md#price-basis-rule)).
- `data/` is gitignored; nothing from EDGAR or Yahoo is committed.

Details: [docs/schema.md](docs/schema.md) for every column and definition,
[docs/pipeline.md](docs/pipeline.md) for how it is built,
[docs/exclusions.md](docs/exclusions.md) for why 15 holdings have no ticker,
[docs/tasks-data-cleanup.md](docs/tasks-data-cleanup.md) for what is still unsafe.
