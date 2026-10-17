"""Builds and saves run records (pipeline result + metadata) as JSON evidence.

Shared by app.py (results/app_runs/) and run_samples.py (results/real_api/).
Records never contain the API key or the full letter text, only a fingerprint of it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "samples"
APP_RUNS_DIR = ROOT / "results" / "app_runs"
REAL_API_DIR = ROOT / "results" / "real_api"
FINGERPRINT_CHARS = 200


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def detect_sample_source(letter_text: str) -> str | None:
    """Returns e.g. "test_set/t1_trafik_cezasi" if the text is one of the sample letters."""
    target = _normalize_text(letter_text)
    for path in sorted(SAMPLES_DIR.glob("*/*.txt")):
        if _normalize_text(path.read_text(encoding="utf-8")) == target:
            return f"{path.parent.name}/{path.stem}"
    return None


def fingerprint(letter_text: str) -> dict:
    head = (letter_text or "").strip()[:FINGERPRINT_CHARS]
    return {
        "length_chars": len(letter_text or ""),
        f"first_{FINGERPRINT_CHARS}_chars_sha256": hashlib.sha256(head.encode("utf-8")).hexdigest(),
    }


def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text.replace("ı", "i").replace("İ", "I"))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].strip("-") or "yazi"


def build_record(
    result: dict,
    letter_text: str,
    language: str,
    checks: list,
    translation_missing: list[str] | None,
    source: str | None,
    mock: bool,
    origin: str,
) -> dict:
    return {
        "saved_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "origin": origin,
        "model": result.get("model"),
        "prompt_versions": result.get("surumler"),
        "language": language,
        "mock": mock,
        "source": {"name": source, **fingerprint(letter_text)},
        "our_validation": {
            "checks": [asdict(c) | {"is_warning": c.is_warning} for c in checks],
            "has_warning": any(c.is_warning for c in checks),
            "translation_missing": translation_missing,
        },
        "result": result,
    }


def record_slug(record: dict) -> str:
    source = record["source"]
    if source.get("name"):
        base = slugify(source["name"].split("/")[-1])
    else:
        base = "yazi-" + source[f"first_{FINGERPRINT_CHARS}_chars_sha256"][:8]
    return f"{base}_mock" if record.get("mock") else base


def to_json(record: dict) -> str:
    text = json.dumps(record, ensure_ascii=False, indent=2)
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.getenv(env_name)
        if key and len(key) > 4 and key in text:
            raise ValueError(f"Refusing to save a record that contains {env_name}.")
    return text


def save_record(record: dict, directory: Path, filename_stem: str, overwrite: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{filename_stem}.json"
    n = 2
    while path.exists() and not overwrite:
        path = directory / f"{filename_stem}-{n}.json"
        n += 1
    path.write_text(to_json(record) + "\n", encoding="utf-8")
    return path


def timestamp_for_filename() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
