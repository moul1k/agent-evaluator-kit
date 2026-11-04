"""Explicit runtime-only secret loading; credential documents are never executed."""

import os
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def load_credentials(*paths: Path | None):
    pending = {}
    for path in paths:
        if path is None:
            continue
        if path.suffix.lower() == ".docx":
            with ZipFile(path) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            content = "\n".join("".join(p.itertext()) for p in document.iter(ns + "p"))
        else:
            content = path.read_text(encoding="utf-8-sig")
        patterns = {
            "OPENAI_API_KEY": r"\bsk-(?!lf-)[A-Za-z0-9_-]{20,}",
            "LANGFUSE_PUBLIC_KEY": r"\bpk-lf-[A-Za-z0-9_-]+",
            "LANGFUSE_SECRET_KEY": r"\bsk-lf-[A-Za-z0-9_-]+",
            "LANGFUSE_BASE_URL": r"https://(?:us\.|jp\.)?cloud\.langfuse\.com\b",
        }
        for name, pattern in patterns.items():
            matches = set(re.findall(pattern, content))
            if len(matches) > 1 or (matches and name in pending and pending[name] not in matches):
                raise ValueError(f"Ambiguous {name}; no credentials loaded")
            if matches:
                pending[name] = matches.pop()
    for name, value in pending.items():
        os.environ.setdefault(name, value)


def tracing_enabled(setting: bool | None):
    if setting is not None:
        return setting
    return all(os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"))
