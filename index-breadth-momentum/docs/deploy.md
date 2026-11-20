# Deployment: the daily signal

The model does not need a web app. Once a day, after the close, it produces one
line: own SPY or sit in cash. This directory runs that, and pushes it to Telegram.

## Pipeline

```
deploy/main.py
  |
  +-- data_repo.load_base()      cached release table, downloaded once
  +-- data_repo.download_prices  daily bars for the current ~500 constituents
  +-- data_repo.extend_base()    overwrite recent prices, append new sessions
  +-- transform.build_frame()    the same features as notebook.ipynb
  +-- train.fit() / load()       random forest, joblib in local_data/
  +-- predict the latest row     expected R, tree vote share, sizing
  +-- notify.send()              Telegram, with local_data/signal.log as fallback
```

Every stage has a `load`/`persist` pair under `local_data/`, so a rerun can skip
the network (`--offline`) or the fit (`--skip-train`).

## Commands

```bash
python -m deploy.main                    # refresh, retrain, alert
python -m deploy.main --skip-train       # daily path: reuse the saved model
python -m deploy.main --offline          # no network, cached data only
python -m deploy.main --dry-run          # print the alert, do not send
python -m deploy.main --dry-run --offline  # preview in seconds
python -m deploy.notify                  # send a fixed sample message
```

On Windows the same thing is `run_daily.bat`, which logs to `local_data/run.log`.
For a preview that sends nothing, double-click `run_signal_preview.bat`.

## Telegram setup

A bot can only message the account that started it, and its token is a secret, so
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are never committed. Each machine
supplies its own.

1. Message **@BotFather**, send `/newbot`, choose a name; it replies with a token.
2. Send any message to your new bot (it cannot message you first).
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy
   `"chat":{"id": ...}`.
4. Copy `.env.example` to `.env` and fill both values.
5. `python -m deploy.notify` should arrive on your phone.

If the token is missing or the API call fails, the message is only written to
`local_data/signal.log`; the job never fails because of the alert.

### Verification status

| piece | state |
|---|---|
| token handshake (`getMe`) | verified |
| refresh → features → train → infer | verified, 2,888 rows to 2026-11-20 |
| Task Scheduler entry at 03:00 Mon-Fri | registered and test-run |
| alert rendering (`--dry-run`) | verified |
| Telegram delivery | **requires your chat id** |

Everything except the final delivery is reproducible without a Telegram account:
`python -m deploy.main --dry-run` prints the message, and the job writes
`local_data/latest_signal.json`.

## Schedule

Windows Task Scheduler, weekdays at 03:00: double-click `setup_task.bat`. It
calls `setup_task.ps1`, which registers:

```
Task name : IndexBreadthDailySignal
Runs      : cmd.exe /c "<repo>\index-breadth-momentum\run_daily.bat"
When      : 03:00, MON-FRI
```

Handy commands:

```bat
schtasks /Run /TN "IndexBreadthDailySignal"        :: run it now
schtasks /Query /TN "IndexBreadthDailySignal" /V   :: confirm it is scheduled
schtasks /Delete /TN "IndexBreadthDailySignal" /F  :: remove it
```

The `schtasks /Create /TR` form is easy to get wrong with quoted paths; the
PowerShell file is the reliable version.

On a Linux host:

```cron
0 3 * * 1-5 /path/to/uv run --project /path/to/repo python -m deploy.main --skip-train >> /path/to/local_data/run.log 2>&1
```

03:00 is before the US open and after the previous close, so the signal uses
strictly completed sessions.

## The message

```
Index Breadth Momentum Alert
2026-11-20 18:13 EST
Action: BUY

Model output
Score: +0.37R - predicted 5-day move, threshold +0.00R
Expectancy: 0.14R - avg R on 510 validation days above threshold
Probability of gain: 0.62 - share of the 300 trees expecting a gain

Top drivers
med_atr_pct_60d: 2.93% - median 60-day ATR across constituents
breadth_sma_5d_chg_5d: -51.9pp - 5-day change in 5-day breadth
breadth_rsi30_20d: 17% - weighted share with RSI below 30, 20-day

Risk at 1.77% ATR
0.25% risk -> 14% equity
0.50% risk -> 28% equity
1.00% risk -> 57% equity

Data through 2026-11-20
```

- **Action** is BUY when the score is above the threshold, SELL when it drops
  below after being long, and WAIT when it is below and already in cash.
- **Score** is the forest's predicted 5-day move in ATR units; the threshold is
  `SIGNAL_THRESHOLD`, default 0.
- **Probability of gain** is the share of the 300 trees predicting a positive
  5-day return. A regression does not produce a probability; this is the honest
  substitute and is labelled as such.
- **Expectancy** is measured on the validation slice, on days above the same
  threshold, so it moves with the signal.
- **Top drivers** are the three features with the highest importance in the
  fitted forest, with their value for this session. They are inputs the model
  actually uses, not a fixed shortlist.
- **Sizing** is `risk / ATR%` of equity, capped at 100% until leverage is
  deliberately enabled. The header states the SPY ATR the sizes are based on;
  at 1.77% ATR, 1% risk is 57% of equity.

## Known limits

- **Weights are frozen between filings.** New sessions reuse the last EDGAR
  snapshot's index weights. Holdings change slowly, but a big index event will
  not be reflected until the next filing arrives.
- **Prices are daily, not intraday.** The signal is for the next session.
- **yfinance is the weak link.** Batches sometimes return an incomplete final
  day; SPY is retried, and the job warns when SPY and breadth disagree on the
  last date.
- **No transaction costs in the live sizing.** The study charged 0.005R per
  trade; the alert reports gross sizing.
- **Pre-tax.** Neither the strategy nor the 7% benchmark is tax-adjusted.
