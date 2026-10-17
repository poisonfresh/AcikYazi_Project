"""Doğrulama katmanı: modelin çıkardığı tarih ve tutarları asıl metinde arar.

Modelden bağımsız çalışır; yalnızca regex ve basit normalizasyon kullanır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

AYLAR = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}

_AY_DESENI = "|".join(sorted(AYLAR, key=len, reverse=True))

# 15.11.2026, 15/11/2026, 15-11-26, 2026-11-15, 15 Kasım 2026
TARIH_REGEX = re.compile(
    r"(?<!\d)(?:"
    r"(?P<g1>\d{1,2})\s*[./-]\s*(?P<a1>\d{1,2})\s*[./-]\s*(?P<y1>\d{4}|\d{2})"
    r"|(?P<y2>\d{4})-(?P<a2>\d{1,2})-(?P<g2>\d{1,2})"
    rf"|(?P<g3>\d{{1,2}})\s+(?P<a3>{_AY_DESENI})\s+(?P<y3>\d{{4}})"
    r")(?!\d)",
    re.IGNORECASE,
)

_PARA_BIRIMI = r"(?:TL|TRY|₺|Türk\s+Lirası|Turk\s+Lirasi|lira|EUR|€|USD|\$)"
_SAYI = r"\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?"

# 1.250,00 TL, ₺350, 2.500 TL, 1250 TRY
TUTAR_REGEX = re.compile(
    rf"(?:(?P<b1>{_PARA_BIRIMI})\s*(?P<s1>{_SAYI}))"
    rf"|(?:(?P<s2>{_SAYI})\s*(?P<b2>{_PARA_BIRIMI}))",
    re.IGNORECASE,
)

_SADECE_SAYI = re.compile(rf"(?<![\d.,])(?:{_SAYI})(?![\d])")


@dataclass
class KontrolSonucu:
    alan: str
    deger: str
    durum: str  # "dogrulandi" | "bulunamadi" | "bos"
    aciklama: str

    @property
    def uyari(self) -> bool:
        return self.durum == "bulunamadi"


def _yil(y: str) -> int:
    n = int(y)
    return 2000 + n if len(y) == 2 else n


def _tarih_eslesmesi_normalize(m: re.Match) -> tuple[int, int, int] | None:
    try:
        if m.group("g1"):
            g, a, y = int(m.group("g1")), int(m.group("a1")), _yil(m.group("y1"))
        elif m.group("y2"):
            g, a, y = int(m.group("g2")), int(m.group("a2")), int(m.group("y2"))
        else:
            g, a, y = int(m.group("g3")), AYLAR[m.group("a3").lower()], int(m.group("y3"))
    except (TypeError, ValueError, KeyError):
        return None
    if not (1 <= g <= 31 and 1 <= a <= 12):
        return None
    return (g, a, y)


def tarihleri_bul(metin: str) -> set[tuple[int, int, int]]:
    """Metindeki tüm tarihleri (gün, ay, yıl) olarak döndürür."""
    sonuc = set()
    for m in TARIH_REGEX.finditer(metin or ""):
        t = _tarih_eslesmesi_normalize(m)
        if t:
            sonuc.add(t)
    return sonuc


def _sayi_normalize(s: str) -> Decimal | None:
    s = re.sub(r"\s", "", s)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return Decimal(s).normalize()
    except InvalidOperation:
        return None


def tutarlari_bul(metin: str) -> set[Decimal]:
    """Metindeki para birimi ile yazılmış tüm tutarları sayı olarak döndürür."""
    sonuc = set()
    for m in TUTAR_REGEX.finditer(metin or ""):
        d = _sayi_normalize(m.group("s1") or m.group("s2"))
        if d is not None:
            sonuc.add(d)
    return sonuc


def _deger_tutarlari(deger: str) -> set[Decimal]:
    bulunan = tutarlari_bul(deger)
    if bulunan:
        return bulunan
    return {d for d in (_sayi_normalize(m.group()) for m in _SADECE_SAYI.finditer(deger)) if d is not None}


def _metni_sadelestir(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def tarih_kontrol(deger: str, asil_metin: str, alan: str = "son_tarih") -> KontrolSonucu:
    deger = (deger or "").strip()
    if not deger:
        return KontrolSonucu(alan, deger, "bos", "Yazıda belirtilmemiş.")
    model_tarihleri = tarihleri_bul(deger)
    if model_tarihleri:
        eksik = model_tarihleri - tarihleri_bul(asil_metin)
        if not eksik:
            return KontrolSonucu(alan, deger, "dogrulandi", "Tarih asıl metinde bulundu.")
        return KontrolSonucu(alan, deger, "bulunamadi", "Bu tarih asıl metinde bulunamadı.")
    if _metni_sadelestir(deger) in _metni_sadelestir(asil_metin):
        return KontrolSonucu(alan, deger, "dogrulandi", "İfade asıl metinde aynen geçiyor.")
    return KontrolSonucu(alan, deger, "bulunamadi", "Tarih biçimi tanınmadı ve metinde aynen geçmiyor.")


def tutar_kontrol(deger: str, asil_metin: str, alan: str = "tutar") -> KontrolSonucu:
    deger = (deger or "").strip()
    if not deger:
        return KontrolSonucu(alan, deger, "bos", "Yazıda belirtilmemiş.")
    model_tutarlari = _deger_tutarlari(deger)
    if model_tutarlari:
        eksik = model_tutarlari - tutarlari_bul(asil_metin)
        if not eksik:
            return KontrolSonucu(alan, deger, "dogrulandi", "Tutar asıl metinde bulundu.")
        return KontrolSonucu(alan, deger, "bulunamadi", "Bu tutar asıl metinde bulunamadı.")
    if _metni_sadelestir(deger) in _metni_sadelestir(asil_metin):
        return KontrolSonucu(alan, deger, "dogrulandi", "İfade asıl metinde aynen geçiyor.")
    return KontrolSonucu(alan, deger, "bulunamadi", "Tutar biçimi tanınmadı ve metinde aynen geçmiyor.")


def cikarimi_dogrula(veri: dict, asil_metin: str) -> list[KontrolSonucu]:
    """Çıkarım JSON'undaki son_tarih ve tutar alanlarını asıl metinle karşılaştırır."""
    return [
        tarih_kontrol(str(veri.get("son_tarih") or ""), asil_metin),
        tutar_kontrol(str(veri.get("tutar") or ""), asil_metin),
    ]


_ARAP_RAKAMLARI = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def ceviride_rakam_kontrol(kaynak: str, ceviri: str) -> list[str]:
    """Çeviride kaybolan tarih/tutarları döndürür (boş liste = sorun yok).

    Çeviride ay adı başka dile geçebileceği için tarihlerde gün ve yılın
    sayı olarak korunması yeterli sayılır.
    """
    ceviri = (ceviri or "").translate(_ARAP_RAKAMLARI).replace("٫", ",").replace("٬", ".")
    ceviri_tarihleri = tarihleri_bul(ceviri)
    ceviri_sayilari = _deger_tutarlari(ceviri) | {
        Decimal(m.group()) for m in re.finditer(r"\d+", ceviri)
    }
    kayip = []
    for g, a, y in sorted(tarihleri_bul(kaynak)):
        if (g, a, y) in ceviri_tarihleri:
            continue
        if Decimal(g) in ceviri_sayilari and Decimal(y) in ceviri_sayilari:
            continue
        kayip.append(f"{g:02d}.{a:02d}.{y}")
    for t in sorted(tutarlari_bul(kaynak)):
        if t not in ceviri_sayilari:
            kayip.append(str(t))
    return kayip
