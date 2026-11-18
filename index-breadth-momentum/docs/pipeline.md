# Pipeline

Holdings -> tickers -> prices -> verification. Breadth features and models are not built yet.
Column definitions live in [schema.md](schema.md); cleanup work in
[tasks-data-cleanup.md](tasks-data-cleanup.md).

## Flow

```
EDGAR submissions index
  -> 77 filings (N-30D 1996-2019, N-PORT 2019+)
  -> parse in memory (text / HTML / XML)
  -> data/holdings/period=YYYY-MM-DD.parquet      62 files, append-only
        |
        v
  CUSIP -> ticker (OpenFIGI)  ->  name -> ticker (later filings, then SEC list)
  -> config/tickers.csv                           committed cache
  -> data/mapped/period=YYYY-MM-DD.parquet        + ticker, ticker_source, issuer_id
        |
        v
  Yahoo daily bars, one file per symbol
  -> data/prices/{ticker}.parquet                 2014-06 onward
  Yahoo split factors
  -> data/splits.parquet
        |
        v
  implied price (holding_value / shares) vs close x split factor
  -> data/verify_report.csv                       coverage + accuracy per period
        |
        v
  as-of join on available_at, issuer level
  -> data/constituents/daily.parquet             the constituent table (1.56M rows)
```

Breadth itself is computed in the research notebook (EDA), from this table: moving averages
via TA-Lib, counts and dispersion in pandas. Nothing is pre-computed and stored, so a measure
can be changed without a rebuild.

| step | command | output |
|---|---|---|
| holdings | `uv run python -m breadth.edgar` | `data/holdings/` |
| mapping | `uv run python -m breadth.tickers` | `config/tickers.csv` |
| mapped layer | `uv run python -m breadth.holdings` | `data/mapped/` |
| prices | `uv run python -m breadth.prices` | `data/prices/`, `data/splits.parquet` |
| verify | `uv run python -m breadth.verify` | `data/verify_report.csv` |
| constituents | `uv run python -m breadth.constituents` | `data/constituents/daily.parquet` |

## Append-only rules

- Holdings: one parquet per period, written only if absent. `_accessions.txt` records what
  has been fetched, so a rerun only requests new filings.
- A period reported twice (N-30D and N-PORT) keeps the better source, ranked
  `N-PORT > N-CSR > N-30D`.
- `data/mapped/` is derived and rebuilt wholesale every run — it is never treated as history.
- Prices: one file per symbol; refetched only when its last date is stale.

## Point-in-time rule

A period ending Sep 30 is filed in late November, so dating holdings by `period` gives you
constituents the market did not see for ~2 months.

```python
snapshot = df[df.available_at <= t].sort_values("period").tail(1)
```

## Tickers

2019+ filings carry a CUSIP, which OpenFIGI maps exactly. Older filings only have a name,
so they borrow the ticker of the same company from a later filing, then from the SEC's
`company_tickers.json`. Any mapping that points at the wrong company shows up in `verify`
as a reported price that differs from the market close.

## Verification

`holding_value / shares` is the price the fund reported. Yahoo closes are split-adjusted,
so multiplying the close by every split after the period must reproduce it. Current state:
99-100% of weight priced from 2020, 99% of those agree within 10%, 17 rows disagree
overall (ticker reuse).

Coverage is reported two ways — `coverage_names` and `coverage_weight` — because missing
names are not random. Each breadth measure is gated on its own denominator at 80%
(`weighted_ok`, `equal_weight_ok`); see [schema.md](schema.md#7-breadth-measurement-policy).

## Parsing rules worth knowing

- Text era: company names wrap, so a name-only line is prepended to the next row.
- Only tables headed `Common Stocks … Shares … Value` are read. Without that filter the
  financial statements (expenses, gains) match the same number pattern.
- Short-term and cash positions are dropped; the universe is common stock only.
- Implied price must be between $0.50 and $50,000 per share.
- Names shorter than 4 characters are dropped (leaves a wrapped `Inc` behind).

## Known limits

- Delisted companies have no Yahoo history, so coverage decays going back: ~99% of weight
  in 2019+, ~93% in 2016, ~68% in 2007. The model window starts 2016.
- Dual share classes appear as two rows under one name. Use `issuer_id`, not row count.
- Row counts per period are 486-506 rather than exactly 500, faithful to the filings.
