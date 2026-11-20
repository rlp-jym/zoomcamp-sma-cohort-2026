"""Daily signal pipeline: fetch -> transform -> train -> infer -> alert.

    python -m deploy.main                 full run, refresh prices, retrain, send
    python -m deploy.main --skip-train    reuse local_data/model.joblib
    python -m deploy.main --dry-run       print the alert, do not call Telegram
    python -m deploy.main --offline       skip the network, use cached files
"""

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from . import config, data_repo, notify, train, transform


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Index breadth daily signal")
    p.add_argument("--offline", action="store_true", help="use cached data, no downloads")
    p.add_argument("--skip-train", action="store_true", help="reuse the saved model")
    p.add_argument("--force-train", action="store_true", help="retrain even if a model exists")
    p.add_argument("--dry-run", action="store_true", help="print instead of sending")
    return p.parse_args()


def refresh(base, spy, offline: bool):
    if offline:
        return base, spy

    _last, snap = data_repo.universe(base)
    print(f"refreshing {len(snap)} tickers ...")
    prices = data_repo.download_prices(snap["ticker"].tolist())
    if prices.empty:
        print("price refresh returned nothing; keeping the cached table")

    base = data_repo.extend_base(base, prices)
    spy = refresh_spy(spy, target=pd.to_datetime(base["date"]).max())
    data_repo.save_snapshot(base, prices, spy)
    return base, spy


def refresh_spy(spy, target, attempts: int = 3):
    """Recent SPY bars; providers sometimes lag a symbol, so retry before giving up."""
    import time

    import pandas as pd
    import yfinance as yf

    raw = None
    for attempt in range(1, attempts + 1):
        candidate = yf.download("SPY", period="3mo", auto_adjust=False, progress=False)
        if not candidate.empty:
            if hasattr(candidate.columns, "nlevels") and candidate.columns.nlevels > 1:
                candidate.columns = candidate.columns.get_level_values(0)
            candidate = candidate.reset_index()
            candidate.columns = [c.lower().replace(" ", "_") for c in candidate.columns]
            if pd.to_datetime(candidate["date"]).max() >= target:
                raw = candidate
                break
            raw = candidate
        print(f"  SPY refresh attempt {attempt} ended early, retrying ...")
        time.sleep(5)

    if raw is None or raw.empty:
        print("SPY refresh failed; using the cached series")
        return spy

    raw = raw[["date", "open", "high", "low", "close", "adj_close", "volume"]]
    raw["date"] = pd.to_datetime(raw["date"])
    spy = spy.copy()
    spy["date"] = pd.to_datetime(spy["date"])
    out = pd.concat([spy[spy["date"] < raw["date"].min()], raw], ignore_index=True)
    out = out.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
    if out["date"].max() < target:
        print(f"warning: SPY ends {out['date'].max().date()}, breadth ends {target.date()}")
    return out


def action_for(long_now: bool, previous: str) -> str:
    if long_now:
        return "BUY"
    return "SELL" if previous == "LONG" else "WAIT"


def main() -> None:
    args = parse_args()
    base = data_repo.load_base()
    spy = data_repo.load_spy()
    base, spy = refresh(base, spy, args.offline)

    print("building features ...")
    frame = transform.build_frame(base, spy)
    print(f"{len(frame)} rows, {frame.index.min().date()} -> {frame.index.max().date()}")

    model = None
    if not args.skip_train and (args.force_train or not train.MODEL_FILE.exists()):
        print("training ...")
        model, _ = train.fit(frame)
    else:
        print("loading model ...")
        model = train.load()

    row = frame.iloc[[-1]]
    pred = float(model.predict(row[config.FEATURES])[0])
    stats = train.segment_stats(model, frame)
    probability = train.vote_share(model, row)
    atr_pct = float(row["atr_20d_pct"].iloc[0])

    long_now = pred > config.THRESHOLD
    state = notify.read_state()
    action = action_for(long_now, state.get("position", "CASH"))

    sizes = {risk: min(100.0, risk / atr_pct * 100) for risk in config.RISK_LEVELS}
    stamp = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M %Z")
    data_through = frame.index.max().strftime("%Y-%m-%d")

    importance = sorted(zip(config.FEATURES, model.feature_importances_),
                        key=lambda kv: kv[1], reverse=True)[:3]
    drivers = [{
        "label": name,
        "value": transform.format_feature(name, float(row[name].iloc[0])),
        "note": config.FEATURE_NOTES.get(name, "model input"),
    } for name, _weight in importance]

    payload = {
        "stamp": stamp,
        "action": action,
        "score": pred,
        "threshold": config.THRESHOLD,
        "expectancy": stats["expectancy"],
        "expectancy_note": f"avg R on {stats['days']} validation days above threshold",
        "probability": probability,
        "probability_note": "share of the 300 trees expecting a gain",
        "drivers": drivers,
        "atr_pct": atr_pct,
        "sizes": sizes,
        "data_through": data_through,
    }

    print(f"predicted {pred:+.2f}R, action {action}")
    notify.send(payload, dry_run=args.dry_run)
    notify.write_state("LONG" if long_now else "CASH", data_through)

    signal = {
        "generated": stamp,
        "data_through": data_through,
        "action": action,
        "position": "LONG" if long_now else "CASH",
        "predicted_r": round(pred, 4),
        "threshold": config.THRESHOLD,
        "probability_up": round(probability, 3),
        "expectancy_r": round(stats["expectancy"], 4),
        "atr_20d_pct": round(atr_pct, 3),
        "sizes_pct": {str(k): round(v, 1) for k, v in sizes.items()},
    }
    (config.LOCAL / "latest_signal.json").write_text(json.dumps(signal, indent=1), encoding="utf-8")
    print("written:", config.LOCAL / "latest_signal.json")


if __name__ == "__main__":
    main()
