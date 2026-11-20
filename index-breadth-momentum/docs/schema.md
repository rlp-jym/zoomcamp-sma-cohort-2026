# Data schema

Everything the pipeline has produced so far. Seven datasets, one purpose each.

## Vocabulary

| term | meaning |
|---|---|
| `holding_value` | market value of the position reported by the fund, USD. **This is holding value, not turnover.** |
| `shares` | shares held at the period date, as reported |
| `index_weight` | `holding_value / Σ holding_value` within one period, in percent. The security's share of the index, not of the portfolio |
| `turnover_value` | **derived later:** `volume × close`, i.e. dollar volume traded that day |
| `period` | fiscal date the holdings describe (e.g. 2026-06-30) |
| `available_at` | date the filing became public. Use this for point-in-time joins, never `period` |
| `coverage_names` | % of constituents on a date that have a usable price |
| `coverage_weight` | % of index weight those priced constituents represent — the honest coverage number |
| `adjusted close` | close adjusted for dividends *and* splits — a total-return series |
| `close` | split-adjusted price. Equal to the price on the day, restated for later splits |

### Words we do not use

| never write | write instead | why |
|---|---|---|
| panel | the constituent table, `data/constituents/` | econometrics jargon, means something else |
| value | `holding_value` or `turnover_value` | two different quantities |
| weight | `index_weight` (share of the index) or `strategy_weight` (share of the portfolio) | they diverge the moment a strategy is not fully invested |
| coverage | `coverage_names` / `coverage_weight` | "coverage" alone does not say which denominator |

## 1. `data/holdings/period=YYYY-MM-DD.parquet`

Raw parse of EDGAR filings. 62 files, 31,078 rows. **Source of truth, append-only, never edited.**

