# Experiments — append-only run log

**Status: pre-registered.** Everything above the run table was written before the first
modelling run and is not edited afterwards. If a criterion turns out to be wrong, it is
superseded in a new section with a date and a reason — the original stays.

Protocol: [docs/SPEC.md](docs/SPEC.md) §3. Decisions behind it:
[docs/DECISIONS.md](docs/DECISIONS.md) (D-22…D-32).

---

## 1. Hypothesis

**Derivatives positioning carries cross-sectional information at a 24-hour horizon.**

At any given hour, the funding rate, open interest, long/short ratios and liquidation
flows of a perpetual contract describe how crowded a position is. Crowded positioning
should mean-revert: the most crowded longs underperform, the most crowded shorts
outperform, relative to the cross-section of the same hour.

The tradable expression is a market-neutral book: long the symbols with the most
favourable predicted excess return, short the least favourable, rebalanced daily.

This is testable and falsifiable. It is not a claim that the strategy is profitable, and
profitability is not the success criterion.

## 2. Primary success criterion

Verbatim from [docs/SPEC.md](docs/SPEC.md) §3.5:

> The derivatives-positioning hypothesis is **supported** only if the sealed holdout shows
> rank IC ≥ 0.02 with t-stat ≥ 2 **and** sim3 net Sharpe > 0 after 6 bps round-trip.
> Otherwise the verdict is **falsified** (adequate power, no effect) or **inconclusive**
> (below minimum detectable effect, or costs dominate).

Evaluated **once**, on the sealed holdout (2025-11 → 2026-10), after all choices are frozen.

| Verdict | Meaning |
|---|---|
| Supported | Both parts of the criterion met on the holdout |
| Falsified | Adequate power, no effect — the idea is dead |
| Inconclusive | Below minimum detectable effect, or costs dominate — the idea is untested |

## 3. Secondary test

`sim0` (funding-carry rule, no model) is the floor. The ML strategy is **additive** only if
`sim3` beats `sim0` on net Sharpe. Reported next to the verdict; it does not change it.

## 4. Plausibility guardrails

Expected ranges for 24h cross-sectional crypto prediction. A result outside the plausible
range triggers a **leakage audit before** any interpretation (D-27).

| Metric | Plausible | Investigate |
|---|---|---|
| Rank IC (dev OOS) | 0.01 – 0.05 | > 0.10 |
| Net Sharpe (sim3) | 0 – 2 | > 3 |
| Precision@top-decile | 0.20 – 0.30 | > 0.45 |

A Sharpe above 3 on a market-neutral crypto book is a bug until proven otherwise.

## 5. Minimum detectable effect

Filled in by the power check (TASKS P3-08), **before** the first modelling run:

| Quantity | Value |
|---|---|
| Universe size | _pending_ |
| Dev-period months | _pending_ |
| Minimum detectable rank IC | _pending_ |
| Is the §2 criterion achievable? | _pending_ |

If the criterion is not achievable at this sample size, the hypothesis is revised here
before modelling — not after seeing results.

## 6. Run log

One row per run. A run without a stated reason is not a valid run (SPEC §3.2).

| run_id | date | change | reason | dev OOS metric | verdict | keep/drop |
|---|---|---|---|---|---|---|

## 7. Rules of the log

- **Append only.** Never edit or delete a past row, even when it was a mistake.
- **Two-strike rule:** an idea that fails twice is dropped with a one-line reason (D-28).
- **No tuning toward a number**, including toward profitability.
- The power check, the config-swap rerun (P9-08) and the final holdout evaluation all get
  rows here.
