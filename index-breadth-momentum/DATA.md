# Data

Two files are enough to run the notebook. Both are attached to the `v0.1-data` release of
this repository, so nothing large sits in git.

| file | size | sha256 |
|---|---|---|
| `sp500_constituents_daily.parquet` | 34.5 MB | `7FB400218B842FE9EB080B871AC556673A962966AA75D7549F09585214E877F2` |
| `SPY.parquet` | 0.15 MB | `A7A0DBC9F125B11FB233A26B75267E16373D5A47BF000C6C035A20FE9C95EA49` |

## Download

```bash
BASE=https://github.com/rlp-jym/zoomcamp-sma-cohort-2026/releases/download/v0.1-data
mkdir -p data/constituents data/prices
curl -L -o data/constituents/sp500_constituents_daily.parquet $BASE/sp500_constituents_daily.parquet
curl -L -o data/prices/SPY.parquet       $BASE/SPY.parquet
```

Or click the links in the release page. Verify with `sha256sum` (Linux/macOS) or
`Get-FileHash` (PowerShell).

## What the files are

| file | grain | contents |
|---|---|---|
| `constituents/sp500_constituents_daily.parquet` | one row per issuer per trading day, 1.57M rows | `open`, `high`, `low`, `close`, `adj_close`, `volume`, `index_weight`, coverage and gate flags |
| `prices/SPY.parquet` | one row per trading day, 3,136 rows | benchmark and target series |

Nothing else is needed: no filings, no per-ticker price files, no splits. The constituent
table already carries prices at issuer level and the index weights they were held at.

Full column definitions: [docs/schema.md](docs/schema.md).

## Rebuild from source

No API keys, no accounts, about ten minutes:

```bash
uv run python -m breadth.edgar         # 77 EDGAR filings -> holdings (append-only)
uv run python -m breadth.tickers       # CUSIP/name -> ticker (cached in config/)
uv run python -m breadth.prices        # 625 symbols of daily bars + split factors
uv run python -m breadth.verify        # reconcile reported prices against the market
uv run python -m breadth.constituents  # the constituent table
```

Sources: SEC EDGAR for holdings (public domain), Yahoo Finance for prices. The pipeline is
idempotent - rerunning only fetches what is missing.

## Updating the local file

Rerun the pipeline; the files under `data/` are rebuilt in place and your notebook picks up
the new version. The release asset is a snapshot from submission time and is **not**
refreshed automatically, so local checksums will drift from the table above after a rebuild.
That is expected; only bytes downloaded from the release are guaranteed to match.
