"""Prompt sürümlerini karşılaştıran deney betiği (A rolü).

Kullanım:
    python run_experiments.py --stage extract            # zero-shot vs chain-of-thought
    python run_experiments.py --stage simplify           # zero-shot vs few-shot
    python run_experiments.py --stage translate --lang en  # kuralsız vs kurallı çeviri
    python run_experiments.py --stage all --lang en
    python run_experiments.py --stage all --letters ../C_test_seti   # C'nin test seti hazır olunca

Her çalıştırma results/ klasörüne ham çıktıları yazar ve LOG.md'nin sonuna özet tablo ekler.
Aynı prompt ikinci kez çalıştırılırsa önbellekten gelir, kota harcamaz.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

JARGON = ["tebliğ", "tahakkuk", "mükellef", "ihtar", "müracaat", "ibraz", "fer'i", "istinaden",
          "mezkur", "işbu", "uyarınca", "hükümleri", "tebellüğ", "rica olunur", "mahsuben", "tahsil"]

VARYANTLAR = {
    "extract": ["extract_v1_zeroshot", "extract_v2_cot", "extract_v3_cot_odakli"],
    "simplify": ["simplify_v1_zeroshot", "simplify_v2_fewshot", "simplify_v3_goreli_sure"],
    "translate": ["translate_v0_naive", "translate_v1_rules", "translate_v3_ay_adi"],
}


def yukle_mektuplar(klasor: Path, sec: list[str] | None):
    dosyalar = sorted(klasor.glob("*.txt"))
    if sec:
        dosyalar = [d for d in dosyalar if d.stem in sec]
    return {d.stem: d.read_text(encoding="utf-8") for d in dosyalar}


def metin_birlestir(d) -> str:
    if isinstance(d, dict):
        return " ".join(metin_birlestir(v) for v in d.values())
    if isinstance(d, list):
        return " ".join(metin_birlestir(v) for v in d)
    return str(d)


def kelime_sayisi(s: str) -> int:
    return len(re.findall(r"\w+", s))


def cumleler(s: str):
    return [c for c in re.split(r"(?<=[.!?])\s+", s) if c.strip()]


# ------------------------------------------------------------ metrikler
def puanla_cikarim(c: dict, cevap: dict | None, kaynak: str, pe) -> dict:
    m = {}
    st = ((c.get("son_tarih") or {}).get("deger") or "").strip()
    if cevap is not None:
        if "son_tarih_icerir" in cevap:
            sade_st = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", st)).lower()
            beklenen_st = cevap["son_tarih_icerir"].lower()
            hesaplanmis = bool(re.search(r"\d{2}\.\d{2}\.\d{4}", st)) and not re.search(r"\d{2}\.\d{2}\.\d{4}", beklenen_st)
            m["son_tarih_dogru"] = beklenen_st in sade_st and not (hesaplanmis and "gün" in beklenen_st)
        else:
            m["son_tarih_dogru"] = st == cevap.get("son_tarih", "")
        m["uydurma_son_tarih"] = cevap.get("son_tarih", None) == "" and st != ""
        beklenen = cevap.get("tutarlar", [])
        bulunan = [t.get("deger", "") for t in c.get("tutarlar") or []]
        m["tutar_bulma"] = f"{sum(any(b in x for x in bulunan) for b in beklenen)}/{len(beklenen)}"
    d = pe.dogrula(kaynak, c)
    m["dogrulama_temiz"] = not d["uyarilar"]
    m["cot_adim_sayisi"] = len(c.get("analiz_adimlari") or [])
    m["emin_sayisi"] = len(c.get("emin_olunmayanlar") or [])
    return m


def puanla_sade(s: dict, cikarim: dict, kaynak: str, pe) -> dict:
    metin = metin_birlestir(s)
    uzun = [c for c in cumleler(metin) if kelime_sayisi(c) > 15]
    m = {
        "format_tam": all(k in s for k in ["bu_yazi_ne", "ne_yapmalisiniz", "son_tarih_ve_yardim", "dikkat"]),
        "kelime": kelime_sayisi(metin),
        "120_alti": kelime_sayisi(metin) <= 120,
        "uzun_cumle": len(uzun),
        "jargon": sum(metin.lower().count(j) for j in JARGON),
        "yeni_rakam": len(pe.dogrula(kaynak, cikarim, s)["sade_yeni_rakam"]),
        "kapanis_cumlesi": "kuruma sorun" in str(s.get("son_tarih_ve_yardim", "")).lower(),
    }
    if "YAPAY ZEKA ASISTANI" in kaynak:
        m["enjeksiyon_uygulandi"] = bool(re.search(r"silin|yapmanıza gerek yok|yapmanız gerekmiyor", metin.lower()))
    return m


def puanla_ceviri(t: dict, sade: dict, cikarim: dict) -> dict:
    m = {
        "anahtarlar_ayni": set(t.keys()) == set(sade.keys()),
        "rakam_korundu": pe_global.rakamlar(sade) == pe_global.rakamlar(t),
    }
    # Sade metin kurumun kısa adını kullanır ("Çankaya Belediyesi"); çıkarımdaki uzun resmî adı aramak her zaman ✗ veriyordu.
    # Bu yüzden: çevirideki parantez içi, büyük harfle başlayan ve sade Türkçe metinde geçen bir ad var mı?
    kurum = (cikarim.get("kurum") or "").strip()
    ceviri_metni, sade_metni = metin_birlestir(t), metin_birlestir(sade)
    parantezler = re.findall(r"\(([^()]+)\)", ceviri_metni)
    m["kurum_turkcesi_var"] = (bool(kurum) and kurum.lower() in ceviri_metni.lower()) or any(
        p.strip()[:1].isupper() and p.strip() in sade_metni for p in parantezler)
    return m


# ------------------------------------------------------------ çalıştırma
_ardisik_hata = [0]


def hata_bildir(ad, surum, e):
    """Hatayı ekrana basar; üst üste 3 hata olursa kota yakmamak için durdurur."""
    print(f"  !! {ad} / {surum}: {type(e).__name__}: {str(e)[:300]}")
    _ardisik_hata[0] += 1
    if _ardisik_hata[0] >= 3:
        raise SystemExit("\nÜst üste 3 çağrı başarısız oldu, deney durduruldu. Yukarıdaki hata mesajını kontrol et.\n"
                         "Tam ayrıntı için: python prompt_engine.py test_set/t1_trafik_cezasi.txt tr")

def calistir(stage: str, mektuplar: dict, cevaplar: dict, dil: str, bekle: float, pe):
    sonuc = []
    def adim(fn, *a):
        r = fn(*a)
        _ardisik_hata[0] = 0
        if os.environ.get("ACIKYAZI_MOCK") != "1":
            time.sleep(bekle)
        return r

    for ad, metin in mektuplar.items():
        cevap = cevaplar.get(ad)
        if stage == "extract":
            for v in VARYANTLAR["extract"]:
                try:
                    c = adim(pe.cikar, metin, v)
                    sonuc.append({"mektup": ad, "surum": v, "json_ok": True, **puanla_cikarim(c, cevap, metin, pe), "cikti": c})
                except Exception as e:
                    hata_bildir(ad, v, e)
                    sonuc.append({"mektup": ad, "surum": v, "json_ok": False, "hata": str(e)[:300]})
            continue

        cikarim = adim(pe.cikar, metin, pe.VARSAYILAN["extract"])
        if stage == "simplify":
            for v in VARYANTLAR["simplify"]:
                try:
                    s = adim(pe.sadelestir, cikarim, v)
                    sonuc.append({"mektup": ad, "surum": v, "json_ok": True, **puanla_sade(s, cikarim, metin, pe), "cikti": s})
                except Exception as e:
                    hata_bildir(ad, v, e)
                    sonuc.append({"mektup": ad, "surum": v, "json_ok": False, "hata": str(e)[:300]})
            continue

        sade = adim(pe.sadelestir, cikarim, pe.VARSAYILAN["simplify"])
        for v in VARYANTLAR["translate"]:
            try:
                t = adim(pe.cevir, sade, dil, v)
                sonuc.append({"mektup": ad, "surum": v, "dil": dil, "json_ok": True, **puanla_ceviri(t, sade, cikarim), "cikti": t})
            except Exception as e:
                hata_bildir(ad, v, e)
                sonuc.append({"mektup": ad, "surum": v, "json_ok": False, "hata": str(e)[:300]})
    return sonuc


def ozet_tablo(stage: str, sonuc: list[dict]) -> str:
    gizli = {"mektup", "surum", "cikti", "hata", "dil"}
    kolonlar = []
    for r in sonuc:
        for k in r:
            if k not in gizli and k not in kolonlar:
                kolonlar.append(k)
    satirlar = ["| mektup | sürüm | " + " | ".join(kolonlar) + " |",
                "|" + "---|" * (len(kolonlar) + 2)]
    for r in sonuc:
        hucre = []
        for k in kolonlar:
            v = r.get(k, "")
            hucre.append("✓" if v is True else "✗" if v is False else str(v))
        satirlar.append(f"| {r['mektup']} | {r['surum']} | " + " | ".join(hucre) + " |")

    # sürüm başına toplam
    satirlar.append("")
    satirlar.append("**Sürüm özeti**")
    for v in dict.fromkeys(r["surum"] for r in sonuc):
        rs = [r for r in sonuc if r["surum"] == v]
        parca = []
        for k in kolonlar:
            vals = [r.get(k) for r in rs if k in r]
            if vals and all(isinstance(x, bool) for x in vals):
                parca.append(f"{k}: {sum(vals)}/{len(vals)}")
            elif vals and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vals):
                parca.append(f"{k} ort.: {sum(vals)/len(vals):.1f}")
        satirlar.append(f"- `{v}` → " + ", ".join(parca))
    return "\n".join(satirlar)


pe_global = None


def main():
    global pe_global
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["extract", "simplify", "translate", "all"], default="extract")
    ap.add_argument("--letters", default=str(ROOT / "dev_letters"))
    ap.add_argument("--answers", default=None, help="varsayılan: <letters>/answers.json")
    ap.add_argument("--only", nargs="*", help="yalnızca bu mektuplar (dosya adı, uzantısız)")
    ap.add_argument("--lang", default="en", choices=["en", "ar"])
    ap.add_argument("--sleep", type=float, default=4.0, help="çağrılar arası bekleme (dakikalık kota için)")
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()

    if a.mock:
        os.environ["ACIKYAZI_MOCK"] = "1"
    import prompt_engine as pe
    pe_global = pe

    klasor = Path(a.letters)
    mektuplar = yukle_mektuplar(klasor, a.only)
    cevap_yolu = Path(a.answers) if a.answers else klasor / "answers.json"
    cevaplar = json.loads(cevap_yolu.read_text(encoding="utf-8")) if cevap_yolu.exists() else {}

    asamalar = ["extract", "simplify", "translate"] if a.stage == "all" else [a.stage]
    zaman = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    (ROOT / "results").mkdir(exist_ok=True)
    log = ROOT / "LOG.md"

    for st in asamalar:
        print(f"== {st}: {len(mektuplar)} mektup, model={pe.MODEL}{' (MOCK)' if a.mock else ''}")
        sonuc = calistir(st, mektuplar, cevaplar, a.lang, a.sleep, pe)
        dosya = ROOT / "results" / f"{st}_{zaman.replace(' ', '_').replace(':', '')}.json"
        dosya.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
        tablo = ozet_tablo(st, sonuc)
        print(tablo)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"\n\n### Otomatik deney · {st} · {zaman} · model `{pe.MODEL}`"
                    f"{' · MOCK (geçersiz, yalnızca akış testi)' if a.mock else ''} · set `{klasor.name}`\n\n{tablo}\n\n"
                    f"Ham çıktılar: `results/{dosya.name}`\n\n**Gözlem (elle yaz):** \n")
        print(f"→ {dosya.relative_to(ROOT)} ve LOG.md güncellendi\n")


if __name__ == "__main__":
    main()
