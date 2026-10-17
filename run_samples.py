"""Runs every sample letter through run_pipeline() and writes evidence plus a Turkish summary.

Usage:
    python run_samples.py                    # real API (needs GEMINI_API_KEY in .env)
    ACIKYAZI_MOCK=1 python run_samples.py    # fake answers, no API calls

For each letter in samples/dev_letters and samples/test_set this script saves the full
result JSON (same record format as the app), runs our validation.py checks, compares the
extraction with answers.json and finally writes ozet.md and ozet.csv into the output folder
(default: results/real_api/<YYYY-MM-DD>/, or <YYYY-MM-DD>_mock in mock mode).

Answers are cached by the engine in .cache/; delete that folder to force fresh API calls.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import prompt_engine  # noqa: E402
import run_records  # noqa: E402
from validation import find_missing_in_translation, validate_extraction  # noqa: E402

SAMPLE_SETS = ("dev_letters", "test_set")
LANGUAGES = ("tr", "en", "ar")
MAX_CONSECUTIVE_FAILURES = 3
DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")

COLUMNS = [
    ("letter", "Yazı"),
    ("deadline_ok", "Son tarih doğru mu"),
    ("amounts_ok", "Tutarlar doğru mu"),
    ("institution_ok", "Kurum doğru mu"),
    ("engine_warning", "Motor uyarısı"),
    ("our_warning", "Bizim uyarımız"),
    ("overall", "Genel sonuç"),
]


def mock_mode() -> bool:
    return os.getenv("ACIKYAZI_MOCK") == "1"


def is_retryable(error: Exception) -> bool:
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code == 429 or code >= 500
    return isinstance(error, (ConnectionError, TimeoutError, OSError))


def run_with_retry(letter_text: str, language: str, retries: int, backoff: float) -> dict:
    """The engine already retries 429s internally; this adds a slower outer retry on top."""
    for attempt in range(retries + 1):
        try:
            return prompt_engine.run_pipeline(letter_text, dil=language)
        except Exception as e:
            if attempt == retries or not is_retryable(e):
                raise
            wait = backoff * (2**attempt)
            print(f"    Geçici hata ({type(e).__name__}: {e}); {wait:.0f} sn sonra yeniden deneniyor…")
            time.sleep(wait)
    raise AssertionError("unreachable")


def compare_with_answers(extraction: dict, answer: dict | None) -> dict:
    """Mirrors run_experiments.puanla_cikarim for the deadline and amounts."""
    if answer is None:
        return {"deadline_ok": None, "amounts_found": None, "amounts_expected": None, "institution_ok": None}
    deadline = ((extraction.get("son_tarih") or {}).get("deger") or "").strip()
    if "son_tarih_icerir" in answer:
        plain = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", deadline)).lower()
        expected = answer["son_tarih_icerir"].lower()
        computed_date = bool(DATE_RE.search(deadline)) and not DATE_RE.search(expected)
        deadline_ok = expected in plain and not (computed_date and "gün" in expected)
    else:
        deadline_ok = deadline == answer.get("son_tarih", "")
    expected_amounts = answer.get("tutarlar", [])
    found = [t.get("deger", "") for t in extraction.get("tutarlar") or [] if isinstance(t, dict)]
    amounts_found = sum(any(e in f for f in found) for e in expected_amounts)
    institution_ok = None
    if answer.get("kurum"):
        institution_ok = answer["kurum"].lower() in str(extraction.get("kurum") or "").lower()
    return {
        "deadline_ok": deadline_ok,
        "amounts_found": amounts_found,
        "amounts_expected": len(expected_amounts),
        "institution_ok": institution_ok,
    }


def yes_no(value: bool | None) -> str:
    return "—" if value is None else ("Evet" if value else "Hayır")


def summarize(name: str, record: dict | None, comparison: dict, error: str | None) -> dict:
    row = {"letter": name}
    if error:
        return row | {
            "deadline_ok": "—",
            "amounts_ok": "—",
            "institution_ok": "—",
            "engine_warning": "—",
            "our_warning": "—",
            "overall": f"Hata: {error}",
        }
    engine_warnings = (record["result"].get("dogrulama") or {}).get("uyarilar") or []
    ours = record["our_validation"]
    our_warnings = [c["message"] for c in ours["checks"] if c["is_warning"]]
    if ours["translation_missing"]:
        our_warnings.append("Çeviride eksik: " + ", ".join(ours["translation_missing"]))

    if comparison["amounts_expected"] is None:
        amounts_ok, amounts_pass = "—", True
    elif comparison["amounts_expected"] == 0:
        amounts_ok, amounts_pass = "Evet (beklenen tutar yok)", True
    else:
        amounts_pass = comparison["amounts_found"] == comparison["amounts_expected"]
        amounts_ok = f"{yes_no(amounts_pass)} ({comparison['amounts_found']}/{comparison['amounts_expected']})"

    if comparison["deadline_ok"] is False or not amounts_pass or comparison["institution_ok"] is False:
        overall = "Kaldı"
    elif engine_warnings or our_warnings:
        overall = "Kontrol gerekli"
    else:
        overall = "Geçti"
    return row | {
        "deadline_ok": yes_no(comparison["deadline_ok"]),
        "amounts_ok": amounts_ok,
        "institution_ok": yes_no(comparison["institution_ok"]),
        "engine_warning": " / ".join(engine_warnings) or "Yok",
        "our_warning": " / ".join(our_warnings) or "Yok",
        "overall": overall,
    }


def md_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_summary(out_dir: Path, rows: list[dict], meta: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = [c for c in COLUMNS if c[0] != "institution_ok" or meta["has_institution_key"]]
    with (out_dir / "ozet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in columns])
        for row in rows:
            writer.writerow([row[key] for key, _ in columns])

    counts = {label: sum(r["overall"].startswith(label) for r in rows) for label in ("Geçti", "Kontrol gerekli", "Kaldı", "Hata")}
    lines = [
        f"# AçıkYazı örnek yazı testi — {meta['date']}",
        "",
        f"- Çalıştırma zamanı: {meta['started_at']}",
        f"- Model: `{meta['model']}`" + (" (deneme/mock modu: cevaplar sahte)" if meta["mock"] else ""),
        "- Prompt sürümleri: " + ", ".join(f"`{k}`: `{v}`" for k, v in meta["prompt_versions"].items()),
        f"- Açıklama dili: `{meta['language']}`",
        f"- Yazı sayısı: {len(rows)} — " + ", ".join(f"{k}: {v}" for k, v in counts.items()),
        "",
        "| " + " | ".join(label for _, label in columns) + " |",
        "|" + "---|" * len(columns),
    ]
    lines += ["| " + " | ".join(md_cell(row[key]) for key, _ in columns) + " |" for row in rows]
    lines += [
        "",
        "**Sütunlar:**",
        "- *Son tarih doğru mu*: modelin bulduğu son tarih `answers.json` ile karşılaştırılır "
        "(`run_experiments.py` ile aynı kural; göreli sürelerde tarih hesaplanmışsa yanlış sayılır).",
        "- *Tutarlar doğru mu*: `answers.json` içindeki tutarlardan kaçının bulunduğu.",
        "- *Motor uyarısı*: `prompt_engine.dogrula()` uyarıları (güvenlik katmanı).",
        "- *Bizim uyarımız*: `validation.py` kontrolleri (tarih/tutar yazıda yok, çeviride eksik bilgi).",
        "- *Genel sonuç*: Geçti = doğru ve uyarı yok; Kontrol gerekli = doğru ama en az bir uyarı var; "
        "Kaldı = son tarih veya tutar yanlış; Hata = API/işlem hatası.",
        "",
        "Her yazının tam sonucu bu klasördeki `<yazı>.json` dosyasındadır.",
    ]
    if meta["mock"]:
        lines.append("**Mock modu:** motor son tarih olarak yazıdaki son tarihi döndürür; bu tablo yalnızca betiğin "
                     "çalıştığını gösterir, doğruluk kanıtı değildir.")
    if not meta["has_institution_key"]:
        lines.append("Cevap anahtarlarında `kurum` alanı olmadığı için kurum karşılaştırması yapılmadı.")
    (out_dir / "ozet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Runs all sample letters through run_pipeline() and writes ozet.md/ozet.csv.")
    parser.add_argument("--out", type=Path, help="Output folder (default: results/real_api/<YYYY-MM-DD>[_mock]).")
    parser.add_argument("--lang", choices=LANGUAGES, default="en", help="Explanation language (default: en, also tests translation).")
    parser.add_argument("--sleep", type=float, default=6.0, help="Seconds to wait between letters (default: 6).")
    parser.add_argument("--retries", type=int, default=3, help="Outer retries on 429/5xx/network errors (default: 3).")
    parser.add_argument("--backoff", type=float, default=20.0, help="First retry wait in seconds, doubled each time (default: 20).")
    parser.add_argument("--only", nargs="*", help="Only run these letters, e.g. t1_trafik_cezasi d2_trafik_cezasi.")
    args = parser.parse_args()

    mock = mock_mode()
    if not mock and not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("GEMINI_API_KEY bulunamadı. `.env` dosyasına ekleyin ya da sahte cevaplarla denemek için "
              "`ACIKYAZI_MOCK=1 python run_samples.py` çalıştırın.")
        return 2

    started_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    today = dt.date.today().isoformat()
    out_dir = args.out or run_records.REAL_API_DIR / (f"{today}_mock" if mock else today)
    out_dir = out_dir if out_dir.is_absolute() else Path.cwd() / out_dir

    letters = []
    answers: dict[str, dict] = {}
    for set_name in SAMPLE_SETS:
        set_dir = run_records.SAMPLES_DIR / set_name
        answers_path = set_dir / "answers.json"
        if answers_path.exists():
            answers |= {k: v for k, v in json.loads(answers_path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        letters += sorted(set_dir.glob("*.txt"))
    if args.only:
        letters = [p for p in letters if p.stem in set(args.only)]
        if not letters:
            print("`--only` ile verilen yazılar bulunamadı.")
            return 2

    print(f"{len(letters)} yazı çalıştırılacak — model: {prompt_engine.MODEL}, dil: {args.lang}"
          + (" (MOCK: sahte cevaplar)" if mock else ""))
    print(f"Sonuçlar: {out_dir}")

    rows = []
    consecutive_failures = 0
    for i, path in enumerate(letters, 1):
        if i > 1 and not mock:
            time.sleep(args.sleep)
        name = path.stem
        print(f"[{i}/{len(letters)}] {path.parent.name}/{name}")
        letter_text = path.read_text(encoding="utf-8")
        try:
            result = run_with_retry(letter_text, args.lang, args.retries, args.backoff)
        except Exception as e:
            consecutive_failures += 1
            message = f"{type(e).__name__}: {e}"
            print(f"    HATA: {message}")
            rows.append(summarize(name, None, {}, message[:200]))
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"Art arda {MAX_CONSECUTIVE_FAILURES} hata; durduruluyor (kota veya anahtar sorunu olabilir).")
                break
            continue
        consecutive_failures = 0

        translation = result.get("ceviri")
        record = run_records.build_record(
            result,
            letter_text,
            language=args.lang,
            checks=validate_extraction(result.get("cikarim") or {}, letter_text),
            translation_missing=(
                find_missing_in_translation(result.get("sade") or {}, translation)
                if translation is not None and args.lang != "tr"
                else None
            ),
            source=f"{path.parent.name}/{name}",
            mock=mock,
            origin="run_samples",
        )
        comparison = compare_with_answers(result.get("cikarim") or {}, answers.get(name))
        record["answer_check"] = comparison
        saved = run_records.save_record(record, out_dir, name, overwrite=True)
        row = summarize(name, record, comparison, None)
        rows.append(row)
        print(f"    {row['overall']} — son tarih: {row['deadline_ok']}, tutarlar: {row['amounts_ok']} → {saved.name}")

    write_summary(
        out_dir,
        rows,
        {
            "date": today,
            "started_at": started_at,
            "model": prompt_engine.MODEL,
            "prompt_versions": prompt_engine.VARSAYILAN,
            "language": args.lang,
            "mock": mock,
            "has_institution_key": any("kurum" in a for a in answers.values()),
        },
    )
    print(f"Özet yazıldı: {out_dir / 'ozet.md'} ve {out_dir / 'ozet.csv'}")
    return 1 if any(r["overall"].startswith("Hata") for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
