"""Scaffold guard: the package and its subpackages must import cleanly."""

import importlib

import pytest

import crypto_cross_pred

SUBPACKAGES = ["io", "data", "models", "sim", "report"]


def test_version_is_set() -> None:
    assert crypto_cross_pred.__version__ == "0.1.0"


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    module = importlib.import_module(f"crypto_cross_pred.{name}")
    assert module.__doc__