| column | dtype | notes |
|---|---|---|
| `period` | string | fiscal date |
| `available_at` | string | filing date |
| `form` | string | `N-30D`, `N-CSR`, `NPORT-P` |
| `accession` | string | EDGAR id |
| `name` | string | as printed, ASCII-folded, footnote markers stripped |
| `ticker` | object | null in practice (SPY's N-PORT has no ticker) |
| `cusip` | object | N-PORT only, 2019+; placeholder `000000000` nulled |
| `shares` | int64 | |
| `holding_value` | int64 | market value of the position, USD |
| `index_weight` | float64 | %, sums to 100 per period |
| `asset_cat` | string/null | N-PORT asset class: `EC` common equity, `DE` derivative, null for N-30D era |
| `payoff_profile` | string/null | N-PORT exposure: `Long`, `Short`, `N/A` for non-derivatives |

Grain: one holding per period. Key: `(period, cusip)` where cusip exists, else `(period, name)`.

## 2. `data/mapped/period=YYYY-MM-DD.parquet`

Derived from (1). Rebuilt wholesale on every run — safe to delete. 62 files, 31,078 rows.

All columns from (1), plus:

| column | dtype | notes |
|---|---|---|
| `ticker` | string | filled from cusip, then name, then the SEC list |
| `ticker_source` | string | `cusip`, `name`, `sec`, or null |
| `issuer_id` | string | normalised name; collapses share classes (GOOGL/GOOG) into one issuer |
| `unresolved` | bool | no ticker found |
| `split_factor` | float64 | product of every split after `period`; brings `shares` onto today's basis |
| `excluded` | bool | ticker reuse or share-class clash; ticker removed, row kept for weight |

Grain: same as (1). Key: `(period, issuer_id)` for breadth, `(period, ticker)` for price joins.
Dtypes: `period` and `available_at` are `datetime64[ns]`, every text column is nullable
string (`string`), `shares` and `holding_value` are `int64`, `unresolved` is `bool`.

`holdings.to_issuer_level(df)` collapses share classes: 31,078 rows -> 30,930 issuer rows,
148 collapsed listings, with `holding_value` and `index_weight` summed and `n_listings` counting
the classes.

## 3. `data/prices/{ticker}.parquet`

625 files, 2014-06-02 → 2026-11-17. Grain: ticker × trading day.

| column | dtype | notes |
|---|---|---|
| `date` | datetime64[ms] | naive US trading dates, no weekends |
| `open`, `high`, `low`, `close` | float64 | split-adjusted only — a real price, restated for splits |
| `adj_close` | float64 | split- **and** dividend-adjusted — a total-return series, not a price |
| `volume` | int64 | shares; `volume × close` gives `turnover_value` |

### Price basis rule

**Levels use `close`. Changes use `adj_close`.**

| use | column | why |
|---|---|---|
| price vs moving average, 52-week high/low, distance from a level | `close` | smooth series in real units |
| returns, advance/decline, momentum | `adj_close` | no fake decline on an ex-dividend date |
| reconciliation, fills, implied price | `close` × split factor | must equal the price that actually traded |

Why not `adj_close` everywhere:

1. **It steps at every ex-dividend date.** The adjustment factor drops by roughly the
   dividend yield of that payment (~0.5% for a quarterly payer), so a name sitting near its
   200-DMA gets a false cross on a day when nothing happened.
2. **It is restated retroactively.** Every new dividend rescales the whole history, so the
   same date shows a different `adj_close` in 2026 than it did in 2020. `close` only
   changes when the company actually splits. Reproducibility requires the second.
3. **It cannot be audited.** `holding_value / shares` is the real traded price. Comparing
   it with `adj_close` is off by the cumulative dividend factor — a 2× gap for a long-term
   payer — which would hide exactly the errors reconciliation is meant to catch.

Never compare either column to `holding_value / shares` without the ticker's split factor.

Files are downloaded per symbol, and a symbol that stops trading keeps its last row. Before
using prices for a given date, call `prices.clean(asof)`:

- `prices.stale(asof)` — symbols more than 5 trading days behind, measured on SPY's calendar.
- `prices.odd_tickers()` — anything that is not a clean common-stock series: preferred or
  warrant symbols (`PCG-PE`), NaN or non-positive closes, duplicate dates, gaps over 10 days.

`clean()` returns the usable set. Today that is 624 of 625 files; the odd one is a preferred
line that no holding references any more.

## 4. `data/splits.parquet`

1,802 rows, 444 tickers. Grain: ticker × corporate-action date.

| column | dtype | notes |
|---|---|---|
| `ticker` | string | |
| `date` | datetime64[ms] | includes spin-offs booked as splits (GE 1.28, 1.25) |
| `ratio` | float64 | 2.0 = 2:1 split, 0.125 = 1:8 reverse |

The factor to apply to a row is the product of all ratios with `date > period`. That value
is materialised as `split_factor` on every mapped row, so no consumer has to re-derive it.

## 5. `data/verify_report.csv`

62 rows, one per period.

| column | notes |
|---|---|
| `period` | |
| `rows` | mapped rows with a ticker |
| `coverage_names` | % of those with a price near the period date |
| `coverage_weight` | % of index weight those rows represent |
| `match_names` | % whose `holding_value / shares` agrees with price × split factor within 10% |
| `match_weight` | the same, weighted by portfolio weight |

Zero before 2016 by design: no price history survives for delisted members.

## 7. Breadth measurement policy

Two readings are computed for every date, because they answer different questions:

| measure | question | failure mode |
|---|---|---|
| equal-weight | what share of *issuers* is participating? | one vote per company, blind to size |
| weighted | what share of *index weight* is participating? | NVDA outvotes 400 small caps |

Both need prices, and prices are missing for delisted names. Rule — each measure is gated
on its own denominator, both at 80%:

- `coverage_weight >= 80%` → the weighted reading is published (`weighted_ok`).
- `coverage_names >= 80%` → the equal-weight reading is published (`equal_weight_ok`).

The assumption is that large constituents keep a price series even in the older years,
so the weighted reading degrades gracefully while the equal-weight one silently loses
votes. Every output keeps `coverage_names` and `coverage_weight` so the reader can see
which regime produced a number.

## 6. `config/tickers.csv`

614 rows. Committed, so a fresh clone skips the rate-limited OpenFIGI call.

| column | notes |
|---|---|
| `cusip` | |
| `ticker` | US listing |
| `name` | issuer name from OpenFIGI |

`config/sec_tickers.csv` is a regenerable cache of the SEC company list and is gitignored.

`config/aliases.csv` holds curated name → ticker pairs for companies the lookup cannot
bridge: renames (`Adobe Systems` → `ADBE`), SEC list gaps (`AVB` is absent from
`company_tickers.json`) and printed-name drift. Each row carries the reconciliation ratio
and `ok`; only `ok=True` is applied. An alias whose reported price does not agree with the
market is rejected, so a wrong guess cannot enter. Regenerate with
`python -m breadth.aliases`.

## 8. `config/exclusions.csv`

Rows whose ticker cannot be reconciled with the price the fund reported. Committed, so the
exclusions are inspectable rather than silent. 15 rows.

| column | notes |
|---|---|
| `period` | |
| `name` | issuer name as stored, so the match is unambiguous |
| `ticker` | the ticker that failed |
| `ratio` | `holding_value / shares` divided by `close x split_factor` |
| `reason` | `share_class` (same issuer, two listings, one ticker) or `unexplained` |

Produced by `python -m breadth.exclusions`, applied by `python -m breadth.holdings`, which
keeps the row (it still carries weight) but clears its ticker and sets `excluded = True`.

Each excluded row, with the corporate action behind it, is explained in
[exclusions.md](exclusions.md).

## 9. `data/constituents/sp500_constituents_daily.parquet`

The constituent table: one row per issuer per trading day, priced and weighted. This is the
only input breadth features may read. 1.56M rows, 2014-06-02 -> 2026-11-17.

| column | dtype | meaning |
|---|---|---|
| `date` | datetime64[ns] | trading day |
| `index_name` | string | `SP500` - kept as a column so other indices can join later |
| `issuer_id` | string | stable company key; share classes are already collapsed |
| `name` | string | issuer name from the active filing |
| `ticker` | string/null | null when the mapping failed or the row was excluded |
| `close` | float/null | split-adjusted price on that day |
| `open`, `high`, `low` | float/null | split-adjusted, from the same price file |
| `adj_close` | float/null | total-return series |
| `volume` | int64/null | shares traded; `volume x close` = `turnover_value` |
| `index_weight` | float | share of the index, from the active filing |
| `coverage_names` | float | % of that day's constituents with a price |
| `coverage_weight` | float | % of index weight with a price |
| `weighted_ok` | bool | `coverage_weight >= 80` |
| `equal_weight_ok` | bool | `coverage_names >= 80` |
| `days_since_filing` | int | calendar days since the governing filing was published |

Grain: `(date, issuer_id)`. Key for joining prices: `(date, ticker)`.

### Point-in-time rule

Membership and weights come from the most recent filing whose `available_at` is on or before
`date`. A June 30 filing lands in late August, so from July 1 to August 28 the table still
carries the March 31 list. `days_since_filing` makes that visible instead of hiding it.

### Reading the coverage columns

`coverage_names` and `coverage_weight` answer different questions. If a snapshot is missing
NVIDIA, name coverage barely moves and weight coverage drops 7.5 points.

Each measure is gated on its own denominator, both at 80%:

| measure | gate | readable from |
|---|---|---|
| weighted breadth | `coverage_weight >= 80` | 2014-12-01 |
| equal-weight breadth | `coverage_names >= 80` | 2018-05-29 |

Weight coverage recovers years before name coverage does, because the names Yahoo lost are
mostly small. A stricter 90% subset can be filtered from the same columns when a cleaner
reading is wanted; it is not the default.

### Asset classification

`asset_cat` and `payoff_profile` come from N-PORT and gate the universe: only `EC` rows reach
this table. SPY's filings are 14,117 `EC` rows and one `DE` — a Hologic contingent value
right worth $25,786 — which is dropped here. Pre-2019 filings (N-30D) carry no tags, so those
rows pass unfiltered.

### Weight semantics

`index_weight` is the security's share of the index as reported by the fund, summing to 100
per date across all constituents, priced or not. Weighted breadth divides by the weight of
the *priced* subset, which renormalises implicitly, so no second weight column is stored.
