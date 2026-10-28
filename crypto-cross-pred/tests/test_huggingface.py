"""Hugging Face helpers: argument construction, not network calls."""

from pathlib import Path

import pytest

from crypto_cross_pred import config
from crypto_cross_pred.io import huggingface


def _settings(tmp_path: Path, repo: str = "") -> config.Settings:
    return config.Settings(
        paths=config.PathsConfig(
            data_dir=tmp_path,
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
            predictions_dir=tmp_path / "predictions",
            sim_dir=tmp_path / "sim",
            artifacts_dir=tmp_path / "artifacts",
        ),
        hf_dataset_repo=repo,
    )


def test_repo_id_requires_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HF_DATASET_REPO"):
        huggingface.repo_id_from(_settings(tmp_path))


def test_repo_id_is_trimmed(tmp_path: Path) -> None:
    assert huggingface.repo_id_from(_settings(tmp_path, "  me/data  ")) == "me/data"


def test_raw_is_never_published() -> None:
    assert not any(pattern.startswith("raw") for pattern in huggingface.DATA_PATTERNS)


def test_pull_requests_only_the_published_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def fake_snapshot(**kwargs):
        captured.update(kwargs)
        return str(tmp_path)

    monkeypatch.setattr(huggingface, "snapshot_download", fake_snapshot)

    huggingface.pull_data(tmp_path, repo_id="me/data")

    assert captured["repo_id"] == "me/data"
    assert captured["repo_type"] == "dataset"
    assert captured["allow_patterns"] == list(huggingface.DATA_PATTERNS)
    assert captured["token"] is None


def test_push_creates_the_repo_and_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}

    class FakeApi:
        def __init__(self, token: str) -> None:
            calls["token"] = token

        def create_repo(self, repo_id: str, **kwargs) -> None:
            calls["create"] = (repo_id, kwargs)

        def upload_folder(self, **kwargs) -> None:
            calls["upload"] = kwargs

    monkeypatch.setattr(huggingface, "HfApi", FakeApi)
    directory = tmp_path / "predictions"
    directory.mkdir()

    huggingface.push_directory(directory, "me/data", token="hf_x", path_in_repo="predictions")

    assert calls["token"] == "hf_x"
    assert calls["create"][0] == "me/data"
    assert calls["upload"]["path_in_repo"] == "predictions"
    assert calls["upload"]["repo_type"] == "dataset"
