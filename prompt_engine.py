"""AçıkYazı prompt motoru.

B (geliştirici) bu modülü Streamlit uygulamasından şöyle kullanır:

    from prompt_engine import run_pipeline
    sonuc = run_pipeline(metin, dil="en")   # dil: "tr", "en", "ar"
    sonuc["cikarim"], sonuc["sade"], sonuc["ceviri"], sonuc["dogrulama"]

Ortam değişkenleri:
    GEMINI_API_KEY   Google AI Studio anahtarı (repoya ASLA koymayın, .env kullanın)
    ACIKYAZI_MODEL   varsayılan "gemini-3.5-flash-lite"; AI Studio'da ücretsiz kotası olan başka bir modelle değiştirilebilir
    ACIKYAZI_MOCK=1  API çağırmadan sahte cevaplarla çalışır (arayüz geliştirme ve kota tasarrufu için)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS = ROOT / "prompts"
CACHE = ROOT / ".cache"

try:  # .env dosyasını otomatik oku (python-dotenv kuruluysa)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

MODEL = os.environ.get("ACIKYAZI_MODEL", "gemini-3.5-flash-lite")
TEMPERATURE = 0.2  # düşük: tutarlı ve tekrarlanabilir çıktı

# Varsayılan (final) sürümler. Deneyler bitince en iyi sürümü burada seçin.
VARSAYILAN = {"extract": "extract_v2_cot", "simplify": "simplify_v3_goreli_sure", "translate": "translate_v3_ay_adi"}

DILLER = {
    "tr": "Türkçe",
    "en": "İngilizce (English)",
    "ar": "Arapça (Modern Standart Arapça)",
}


# ---------------------------------------------------------------- şablonlar
def sablon(ad: str) -> str:
    return (PROMPTS / f"{ad}.txt").read_text(encoding="utf-8")


def sistem_promptu() -> str:
    return sablon("system")


def few_shot_blogu() -> str:
    ornekler = json.loads((PROMPTS / "fewshot_examples.json").read_text(encoding="utf-8"))
    parcalar = []
    for i, o in enumerate(ornekler, 1):
        parcalar.append(
            f"ÖRNEK {i}\nGirdi:\n{json.dumps(o['girdi'], ensure_ascii=False)}\n"
            f"Çıktı:\n{json.dumps(o['cikti'], ensure_ascii=False)}"
        )
    return "\n\n".join(parcalar)


def doldur(ad: str, **alanlar) -> str:
    """{{ALAN}} yer tutucularını doldurur. str.format kullanmıyoruz çünkü şablonlarda JSON parantezleri var."""
    metin = sablon(ad)
    if "{{ORNEKLER}}" in metin:
        metin = metin.replace("{{ORNEKLER}}", few_shot_blogu())
    for k, v in alanlar.items():
        metin = metin.replace("{{" + k.upper() + "}}", v)
    return metin


# ---------------------------------------------------------------- model çağrısı
def _mock_cevap(prompt: str) -> str:
    """API olmadan akışı test etmek için kaba sahte cevap. Kalite ölçümü için KULLANMAYIN."""
    if "YAZI:\n<<<" in prompt:
        yazi = prompt.split("<<<", 1)[-1]
        tarihler = re.findall(r"\d{2}\.\d{2}\.\d{4}", yazi)
        tutarlar = re.findall(r"\d[\d.]*,\d{2} TL", yazi)
        return json.dumps({
            "analiz_adimlari": ["(mock)"], "belge_turu": "mock", "kurum": "mock", "konu": "mock",
            "istenen_islem": "mock",
            "son_tarih": {"deger": tarihler[-1] if tarihler else "", "aciklama": "", "kaynak_alinti": ""},
            "tutarlar": [{"deger": t, "aciklama": ""} for t in tutarlar],
            "diger_tarihler": [], "gerekli_belgeler": [], "itiraz_yolu": "", "yaptirim": "", "iletisim": "",
            "emin_olunmayanlar": [],
        }, ensure_ascii=False)
    if "diline çevir" in prompt:
        return prompt[prompt.rfind('{"bu_yazi_ne"'):].strip()
    girdi = prompt[prompt.rfind('{"belge_turu"') if '{"belge_turu"' in prompt else 0:]
    try:
        d = json.loads(girdi.split("\nÇıktı:")[0])
        st = d["son_tarih"]["deger"]
    except Exception:
        st = ""
    return json.dumps({"bu_yazi_ne": "(mock) Bu yazı bir bildirim.", "ne_yapmalisiniz": ["(mock) Kuruma başvurun."],
                       "son_tarih_ve_yardim": f"Son gün: {st or 'belirtilmemiş'}. Emin olmadığınızda yazıyı gönderen kuruma sorun.",
                       "dikkat": []}, ensure_ascii=False)


def model_cagir(prompt: str, sistem: str | None = None, json_cikti: bool = True, max_deneme: int = 5) -> str:
    sistem = sistem if sistem is not None else sistem_promptu()
    anahtar = hashlib.sha256(f"{MODEL}|{TEMPERATURE}|{sistem}|{prompt}".encode()).hexdigest()[:24]
    CACHE.mkdir(exist_ok=True)
    onbellek = CACHE / f"{anahtar}.txt"
    if onbellek.exists() and os.environ.get("ACIKYAZI_MOCK") != "1":
        return onbellek.read_text(encoding="utf-8")

    if os.environ.get("ACIKYAZI_MOCK") == "1":
        return _mock_cevap(prompt)

    from google import genai
    from google.genai import errors, types

    client = genai.Client()  # GEMINI_API_KEY ortam değişkeninden okunur
    ayar = types.GenerateContentConfig(
        system_instruction=sistem,
        temperature=TEMPERATURE,
        response_mime_type="application/json" if json_cikti else "text/plain",
    )
    for deneme in range(max_deneme):
        try:
            cevap = client.models.generate_content(model=MODEL, contents=prompt, config=ayar)
            metin = cevap.text or ""
            onbellek.write_text(metin, encoding="utf-8")
            return metin
        except errors.APIError as e:
            # 429: dakikalık kota. Günlük kota dolduysa bekleme işe yaramaz.
            if getattr(e, "code", None) != 429 or deneme == max_deneme - 1:
                raise
            time.sleep(2 ** deneme + random.random())
    raise RuntimeError("Model çağrısı başarısız")


def json_coz(metin: str) -> dict:
    """Modelin cevabından JSON'u çıkarır; ```json bloklarını ve baştaki/sondaki metni tolere eder."""
    metin = metin.strip()
    metin = re.sub(r"^```(?:json)?\s*|\s*```$", "", metin)
    try:
        return json.loads(metin)
    except json.JSONDecodeError:
        bas, son = metin.find("{"), metin.rfind("}")
        if bas != -1 and son > bas:
            return json.loads(metin[bas:son + 1])
        raise


