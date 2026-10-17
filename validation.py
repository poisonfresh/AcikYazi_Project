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


@dataclass
class CheckResult:
    field: str
    value: str
    status: str  # "verified" | "not_found" | "empty"
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
        return CheckResult(field, value, "empty", "Not specified in the letter.")
    model_dates = find_dates(value)
    if model_dates:
        missing = model_dates - find_dates(original_text)
        if not missing:
            return CheckResult(field, value, "verified", "Date found in the original letter.")
        return CheckResult(field, value, "not_found", "This date was not found in the original letter.")
    if _squash(value) in _squash(original_text):
        return CheckResult(field, value, "verified", "The exact wording appears in the original letter.")
    return CheckResult(field, value, "not_found", "Date format not recognized and the text does not appear in the letter.")


def check_amount(value: str, original_text: str, field: str = "amount") -> CheckResult:
    value = (value or "").strip()
    if not value:
        return CheckResult(field, value, "empty", "Not specified in the letter.")
    model_amounts = _amounts_in_value(value)
    if model_amounts:
        missing = model_amounts - find_amounts(original_text)
        if not missing:
            return CheckResult(field, value, "verified", "Amount found in the original letter.")
        return CheckResult(field, value, "not_found", "This amount was not found in the original letter.")
    if _squash(value) in _squash(original_text):
        return CheckResult(field, value, "verified", "The exact wording appears in the original letter.")
    return CheckResult(field, value, "not_found", "Amount format not recognized and the text does not appear in the letter.")


def validate_extraction(data: dict, original_text: str) -> list[CheckResult]:
    """Compares the deadline and amount fields of the extraction JSON with the original letter."""
    return [
        check_date(str(data.get("deadline") or ""), original_text),
        check_amount(str(data.get("amount") or ""), original_text),
    ]


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def find_missing_in_translation(source: str, translation: str) -> list[str]:
    """Returns the dates/amounts lost in translation (empty list = no problem).

    Month names may change language in translation, so for dates it is enough
    that the day and the year survive as numbers.
    """
    translation = (translation or "").translate(_ARABIC_DIGITS).replace("٫", ",").replace("٬", ".")
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
