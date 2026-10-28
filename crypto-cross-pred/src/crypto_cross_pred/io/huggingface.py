"""Hugging Face Datasets: the system of record for everything except raw data.

Raw Binance archives stay local because they are re-derivable; ``processed/``,
``predictions/``, ``sim/`` and ``summary/`` are published. Reads are public, so the
deployed dashboard needs no token.

Credentials come from the environment only: ``HF_TOKEN`` (write) and
``HF_DATASET_REPO`` (target). See AGENTS.md section 7.
"""

from __future__ import annotations

import logging
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download

from crypto_cross_pred.config import Settings, get_settings

logger = logging.getLogger(__name__)

#: Published artifact families. ``raw/`` is deliberately absent.
DATA_PATTERNS: tuple[str, ...] = (
    "processed/*",
    "predictions/*",
    "sim/*",
    "summary/*",
)


def repo_id_from(settings: Settings | None = None) -> str:
    """Return the configured dataset repo, or raise a clear error."""
    settings = settings or get_settings()
    repo_id = settings.hf_dataset_repo.strip()
    if not repo_id:
        raise ValueError(
            "HF_DATASET_REPO is not set; export it or add it to .env (see .env.example)"
        )
    return repo_id


def push_directory(
    local_dir: Path,
    repo_id: str,
    *,
    token: str,
    path_in_repo: str = "",
    message: str | None = None,
) -> None:
    """Upload a directory into the dataset repo, creating it if needed."""
    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(
        folder_path=str(local_dir),
        repo_id=repo_id,
        repo_type="dataset",
        path_in_repo=path_in_repo,
        commit_message=message or f"update {path_in_repo or 'root'}",
    )
    logger.info("pushed %s -> %s/%s", local_dir, repo_id, path_in_repo)


def push_data(settings: Settings | None = None) -> None:
    """Publish every artifact family that exists locally."""
    settings = settings or get_settings()
    repo_id = repo_id_from(settings)
    token = settings.hf_token.get_secret_value()
    if not token:
        raise ValueError("HF_TOKEN is not set; it is required to upload")

    data_dir = settings.paths.resolve().data_dir
    for name in ("processed", "predictions", "sim", "summary"):
        directory = data_dir / name
        if not directory.exists() or not any(directory.iterdir()):
            logger.info("skipping %s (nothing to upload)", name)
            continue
        push_directory(directory, repo_id, token=token, path_in_repo=name, message=f"update {name}")


def pull_data(
    local_dir: Path,
    *,
    repo_id: str | None = None,
    patterns: tuple[str, ...] = DATA_PATTERNS,
    token: str | None = None,
) -> Path:
    """Download the published artifacts into ``local_dir``.

    Only the requested patterns are fetched, so the dashboard pulls megabytes, not
    the whole repository.
    """
    repo_id = repo_id or repo_id_from()
    path = snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=str(local_dir),
        allow_patterns=list(patterns),
        token=token,
    )
    logger.info("pulled %s into %s", ", ".join(patterns), path)
    return Path(path)


def pull_file(
    path_in_repo: str,
    local_dir: Path,
    *,
    repo_id: str | None = None,
    token: str | None = None,
) -> Path:
    """Download a single artifact file."""
    repo_id = repo_id or repo_id_from()
    return Path(
        hf_hub_download(
            repo_id=repo_id,
            filename=path_in_repo,
            repo_type="dataset",
            local_dir=str(local_dir),
            token=token,
        )
    )
