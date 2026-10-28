# Cross-Sectional Return Prediction for Crypto Futures

> Placeholder README. The design is in [docs/SPEC.md](docs/SPEC.md), the reasoning behind it
> in [docs/DECISIONS.md](docs/DECISIONS.md), and the build plan in
> [docs/TASKS.md](docs/TASKS.md).

## The problem

Crypto futures markets trade hundreds of contracts around the clock. Most tools and
commentary reduce the question to a single market call: is crypto going up or down?

That framing leaves out the more useful question. On any given day, some contracts do
better than others. The interesting problem is not the direction of the whole market, but
**which contracts are likely to outperform or underperform the rest over the next day**.

This project works on exactly that question: given what is observable at a point in time,
rank the available contracts by their expected performance relative to each other.

## Why it matters

- **Relative instead of absolute.** A ranking stays useful when the overall market is flat
  or falling. It supports decisions that do not depend on guessing where the whole market
  is headed.
- **A reusable method, not a one-off answer.** The work is structured so the market, the
  time horizon, and the cost assumptions can be changed without rebuilding it. The crypto
  case is the first instance, not the only intended one.
- **Honest measurement.** Results are compared against simple alternatives, so the outcome
  can be judged on evidence rather than on a claim.
- **Runs unattended.** The process refreshes with new data and publishes its output daily,
  so the result stays current rather than becoming a one-off analysis.

## How results are judged

Work like this is usually reported as either a win or a failure. This project uses three
outcomes instead:

- **Supported** — the evidence held up on data the model never saw.
- **Falsified** — the test was strong enough to find an effect and found none. The idea is
  closed, written down, and the next one starts.
- **Inconclusive** — the test was too weak, or the costs too large, to decide. Said plainly
  rather than dressed up as a result.

Every attempt is recorded, including the ones that did not work. A negative result is a
finished result when it removes a hypothesis from the table.

## Who it is for

- **Learners** who want to see a project carried from raw data to a reproducible result.
- **Reviewers** who want to check the reasoning and reproduce it.
- **Anyone building something similar** who wants a starting point they can adapt.

## Scope

The project covers one market, one time horizon, and one style of decision. It is a study,
not investment advice, and it does not trade real money.

## Design and decisions

- [docs/SPEC.md](docs/SPEC.md) — what the system must do
- [docs/DECISIONS.md](docs/DECISIONS.md) — why, including the alternatives rejected
- [docs/TASKS.md](docs/TASKS.md) — the build plan

## How this was built

The design and decisions are mine. Implementation is done with AI coding agents, as a
deliberate application of the workflow from the AI Dev Tools Zoomcamp: write the spec
first, record the decisions, break the work into verifiable tasks, and give the agent
explicit rules. The full trail — including the pivots and the options that were rejected —
is in [docs/DECISIONS.md](docs/DECISIONS.md).

## Status

Phase 0 (scaffold) is complete: `uv` project, package tree, typed config, CLI stubs,
contracts module, tests, CI, and the notebook export path. Data acquisition starts at
Phase 1. See [docs/TASKS.md](docs/TASKS.md) for the live task board.
