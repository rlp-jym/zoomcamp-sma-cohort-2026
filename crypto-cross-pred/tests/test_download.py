"""Archive parsing and URL construction, on synthetic payloads."""

from datetime import UTC, date, datetime

import pandas as pd

from crypto_cross_pred.data import download

KLINE_LINE = (
    "1609459200000,28948.19,29055.00,28706.00,29015.00,8037.588,1609462799999,"
    "232164597.07348,65942,3983.842,115131176.76487,0"
)


def test_month_range_is_inclusive() -> None:
    assert download.month_range(date(2021, 1, 15), date(2021, 4, 2)) == [
        "2021-01",
        "2021-02",
        "2021-03",
        "2021-04",
    ]


def test_month_range_crosses_the_year_boundary() -> None:
    assert download.month_range(date(2024, 11, 1), date(2025, 2, 1)) == [
        "2024-11",
        "2024-12",
        "2025-01",
        "2025-02",
    ]


def test_day_range_is_inclusive() -> None:
    assert download.day_range(date(2025, 1, 1), date(2025, 1, 3)) == [
        "2025-01-01",
        "2025-01-02",
        "2025-01-03",
    ]


def test_archive_urls() -> None:
    assert download.archive_url("klines", "BTCUSDT", "2021-01").endswith(
        "/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip"
    )
    assert download.archive_url("funding", "BTCUSDT", "2021-01").endswith(
        "/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2021-01.zip"
    )
    assert download.archive_url("metrics", "BTCUSDT", "2021-01-04").endswith(
        "/daily/metrics/BTCUSDT/BTCUSDT-metrics-2021-01-04.zip"
    )


def test_parse_klines_without_header() -> None:
    frame = download.parse_klines_csv([KLINE_LINE])

    assert list(frame.columns) == [
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_volume",
        "taker_buy_quote_volume",
        "trades",
    ]
    assert frame["ts"].iloc[0] == pd.Timestamp("2021-01-01T00:00Z")
    assert frame["close"].iloc[0] == 29015.00
    assert frame["trades"].iloc[0] == 65942


def test_parse_klines_with_header() -> None:
    header = ",".join(download.KLINE_COLUMNS)

    frame = download.parse_klines_csv([header, KLINE_LINE])

    assert len(frame) == 1


def test_parse_funding() -> None:
    frame = download.parse_funding_csv(
        ["calc_time,funding_interval_hours,last_funding_rate", "1609459200002,8,0.00022753"]
    )

    assert frame["funding_rate"].iloc[0] == 0.00022753
    assert frame["ts"].iloc[0] == pd.Timestamp("2021-01-01T00:00:00.002Z")


def test_parse_metrics_deduplicates_rows() -> None:
    header = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,"
        "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
        "count_long_short_ratio,sum_taker_long_short_vol_ratio"
    )
    row = "2021-01-04 00:00:00,BTCUSDT,33787.33,1116826744.32,1.89,1.20,2.01,1.12"

    frame = download.parse_metrics_csv([header, row, row])

    assert len(frame) == 1
    assert "create_time" not in frame.columns
    assert frame["open_interest"].iloc[0] == 33787.33


def test_metrics_are_aggregated_to_hourly() -> None:
    header = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,"
        "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
        "count_long_short_ratio,sum_taker_long_short_vol_ratio"
    )
    rows = [
        f"2021-01-04 00:{minute:02d}:00,BTCUSDT,{minute},{minute * 10},1,1,1,1"
        for minute in range(0, 60, 5)
    ]
    rows.append("2021-01-04 01:00:00,BTCUSDT,999,9990,1,1,1,1")

    frame = download.parse_metrics_csv([header, *rows])

    assert len(frame) == 2
    assert frame["ts"].tolist() == [
        pd.Timestamp("2021-01-04T00:00Z"),
        pd.Timestamp("2021-01-04T01:00Z"),
    ]
    # the last snapshot inside the hour wins
    assert frame["open_interest"].tolist() == [55, 999]


def test_empty_payloads_return_empty_frames() -> None:
    assert download.parse_klines_csv([]).empty
    assert download.parse_funding_csv([]).empty
    assert download.parse_metrics_csv([]).empty


def test_clamp_end_never_passes_the_study_boundary() -> None:
    boundary = date(2026, 10, 31)

    assert download.clamp_end(datetime(2026, 12, 15, tzinfo=UTC), boundary) == datetime(
        2026, 10, 31, 23, 59, 59, 999999, tzinfo=UTC
    )
    assert download.clamp_end(datetime(2026, 10, 20, tzinfo=UTC), boundary) == datetime(
        2026, 10, 20, tzinfo=UTC
    )


def test_clamp_end_without_a_boundary_is_a_noop() -> None:
    now = datetime(2026, 12, 15, tzinfo=UTC)
    assert download.clamp_end(now, None) is now
