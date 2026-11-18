# Excluded holdings

`config/exclusions.csv` lists the 15 holdings whose ticker could not be reconciled with the
price the fund reported. This page explains each one, so an exclusion can be audited
instead of taken on trust.

## Why a row can be excluded

The reconciliation in [verify.py](../breadth/verify.py) computes, for every holding:

```
reported_price = holding_value / shares          # what the fund says it was worth per share
market_price   = close x split_factor            # what the market says it traded at
ratio          = reported_price / market_price
```

A correct ticker gives `ratio = 1.00`. A ratio outside `0.90 - 1.10` means one of:

1. **The ticker changed hands.** The symbol now belongs to a different company, so the
   price series is the wrong company's. (`IR`, `CB`, `AVGO`)
2. **Two share classes were mapped to one ticker.** Both classes are present in the filing,
   but the name lookup sent both to the same symbol, and the classes trade at different
   prices. (`UAA` Class C)
3. **The split list is wrong.** The company is right and the ticker is right, but a
   corporate action in Yahoo's list was never applied to its price series. (`ADP`)

Only case 1 and 2 are data problems in this project. Case 3 is an upstream inconsistency,
kept in the file so it can be revisited.

## What happens to an excluded row

The row stays in `data/mapped/` with its `holding_value`, `shares` and `weight` intact,
because dropping it would silently shrink the breadth denominator. Only the ticker is
cleared:

```
excluded      = True
ticker        = NA
ticker_source = "excluded"
unresolved    = True
```

It therefore carries weight in the index but cannot produce a price signal. That is the
honest outcome: we know it was held, we do not know which price series it belongs to.

## The 15 rows

Snapshot of `config/exclusions.csv` on 2026-11-18. The CSV is the source of truth.

| period | holding | ticker | ratio | reason | what happened |
|---|---|---|---|---|---|
| 2014-09-30 | Broadcom Corp. (Class A) | AVGO | 0.46 | ticker reuse | Broadcom Corp. (BRCM) was acquired by Avago in 2016; the merged company took the name Broadcom and the symbol **AVGO**. Yahoo's AVGO history is Avago's, roughly 2x the price of BRCM. |
| 2015-03-31 | Broadcom Corp. (Class A) | AVGO | 0.34 | ticker reuse | same |
| 2015-09-30 | Broadcom Corp. (Class A) | AVGO | 0.41 | ticker reuse | same |
| 2014-09-30 | Chubb Corp | CB | 0.87 | ticker reuse | Chubb Corp was acquired by ACE Ltd in 2016; ACE renamed itself **Chubb Ltd** and kept **CB**. Pre-2016 CB rows are the old Chubb, but the series is ACE's. |
| 2015-09-30 | Chubb Corp | CB | 1.19 | ticker reuse | same — the ratio is above 1 here because the two share prices crossed during the merger year |
| 2017-09-30 | Ingersoll-Rand PLC | IR | 3.24 | ticker reuse | Ingersoll-Rand plc merged with Gardner Denver in 2020; the combined company took the name **Ingersoll Rand Inc** and the symbol **IR**. Yahoo's IR history backfills with Gardner Denver's ~$28-36 prices against IR plc's ~$90-133. |
| 2018-03-31 | Ingersoll-Rand PLC | IR | 2.79 | ticker reuse | same |
| 2018-09-30 | Ingersoll-Rand PLC | IR | 3.65 | ticker reuse | same |
| 2019-03-31 | Ingersoll-Rand PLC | IR | 3.86 | ticker reuse | same |
| 2019-09-30 | Ingersoll-Rand PLC | IR | 4.36 | ticker reuse | same |
| 2019-12-31 | Ingersoll-Rand PLC | IR | 3.62 | ticker reuse | same |
| 2016-09-30 | Under Armour, Inc. Class C | UAA | 0.88 | share class | Under Armour files two classes: **UAA** (Class A) and **UA** (Class C). Both rows are named "Under Armour, Inc.", so both resolved to UAA. Class C trades ~10-12% below Class A, which is exactly the gap. |
| 2018-03-31 | Under Armour, Inc. Class C | UAA | 0.88 | share class | same |
| 2019-03-31 | Under Armour, Inc. Class C | UAA | 0.89 | share class | same |
| 2014-09-30 | Automatic Data Processing, Inc | ADP | 0.88 | split list | ADP spun off CDK Global on 2014-10-01. Yahoo's split list records a `1.139` ratio for it, but its ADP price series was never adjusted. Our factor therefore over-adjusts by 13.9% for the one period immediately before the spin. The holding and the ticker are correct. |

Three of these are `share_class` and the rest are labelled `unexplained` by the generator,
because it cannot tell ticker reuse from a bad split entry automatically. The table above is
that human step.

## Why not just drop them

- `AVGO`, `CB`, `IR`: the issuer is still represented in later periods under the new
  company, so nothing is lost from breadth — only the mislabelled years are muted.
- `UAA` Class C: its Class A sibling keeps the issuer in the denominator for those periods.
- `ADP`: the holding is real and its weight matters; only our price series is unreliable.

Excluding the row rather than the ticker matters: `AVGO` in 2026 is a valid holding, and
dropping the ticker outright would remove 2.8% of the index.

## Residual risk

The test only proves *price agreement*, not correctness of identity. A ticker that happens
to trade near the held company's price would pass. That risk is small (the 15 failures were
all far outside tolerance) but it is not zero, and it is why the reconciliation compares
levels rather than trusting name matching.

## Reproducing and reviewing

```bash
uv run python -m breadth.exclusions   # regenerate config/exclusions.csv
uv run python -m breadth.holdings     # apply it to data/mapped/
uv run pytest -q                      # enforces that nothing priced is off by >10%
```

The generator rewrites the file from scratch each run. If a new row appears, it will show up
with its ratio and an `unexplained` label — look at the implied price versus the market
price before accepting it, then add the explanation above.