# ---------------------------------------------------------------- adımlar
def _tek_sozluk(d):
    """Model bazen JSON'u bir listenin içinde döndürür: [{...}]. Bunu düzeltir."""
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return d[0]
    if not isinstance(d, dict):
        raise ValueError(f"Beklenen JSON nesnesi değil: {str(d)[:120]}")
    return d


def cikarim_duzelt(c) -> dict:
    """Modelin şemadan küçük sapmalarını (string yerine nesne vb.) toparlar."""
    c = _tek_sozluk(c)
    st = c.get("son_tarih")
    if not isinstance(st, dict):
        c["son_tarih"] = {"deger": str(st or ""), "aciklama": "", "kaynak_alinti": ""}
    for alan in ("tutarlar", "diger_tarihler"):
        liste = c.get(alan) or []
        if not isinstance(liste, list):
            liste = [liste]
        c[alan] = [x if isinstance(x, dict) else {"deger": str(x), "aciklama": ""} for x in liste]
    for alan in ("gerekli_belgeler", "emin_olunmayanlar", "analiz_adimlari"):
        v = c.get(alan) or []
        c[alan] = v if isinstance(v, list) else [str(v)]
    return c


def cikar(metin: str, surum: str | None = None) -> dict:
    return cikarim_duzelt(json_coz(model_cagir(doldur(surum or VARSAYILAN["extract"], metin=metin))))


