"""The dashboard must render with no artifacts, and without raising."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_app_renders_with_empty_artifacts() -> None:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    assert not app.exception
    assert len(app.tabs) == 4
    assert len(app.info) == 3  # dataset, predictions and simulation empty states
