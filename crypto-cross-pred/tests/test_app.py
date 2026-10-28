"""The dashboard must render with no artifacts, and without raising."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from crypto_cross_pred import config

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def _empty_config(tmp_path: Path) -> Path:
    """A config whose data directories are empty and outside the repo."""
    path = tmp_path / "config.yaml"
    root = tmp_path.as_posix()
    path.write_text(
        "paths:\n"
        f"  data_dir: {root}/data\n"
        f"  raw_dir: {root}/data/raw\n"
        f"  processed_dir: {root}/data/processed\n"
        f"  predictions_dir: {root}/data/predictions\n"
        f"  sim_dir: {root}/data/sim\n"
        f"  artifacts_dir: {root}/data/artifacts\n",
        encoding="utf-8",
    )
    return path


def test_app_renders_with_empty_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTO_CONFIG_FILE", str(_empty_config(tmp_path)))
    config.get_settings.cache_clear()
    try:
        app = AppTest.from_file(APP, default_timeout=60)
        app.run()

        assert not app.exception
        assert len(app.tabs) == 4
        assert len(app.info) == 3  # dataset, predictions and simulation empty states
    finally:
        config.get_settings.cache_clear()
