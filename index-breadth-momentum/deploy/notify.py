"""Telegram alert, with a log fallback so a missing token never breaks the cron."""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import config

LOG_FILE = config.LOCAL / "signal.log"
STATE_FILE = config.LOCAL / "state.json"


def today_stamp() -> str:
    return datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M %Z")


def format_message(p: dict) -> str:
    size_lines = "\n".join(
        f"{risk:.2f}% risk -> {p['sizes'][risk]:.0f}% equity" for risk in config.RISK_LEVELS
    )
    drivers = "\n".join(
        f"{row['label']}: {row['value']} - {row['note']}" for row in p["drivers"]
    )
    return (
        "<b>Index Breadth Momentum Alert</b>\n"
        f"{p['stamp']}\n"
        f"Action: <b>{p['action']}</b>\n\n"
        "<b>Model output</b>\n"
        f"Score: {p['score']:+.2f}R - predicted 5-day move, threshold {p['threshold']:+.2f}R\n"
        f"Expectancy: {p['expectancy']:.2f}R - {p['expectancy_note']}\n"
        f"Probability of gain: {p['probability']:.2f} - {p['probability_note']}\n\n"
        "<b>Top drivers</b>\n"
        f"{drivers}\n\n"
        f"<b>Risk at {p['atr_pct']:.2f}% ATR</b>\n"
        f"{size_lines}\n\n"
        f"Data through {p['data_through']}"
    )


def _telegram(text: str) -> bool:
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT):
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=20)
        if r.status_code != 200:
            print(f"telegram error {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except Exception as exc:
        print(f"telegram failed: {exc}")
        return False


def send(payload: dict, dry_run: bool = False) -> None:
    text = format_message(payload)
    plain = text.replace("<b>", "").replace("</b>", "")

    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(plain + "\n\n")

    if dry_run:
        print(plain)
        return

    if _telegram(text):
        print("alert sent to Telegram")
    else:
        print("alert not sent (no token or API failure); written to local_data/signal.log")


def read_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"position": "CASH"}


def write_state(position: str, data_through: str) -> None:
    STATE_FILE.write_text(json.dumps({
        "position": position,
        "data_through": data_through,
        "written": today_stamp(),
    }, indent=1), encoding="utf-8")


def test_message() -> None:
    payload = {
        "stamp": today_stamp(),
        "action": "BUY",
        "score": 0.37,
        "threshold": 0.0,
        "expectancy": 0.21,
        "expectancy_note": "avg R on validation days above threshold",
        "probability": 0.58,
        "probability_note": "share of trees expecting a gain",
        "drivers": [
            {"label": "med_atr_pct_60d", "value": "1.82%", "note": "median 60-day ATR across constituents"},
            {"label": "breadth_rsi30_5d", "value": "12%", "note": "weighted share with RSI below 30"},
            {"label": "breadth_sma_20d", "value": "42%", "note": "weighted share above their 20-day average"},
        ],
        "atr_pct": 1.75,
        "sizes": {0.25: 14, 0.50: 29, 1.00: 57},
        "data_through": "2026-11-20",
    }
    send(payload, dry_run="--no-send" in sys.argv)


if __name__ == "__main__":
    test_message()
