# index-breadth-momentum — S&P 500 breadth

Predicting SPY with market breadth: what share of the index is actually participating.

## Problem

Market breadth has been a widely known indicator, but its practical use case has been unclear.

## Solution

Build a model that converts breadth data into actionable signals, and test whether those signals can outperform low-risk fixed-interest income.

**Status: ingestion chain done and verified. Breadth features and models not started.**

| Step | State |
|---|---|
| 1. SPY holdings from SEC EDGAR (1996-2026) | done — 31,078 rows, 62 periods |
| 2. CUSIP/name → ticker | done — 99.5% of index weight resolved |
| 3. Mapped layer with issuer ids | done — `data/mapped/` |
| 4. Daily prices | done — 625 symbols, 2014 onward |
| 5. Reconciliation against real prices | done — 0 rows disagree |
| 6. Constituent table (issuer × day, priced) | done — 1.56M rows |
| 7. Breadth measures | notebook / EDA — not stored |
| 8. Target, model, simulation, dashboard | todo |

## Data

Two files run the notebook, both attached to the `v0.1-data` release:
`data/constituents/sp500_constituents_daily.parquet` and `data/prices/SPY.parquet`. Nothing large is in git.

Download links, checksums and the rebuild commands: [DATA.md](DATA.md).

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

## Why the model starts in 2016

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

**Model window: 2016-01-01 onward.** Weighted breadth is readable from 2014-12-01, equal-weight
from 2018-05-29 — each gated on its own denominator at 80%. Every row carries
`coverage_names`, `coverage_weight`, `weighted_ok` and `equal_weight_ok`, so the reader can
see exactly what backs each date. A stricter 90% subset is a filter away, not the default.

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
