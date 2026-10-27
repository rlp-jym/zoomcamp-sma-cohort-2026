# AGENTS.md — Working rules for this project

Project-scoped guidance for AI coding agents (and humans) working in `crypto-cross-pred/`.

Read in this order: **docs/SPEC.md** (what and why) → **docs/DECISIONS.md** (why not something
else) → **docs/TASKS.md** (what's next) → this file (how).

---

## 1. Golden rules

1. **Free tools only.** No paid API, no paid host, no credit card. If a task seems to need
   one, stop and propose a free alternative.
2. **Never commit data.** No parquet, CSV, or model binaries in git. Data lives on
   Hugging Face Datasets. `data/` is gitignored.
3. **Never leak the future.** Any feature computed with `shift(-n)`, a global mean, or a
   fit on the full dataset is a bug. See docs/SPEC.md §6.
4. **Never touch the sealed holdout.** It is loaded exactly once, by the final run
   (docs/SPEC.md §3.1). No feature, hyperparameter, or threshold may be chosen from it.
5. **Log every run.** Each modelling or simulation run gets a row in `experiments.md` with
   its reason and result. A run without a logged reason is not a valid run (docs/SPEC.md §3.3).
6. **Do not silently reverse a decision** in docs/DECISIONS.md. If a decision looks wrong,
   write the concern down and ask; supersede it with a new row rather than editing history.
7. **One stage at a time.** Finish and verify a stage before starting the next. The build
   order in docs/TASKS.md is intentional.
8. **Specs are the source of truth.** If code and specs disagree, the specs win unless the
   user approves a change — then update docs/SPEC.md and docs/DECISIONS.md in the same commit.

---

## 2. Environment and commands

The project is a **standalone `uv` project** rooted at `crypto-cross-pred/` (separate from the
homework `pyproject.toml` at the repo root). Python 3.12+.

```bash
cd crypto-cross-pred
uv sync                      # install runtime deps
uv sync --all-groups         # include dev + app + bonus groups
uv run python -m crypto_cross_pred.cli --help
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
```

Pipeline entry points (target shape):

```bash
uv run python -m crypto_cross_pred.cli download  --source binance --since 2021-01-01
uv run python -m crypto_cross_pred.cli transform
uv run python -m crypto_cross_pred.cli train
uv run python -m crypto_cross_pred.cli predict
uv run python -m crypto_cross_pred.cli simulate
uv run python -m crypto_cross_pred.cli notify
uv run python -m crypto_cross_pred.cli all --source hf
```

Streamlit app: `uv run streamlit run app/streamlit_app.py`

---

## 3. Where things live

| Concern | Path |
|---|---|
| Settings / paths / thresholds | `src/crypto_cross_pred/config.py` + `config/config.yaml` |
| HTTP clients, retries, pagination | `src/crypto_cross_pred/io/binance.py` |
| FRED macro series (1-day lag) | `src/crypto_cross_pred/io/fred.py` |
| HF Datasets read/write | `src/crypto_cross_pred/io/huggingface.py` |
| Local parquet cache helpers | `src/crypto_cross_pred/io/storage.py` |
| Raw → unified schema | `src/crypto_cross_pred/data/transform.py` |
| Feature engineering | `src/crypto_cross_pred/data/features.py` |
| Labels / targets | `src/crypto_cross_pred/data/labels.py` |
| Purged walk-forward | `src/crypto_cross_pred/models/validate.py` |
| Optuna tuning | `src/crypto_cross_pred/models/tuning.py` |
| Train / predict | `src/crypto_cross_pred/models/train.py`, `predict.py` |
| Vector sims | `src/crypto_cross_pred/sim/vector.py` |
| Exact iterative sim | `src/crypto_cross_pred/sim/exact.py` |
| Metrics / benchmarks | `src/crypto_cross_pred/sim/metrics.py` |
| Plots, Telegram, broker | `src/crypto_cross_pred/report/` |
| Research notebooks | `notebooks/` |
| Public app | `app/streamlit_app.py` |
| Run log (append-only) | `experiments.md` |

---

## 4. Contracts

These are load-bearing. Changing them breaks notebooks, the app, and CI.

- **Unified schema:** exactly the columns in docs/SPEC.md §4.2. Add new columns by updating
  docs/SPEC.md first.
- **Feature sets:** `TO_PREDICT_REG`, `TO_PREDICT_CLF`, `NUMERIC`, `DUMMIES`, `CATEGORICAL`
  are defined in **one** module and imported everywhere. Never redefine them in a notebook.
- **Artifact paths:** `raw/{source}/{symbol}.parquet`,
  `processed/dataset_{YYYY-MM-DD}.parquet`, `predictions/{YYYY-MM-DD}.parquet`,
  `sim/{strategy}_{YYYY-MM-DD}.parquet`.
- **Time:** all timestamps UTC, timezone-aware, never naive.
- **Macro lag:** FRED series are shifted 1 day before joining. A same-day macro value at an
  hourly timestamp is a bug, not a feature.

---

## 5. Coding conventions

- Type hints on public functions; docstrings state the expected dataframe columns.
- Pure functions for feature/label logic — no I/O inside them, so they're testable.
- No hidden global state; configuration comes from `config.py`.
- Prefer `pandas` + `numpy`; `duckdb` is available for large scans.
- Log with `logging`, not `print`, in `src/`. `tqdm` for long loops.
- Fail loudly on schema violations (missing columns, duplicate `(symbol, ts)` keys).
- Keep `src/` free of notebook-only imports (`matplotlib` inline magic, etc.).

---

## 6. Notebook policy

Notebooks are **research and demonstration only**. Every piece of logic they need must
already exist in `src/`. A notebook cell should look like:

```python
from crypto_cross_pred.data.features import build_features
from crypto_cross_pred.models.train import fit_model
```

If you're about to write a 30-line function inside a notebook, it belongs in `src/` first.
Each notebook must be exportable to a `.py` script (rubric 6.1).

---

## 7. Secrets

Never hardcode or commit. Read from environment:

| Variable | Used by |
|---|---|
| `HF_TOKEN` | dataset upload |
| `HF_DATASET_REPO` | dataset target |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET` | testnet orders only |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | alerts |

`.env.example` documents names with empty values. `.env` is gitignored.
In CI, values come from GitHub Actions secrets.

FRED needs no key when read through `pandas-datareader`. If `fredapi` is used instead,
add `FRED_API_KEY` here and to `.env.example`.

---

## 8. Definition of done

A task is done when:

- [ ] Code runs end-to-end via the CLI (no manual notebook step required)
- [ ] `ruff check` and `pytest` pass
- [ ] No leakage: features `<= t`, labels `> t`, scaling/target-encoding fit inside the fold
- [ ] Outputs written to the documented artifact path
- [ ] Logs/report include a sanity metric (row counts, date range, NaN rate)
- [ ] Relevant doc updated (docs/SPEC.md for requirements, docs/DECISIONS.md for rationale,
      docs/TASKS.md for status, `experiments.md` for the run, README for usage)
- [ ] Task marked complete in `docs/TASKS.md` with its short commit hash

---

## 9. Git workflow

**Branches**

1. **Work on `develop`.** Commit frequently and push to `develop` as work progresses.
2. **Never push to `main` unless explicitly asked.** `main` only receives merges from
   `develop`, and only on request. Never commit directly to `main`.
3. **Never amend or force-push a pushed commit.** Fix forward with a new commit.

**Commits**

4. **Message format:** `<TASK-ID>: <imperative summary>` — e.g. `P1-03: add bulk klines
   backfill`. Batch a coherent set when it helps: `P2-03,P2-04: add feature families`.
5. **One task or one coherent batch per commit.** Do not mix a refactor with a feature.
6. **Record the hash in a follow-up commit.** The commit that completes a task cannot
   contain its own hash. The next commit updates the Commit column in `docs/TASKS.md`
   with the short hash (7 chars). Several commits: `a1b2c3d, e4f5g6h`.

**Verification — keep it cheap**

7. **Every commit:** check `git status` — no data files, no `.env`, no secrets.
8. **Touching feature or label code:** run `uv run pytest -q tests/test_no_leakage.py`.
9. **Do not block commits on the full suite.** CI is the gate for `main`, not for
   `develop`. Push and let CI verify.

**Completion**

10. **Mark a task complete only after its "Done when" is verified**, updating the status
    and the Commit column together.
11. **Tag the submission:** `v1.0-submission` on `main` when the project is handed in.

**Not doing:** conventional-commit prefixes (the task ID already does that), a branch per
task, signed commits.

---

## 10. When unsure

Ask before: changing the schema, changing the validation scheme, adding a dependency that
isn't free, deleting existing work, or expanding scope beyond docs/SPEC.md §12.