def sadelestir(cikarim: dict, surum: str | None = None) -> dict:
    temiz = {k: v for k, v in cikarim.items() if k != "analiz_adimlari"}  # CoT'yi sonraki adıma taşımıyoruz
    return _tek_sozluk(json_coz(model_cagir(doldur(surum or VARSAYILAN["simplify"], json=json.dumps(temiz, ensure_ascii=False)))))


def cevir(sade: dict, dil: str, surum: str | None = None) -> dict:
    if dil == "tr":
        return sade
    return _tek_sozluk(json_coz(model_cagir(doldur(surum or VARSAYILAN["translate"], dil=DILLER[dil],
                                       json=json.dumps(sade, ensure_ascii=False)))))


# ---------------------------------------------------------------- doğrulama (modelden bağımsız)
_ARAP_RAKAM = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _norm(s: str) -> str:
    s = (s or "").translate(_ARAP_RAKAM).replace("₺", "TL").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def rakamlar(s) -> set[str]:
    """Metindeki tarih/tutar/saat/numara benzeri sayısal öğeler."""
    if not isinstance(s, str):
        s = json.dumps(s, ensure_ascii=False)
    s = s.translate(_ARAP_RAKAM)
    return set(re.findall(r"\d+(?:[.,:/]\d+)*", s))


def dogrula(kaynak: str, cikarim: dict, sade: dict | None = None, ceviri: dict | None = None) -> dict:
    k = _norm(kaynak)
    kontroller, uyarilar = [], []

    def kontrol(alan, deger):
        if not deger:
            return
        bulundu = _norm(deger) in k
        kontroller.append({"alan": alan, "deger": deger, "bulundu": bulundu})
        if not bulundu:
            uyarilar.append(f"'{deger}' ({alan}) asıl yazıda bulunamadı. Lütfen yazıdan kontrol edin.")

    st = cikarim.get("son_tarih") or {}
    kontrol("son_tarih", st.get("deger", ""))
    for t in cikarim.get("tutarlar") or []:
        kontrol("tutar", t.get("deger", ""))
    for t in cikarim.get("diger_tarihler") or []:
        kontrol("tarih", t.get("deger", ""))
    alinti = st.get("kaynak_alinti", "")
    if alinti and _norm(alinti) not in k:
        uyarilar.append("Son tarihin dayandığı cümle yazıda birebir bulunamadı.")

    sonuc = {"kontroller": kontroller, "uyarilar": uyarilar}

    if sade is not None:
        yeni = rakamlar(sade) - rakamlar(cikarim) - rakamlar(kaynak)
        sonuc["sade_yeni_rakam"] = sorted(yeni)
        if yeni:
            uyarilar.append(f"Sade metinde asıl yazıda olmayan sayılar var: {', '.join(sorted(yeni))}")
    if ceviri is not None and sade is not None and ceviri is not sade:
        eksik = rakamlar(sade) - rakamlar(ceviri)
        fazla = rakamlar(ceviri) - rakamlar(sade)
        sonuc["ceviri_rakam_korundu"] = not eksik and not fazla
        if eksik or fazla:
            uyarilar.append("Çeviride bazı tarih veya tutarlar değişmiş olabilir. Türkçe metni esas alın.")
    return sonuc


UYARI_METNI = ("Bu bir hukuki tavsiye değildir. AçıkYazı hata yapabilir. Önemli kararlardan önce "
               "yazıyı gönderen kuruma veya barodaki adli yardım bürosuna danışın.")


def run_pipeline(metin: str, dil: str = "tr", surumler: dict | None = None) -> dict:
    s = {**VARSAYILAN, **(surumler or {})}
    cikarim = cikar(metin, s["extract"])
    sade = sadelestir(cikarim, s["simplify"])
    ceviri = cevir(sade, dil, s["translate"])
    return {
        "cikarim": cikarim,
        "sade": sade,
        "ceviri": ceviri,
        "dogrulama": dogrula(metin, cikarim, sade, ceviri),
        "uyari": UYARI_METNI,
        "model": MODEL,
        "surumler": s,
    }


if __name__ == "__main__":
    import sys
    yol = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "dev_letters" / "d1_emlak_vergisi.txt")
    dil = sys.argv[2] if len(sys.argv) > 2 else "en"
    print(json.dumps(run_pipeline(Path(yol).read_text(encoding="utf-8"), dil), ensure_ascii=False, indent=2))
