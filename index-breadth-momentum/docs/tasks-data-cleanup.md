# Data cleaning tasks

What must be fixed before any breadth feature or model touches the data.
Legend: `[ ]` todo · `[~]` in progress · `[x]` done

Build order: **A identity → B price honesty → C constituent table**. B and C assume A is finished.

---

## Phase A — identity (blocking)

| ID | Status | Task | Done when |
|---|---|---|---|
| A1 | `[x]` | Null the `000000000` CUSIP placeholder | 0 rows carry it; 28 files rewritten once, parse fixed for future runs |
| A2 | `[x]` | `breadth/holdings.py` → `data/mapped/` with `ticker`, `ticker_source`, `unresolved` | ≥99% of weight has a ticker from 2019, ≥98% from 2016 |
| A3 | `[x]` | `issuer_id` column collapsing share classes | Google A/C, Fox A/B, Discovery A/C share one id |
| A4 | `[x]` | Normalise dtypes on read: dates to `datetime64[ns]`, ticker/cusip to nullable string | `tests/test_schema.py` passes on all 62 periods |
| A5 | `[x]` | `to_issuer_level()` + test that no `(period, issuer_id)` duplicates survive | 148 collapsed listings, value and weight conserved |
| A6 | `[x]` | Rename `value` → `holding_value` (code, docs, 62 store files) | no `value` column anywhere; `turnover_value` stays a derived concept |

**Why A first:** every join downstream needs a stable key. Null tickers were the reason
each module re-derived the mapping.

**Migrations applied to the raw store** (both one-off, both documented here so the
append-only claim stays honest): nulled the `000000000` CUSIP (A1), renamed `value` to
`holding_value` (A6).

## Phase B — price honesty

| ID | Status | Task | Done when |
|---|---|---|---|
| B1 | `[x]` | Price basis rule: **levels use `close`, changes use `adj_close`** | stated in `schema.md`, enforced by `tests/test_prices.py` |
| B2 | `[x]` | `split_factor` on every mapped row | GE, GOOGL, WMT reconcile to 1.00 (`test_split_factor_reconciles_with_prices`) |
| B3 | `[x]` | Exclude ticker-reuse and share-class rows (`breadth/exclusions.py` → `config/exclusions.csv`) | 0 priced rows off by >10%; `test_no_priced_row_is_off_by_more_than_10pct` |
| B4 | `[x]` | Stale guard: `prices.stale()` drops tickers >5 trading days behind | `tests/test_staleness.py`: fresh, exactly-5, stale and weekend cases |
| B5 | `[x]` | Odd-instrument filter: `prices.odd_tickers()` + `prices.clean()`; preferred line remapped to parent | `PCG-PE` no longer appears in `data/mapped/`; `tests/test_odd_instruments.py` |
| B6 | `[x]` | Reconciliation budget in CI: fail above 1% of weight mismatched | `tests/test_reconciliation.py`; `.github/workflows/index-breadth-momentum-tests.yml` |

## Phase C — constituent table

| ID | Status | Task | Done when |
|---|---|---|---|
| C1 | `[x]` | `breadth/constituents.py`: as-of join on `available_at`, prices only `<= date` | 1.56M issuer-days; `tests/test_constituents.py` checks weights, coverage, filing lag |
| C2 | `[x]` | `coverage_names`, `coverage_weight`, `equal_weight_ok` per date | weighted breadth renormalises over the priced subset implicitly |
| C3 | `[x]` | Capture `assetCat`, `payoffProfile`; filter the universe to common equity | 14,117 `EC` rows in, one `DE` CVR out; `test_no_non_equity_rows` |
| C4 | `[x]` | Write `data/constituents/daily.parquet` | feature code reads this and nothing else |
| C5 | `[x]` | Weighting capability only: `weighted_ok` and `equal_weight_ok` flags, each on its own 80% gate | flags live in `data/constituents/`; the readings themselves are notebook/EDA work |

**Why C last:** the constituent table is the only thing features should import. Until A and B
are done, it would bake in the errors.

---

## Decisions taken

- **Ticker reuse** (`IR`, `CB`, `AVGO`) and share-class clashes (`UAA` Class C): the row is
  kept for its weight but its ticker is cleared, recorded in `config/exclusions.csv` with
  the reconciliation ratio. 15 rows, 0.03% of weight. Never dropped silently, never
  averaged into another company's series. Per-row explanations:
  [exclusions.md](exclusions.md).
- **Coverage floor**: 90% of index weight opens the equal-weight reading; everything from
  2016 onward still publishes the weighted reading. Measured: first snapshot above the
  floor is 2019-09-30 (95.1%), 2016-09-30 sits at 84.2%.
- **Price basis**: levels use `close` (split-adjusted, stable, auditable), changes use
  `adj_close` (total return). Using `adj_close` for everything was considered and rejected:
  it steps ~0.5% at each ex-dividend date, it is restated whenever a new dividend is paid,
  and it cannot be reconciled against `holding_value / shares`. Deriving returns from
  `close` instead was also rejected — advance/decline would book a spurious down day for
  every dividend payer, four times a year.
- **Breadth variants**: both equal-weight and weighted are computed for every date, with
  `coverage_names`, `coverage_weight` and `equal_weight_ok` alongside.

## Open questions

- `issuer_id` by normalised name can merge two genuinely different companies with the same
  name. Acceptable, or should it be the CUSIP of the largest share class?
- Should the weighted breadth use reported `weight`, or recompute weights from
  `holding_value` after dropping unpriced names? Both are defensible; they differ by the
  coverage gap.
