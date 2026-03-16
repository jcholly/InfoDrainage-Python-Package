"""Shared pytest configuration and fixtures for iddx_core test suite.

Usage:
    pytest tests/                           # runs only synthetic/unit tests
    pytest tests/ --model path/to/file.iddx # runs all tests including model-dependent ones
    pytest tests/ --model-dir path/to/dir   # auto-discovers all .iddx files in directory
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="Path to a single .iddx file for integration tests.",
    )
    parser.addoption(
        "--model-dir",
        action="store",
        default=None,
        help="Path to a directory containing .iddx files (searched recursively).",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def model_path(request: pytest.FixtureRequest) -> Optional[Path]:
    """Return the Path to the .iddx file specified via --model, or None."""
    raw = request.config.getoption("--model")
    if raw is None:
        return None
    p = Path(raw)
    if not p.exists():
        pytest.fail(f"--model path does not exist: {p}")
    return p


@pytest.fixture(scope="session")
def all_model_paths(request: pytest.FixtureRequest) -> list[Path]:
    """Collect every .iddx path from --model and/or --model-dir."""
    paths: list[Path] = []
    single = request.config.getoption("--model")
    if single:
        p = Path(single)
        if p.exists():
            paths.append(p)

    model_dir = request.config.getoption("--model-dir")
    if model_dir:
        d = Path(model_dir)
        if d.is_dir():
            paths.extend(sorted(d.rglob("*.iddx")))
    return paths


@pytest.fixture(scope="session")
def iddx_model(model_path):
    """Open the --model file and return an IddxModel, or skip."""
    if model_path is None:
        pytest.skip("No --model provided")
    from iddx_core import IddxModel
    return IddxModel.open(model_path)


@pytest.fixture(scope="session")
def first_phase(iddx_model):
    """Return the first phase from the model, or skip."""
    if not iddx_model.phases:
        pytest.skip("Model has no phases")
    return next(iter(iddx_model.phases.values()))


@pytest.fixture
def tmp_iddx_path(tmp_path: Path) -> Path:
    """Provide a temporary .iddx output path for save tests."""
    return tmp_path / "test_output.iddx"


@pytest.fixture(scope="session")
def tmp_session_dir() -> Path:
    """Session-scoped temporary directory, cleaned up at the end."""
    d = Path(tempfile.mkdtemp(prefix="iddx_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------

requires_model = pytest.mark.skipif(
    "not config.getoption('--model')",
    reason="No --model provided",
)

requires_model_dir = pytest.mark.skipif(
    "not config.getoption('--model-dir')",
    reason="No --model-dir provided",
)
