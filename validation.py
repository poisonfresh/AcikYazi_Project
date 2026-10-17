"""Validation layer: looks up the dates and amounts extracted by the model in the original letter.

Independent of the model; uses only regexes and simple normalization. The letters
are Turkish, so Turkish date/amount formats are matched alongside English ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MONTHS = {
    # Turkish (with and without diacritics)
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
    # English
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

_MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))

# 15.11.2026, 15/11/2026, 15-11-26, 2026-11-15, 15 Kasım 2026, 15 November 2026
DATE_REGEX = re.compile(
    r"(?<!\d)(?:"
    r"(?P<d1>\d{1,2})\s*[./-]\s*(?P<m1>\d{1,2})\s*[./-]\s*(?P<y1>\d{4}|\d{2})"
    r"|(?P<y2>\d{4})-(?P<m2>\d{1,2})-(?P<d2>\d{1,2})"
    rf"|(?P<d3>\d{{1,2}})\s+(?P<m3>{_MONTH_PATTERN})\s+(?P<y3>\d{{4}})"
    r")(?!\d)",
    re.IGNORECASE,
)

_CURRENCY = r"(?:TL|TRY|₺|Türk\s+Lirası|Turk\s+Lirasi|Turkish\s+Lira|lira|EUR|€|USD|\$)"
_NUMBER = r"\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?"

# 1.250,00 TL, ₺350, 2.500 TL, 1250 TRY
AMOUNT_REGEX = re.compile(
    rf"(?:(?P<c1>{_CURRENCY})\s*(?P<n1>{_NUMBER}))"
    rf"|(?:(?P<n2>{_NUMBER})\s*(?P<c2>{_CURRENCY}))",
    re.IGNORECASE,
)

_BARE_NUMBER = re.compile(rf"(?<![\d.,])(?:{_NUMBER})(?![\d])")

# Relative deadlines: "tebliğden itibaren 15 gün", "15 (on beş) gün", "iki hafta", "1 ay", "10 iş günü"
_NUMBER_WORDS = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
    "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70,
    "seksen": 80, "doksan": 90, "yüz": 100,
}
_WORD = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
_WORD_NUMBER = rf"(?:(?:{_WORD})\s+){{0,2}}(?:{_WORD})"
_PARENTHESIS = r"(?:\s*\([^)]{1,40}\))?"
RELATIVE_REGEX = re.compile(
    rf"(?<!\w)(?:(?P<digits>\d{{1,3}})|(?P<words>{_WORD_NUMBER})){_PARENTHESIS}\s+"
    r"(?P<unit>iş\s+gün\w*|gün\w*|hafta\w*|ay(?:lık|da|dan|a|ı|ın)?|yıl\w*)(?!\w)"
)


def _turkish_lower(s: str) -> str:
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def _words_to_number(words: str) -> int | None:
    total = 0
    for w in words.split():
        n = _NUMBER_WORDS.get(w)
        if n is None:
            return None
        total = total * n if n == 100 and total else total + n
    return total or None


def _unit(raw: str) -> str:
    if raw.startswith("iş"):
        return "iş günü"
    for stem in ("gün", "hafta", "yıl"):
        if raw.startswith(stem):
            return stem
    return "ay"


def find_relative_periods(text: str) -> set[tuple[int, str]]:
    """Returns every relative period in the text as (number, unit), e.g. (15, "gün")."""
    result = set()
    for m in RELATIVE_REGEX.finditer(_turkish_lower(text)):
        n = int(m.group("digits")) if m.group("digits") else _words_to_number(m.group("words"))
        if n:
            result.add((n, _unit(m.group("unit"))))
    return result


@dataclass
class CheckResult:
    field: str
    value: str
    status: str  # "verified" | "relative" | "not_found" | "empty"
    message: str

    @property
    def is_warning(self) -> bool:
        return self.status == "not_found"


def _year(y: str) -> int:
    n = int(y)
    return 2000 + n if len(y) == 2 else n


def _normalize_date_match(m: re.Match) -> tuple[int, int, int] | None:
    try:
        if m.group("d1"):
            d, mo, y = int(m.group("d1")), int(m.group("m1")), _year(m.group("y1"))
        elif m.group("y2"):
            d, mo, y = int(m.group("d2")), int(m.group("m2")), int(m.group("y2"))
        else:
            d, mo, y = int(m.group("d3")), MONTHS[m.group("m3").lower()], int(m.group("y3"))
    except (TypeError, ValueError, KeyError):
        return None
    if not (1 <= d <= 31 and 1 <= mo <= 12):
        return None
    return (d, mo, y)


def find_dates(text: str) -> set[tuple[int, int, int]]:
    """Returns every date in the text as (day, month, year)."""
    result = set()
    for m in DATE_REGEX.finditer(text or ""):
        date = _normalize_date_match(m)
        if date:
            result.add(date)
    return result


def _normalize_number(s: str) -> Decimal | None:
    s = re.sub(r"\s", "", s)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return Decimal(s).normalize()
    except InvalidOperation:
        return None


def find_amounts(text: str) -> set[Decimal]:
    """Returns every amount written with a currency in the text, as a number."""
    result = set()
    for m in AMOUNT_REGEX.finditer(text or ""):
        d = _normalize_number(m.group("n1") or m.group("n2"))
        if d is not None:
            result.add(d)
    return result


def _amounts_in_value(value: str) -> set[Decimal]:
    found = find_amounts(value)
    if found:
        return found
    return {d for d in (_normalize_number(m.group()) for m in _BARE_NUMBER.finditer(value)) if d is not None}


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def check_date(value: str, original_text: str, field: str = "deadline") -> CheckResult:
    value = (value or "").strip()
    if not value:
        return CheckResult(field, value, "empty", "Yazıda belirtilmemiş.")
    model_dates = find_dates(value)
    if model_dates:
        missing = model_dates - find_dates(original_text)
        if not missing:
            return CheckResult(field, value, "verified", "Tarih asıl yazıda bulundu.")
        return CheckResult(field, value, "not_found", "Bu tarih asıl yazıda bulunamadı.")
    model_periods = find_relative_periods(value)
    if model_periods:
        periods = ", ".join(f"{n} {unit}" for n, unit in sorted(model_periods))
        if not model_periods - find_relative_periods(original_text):
            return CheckResult(
                field, value, "relative",
                f"Göreli süre ({periods}) asıl yazıda bulundu; kesin tarih yazının size teslim (tebliğ) "
                "edildiği güne göre hesaplanır.",
            )
        return CheckResult(field, value, "not_found", f"Bu süre ({periods}) asıl yazıda bulunamadı.")
    if _squash(value) in _squash(original_text):
        return CheckResult(field, value, "verified", "İfade asıl yazıda aynen geçiyor.")
    return CheckResult(field, value, "not_found", "Tarih biçimi tanınmadı ve ifade yazıda aynen geçmiyor.")


def check_amount(value: str, original_text: str, field: str = "amount") -> CheckResult:
    value = (value or "").strip()
    if not value:
        return CheckResult(field, value, "empty", "Yazıda belirtilmemiş.")
    model_amounts = _amounts_in_value(value)
    if model_amounts:
        missing = model_amounts - find_amounts(original_text)
        if not missing:
            return CheckResult(field, value, "verified", "Tutar asıl yazıda bulundu.")
        return CheckResult(field, value, "not_found", "Bu tutar asıl yazıda bulunamadı.")
    if _squash(value) in _squash(original_text):
        return CheckResult(field, value, "verified", "İfade asıl yazıda aynen geçiyor.")
    return CheckResult(field, value, "not_found", "Tutar biçimi tanınmadı ve ifade yazıda aynen geçmiyor.")


def _item_values(items) -> list[str]:
    if not isinstance(items, list):
        items = [items] if items else []
    return [str((x.get("deger") if isinstance(x, dict) else x) or "").strip() for x in items]


def validate_extraction(extraction: dict, original_text: str) -> list[CheckResult]:
    """Checks the engine's extraction (`cikarim`) against the original letter.

    Uses the engine's Turkish schema: `son_tarih` is an object with `deger`,
    `tutarlar` and `diger_tarihler` are lists of `{deger, aciklama}`.
    """
    deadline = extraction.get("son_tarih")
    deadline = deadline.get("deger", "") if isinstance(deadline, dict) else deadline
    results = [check_date(str(deadline or ""), original_text, field="son_tarih")]

    amounts = [v for v in _item_values(extraction.get("tutarlar")) if v]
    if amounts:
        results += [check_amount(v, original_text, field="tutarlar") for v in amounts]
    else:
        results.append(check_amount("", original_text, field="tutarlar"))

    results += [
        check_date(v, original_text, field="diger_tarihler")
        for v in _item_values(extraction.get("diger_tarihler"))
        if v
    ]
    return results


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _flatten(value) -> str:
    if isinstance(value, dict):
        return "\n".join(_flatten(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten(v) for v in value)
    return str(value or "")


def find_missing_in_translation(source, translation) -> list[str]:
    """Returns the dates/amounts lost in translation (empty list = no problem).

    Accepts plain strings or the engine's `sade` / `ceviri` dicts. Month names
    may change language in translation, so for dates it is enough that the day
    and the year survive as numbers.
    """
    source = _flatten(source)
    translation = _flatten(translation).translate(_ARABIC_DIGITS).replace("٫", ",").replace("٬", ".")
    translation_dates = find_dates(translation)
    translation_numbers = _amounts_in_value(translation) | {
        Decimal(m.group()) for m in re.finditer(r"\d+", translation)
    }
    missing = []
    for d, mo, y in sorted(find_dates(source)):
        if (d, mo, y) in translation_dates:
            continue
        if Decimal(d) in translation_numbers and Decimal(y) in translation_numbers:
            continue
        missing.append(f"{d:02d}.{mo:02d}.{y}")
    for amount in sorted(find_amounts(source)):
        if amount not in translation_numbers:
            missing.append(str(amount))
    return missing
