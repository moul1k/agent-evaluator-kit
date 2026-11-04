"""Reproducible run metadata without environment variables or credential values."""

import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def capture() -> dict:
    root = Path(__file__).resolve().parents[2]

    def git(*args):
        try:
            return subprocess.check_output(
                ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    packages = {}
    for package in ("agent-evaluator-kit", "pydantic", "openai", "langfuse"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    dirty = git("status", "--porcelain")
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(dirty) if dirty is not None else None,
        "python": platform.python_version(),
        "packages": packages,
    }
