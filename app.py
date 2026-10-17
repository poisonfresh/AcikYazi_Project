"""AçıkYazı: resmî yazıları sade dille anlatan ve rakamları kendi kendine kontrol eden asistan."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from validation import ceviride_rakam_kontrol, cikarimi_dogrula

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_DOSYALARI = {
    "cikarim": "cikarim.txt",
    "sadelestirme": "sadelestirme.txt",
    "ceviri": "ceviri.txt",
}
SAGLAYICILAR = {
    "gemini": {
        "ad": "Google Gemini",
        "anahtar_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "model_env": "GEMINI_MODEL",
        "varsayilan_model": "gemini-2.5-flash",
    },
    "anthropic": {
        "ad": "Anthropic Claude",
        "anahtar_env": ("ANTHROPIC_API_KEY",),
        "model_env": "ANTHROPIC_MODEL",
        "varsayilan_model": "claude-opus-5-5",
    },
}
VARSAYILAN_SAGLAYICI = "gemini"
ANTHROPIC_MAX_TOKENS = 4096
DILLER = {"Türkçe": None, "English": "İngilizce", "العربية (Arapça)": "Arapça"}
HUKUKI_UYARI = (
    "Bu bir hukuki tavsiye değildir; emin olmadığınızda kuruma veya "
    "baro adli yardım bürosuna başvurun."
)
JSON_ALANLARI = [
    ("kurum", "Kurum"),
    ("konu", "Konu"),
    ("istenen_islem", "İstenen işlem"),
    ("son_tarih", "Son tarih"),
    ("tutar", "Tutar"),
    ("gerekli_belgeler", "Gerekli belgeler"),
    ("itiraz_yolu", "İtiraz yolu"),
]


class AcikYaziHatasi(Exception):
    """Kullanıcıya gösterilecek, anlaşılır mesajlı hata."""


def prompt_yukle(ad: str) -> str | None:
    yol = PROMPTS_DIR / PROMPT_DOSYALARI[ad]
    try:
        icerik = yol.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, IsADirectoryError):
        return None
    return icerik or None


def prompt_doldur(sablon: str, **degerler: str) -> str:
    # str.format kullanılmaz: prompt içindeki JSON süslü parantezleri bozulur.
    for anahtar, deger in degerler.items():
        sablon = sablon.replace("{" + anahtar + "}", deger)
    return sablon


def env_saglayici() -> str:
    deger = (os.getenv("LLM_PROVIDER") or VARSAYILAN_SAGLAYICI).strip().lower()
    return deger if deger in SAGLAYICILAR else VARSAYILAN_SAGLAYICI


def api_anahtari(saglayici: str) -> str | None:
    for ad in SAGLAYICILAR[saglayici]["anahtar_env"]:
        anahtar = os.getenv(ad)
        if not anahtar:
            try:
                anahtar = st.secrets.get(ad)
            except Exception:
                anahtar = None
        if anahtar and anahtar.strip():
            return anahtar.strip()
    return None


def model_adi(saglayici: str) -> str:
    bilgi = SAGLAYICILAR[saglayici]
    return (os.getenv(bilgi["model_env"]) or bilgi["varsayilan_model"]).strip()


def model_cagir(prompt: str, saglayici: str) -> str:
    anahtar = api_anahtari(saglayici)
    if not anahtar:
        env_adi = SAGLAYICILAR[saglayici]["anahtar_env"][0]
        raise AcikYaziHatasi(
            f"{SAGLAYICILAR[saglayici]['ad']} için API anahtarı bulunamadı. Proje klasöründe `.env` "
            f"dosyası oluşturup `{env_adi}=...` satırını ekleyin (bkz. `.env.example` ve README)."
        )
    model = model_adi(saglayici)
    if saglayici == "anthropic":
        metin = _anthropic_cagir(prompt, anahtar, model)
    else:
        metin = _gemini_cagir(prompt, anahtar, model)
    if not metin:
        raise AcikYaziHatasi("Model boş yanıt döndürdü (içerik filtresine takılmış olabilir).")
    return metin


def _anthropic_cagir(prompt: str, anahtar: str, model: str) -> str:
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=anahtar)
        yanit = client.messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise AcikYaziHatasi(
            "Anthropic API anahtarı geçersiz veya yetkisiz. `.env` içindeki `ANTHROPIC_API_KEY` değerini kontrol edin."
        ) from e
    except anthropic.RateLimitError as e:
        raise AcikYaziHatasi("Anthropic API kotası/hız sınırı doldu (429). Biraz bekleyip tekrar deneyin.") from e
    except anthropic.NotFoundError as e:
        raise AcikYaziHatasi(f"Model bulunamadı: `{model}`. `ANTHROPIC_MODEL` değerini kontrol edin.") from e
    except anthropic.APIConnectionError as e:
        raise AcikYaziHatasi(
            f"Anthropic servisine bağlanılamadı. İnternet bağlantınızı kontrol edin. ({type(e).__name__})"
        ) from e
    except anthropic.InternalServerError as e:
        raise AcikYaziHatasi(f"Model sunucusu hata verdi ({e.status_code}). Biraz sonra tekrar deneyin.") from e
    except anthropic.APIStatusError as e:
        raise AcikYaziHatasi(f"Anthropic API isteği reddedildi ({e.status_code}): {e.message}") from e
    except anthropic.APIError as e:
        raise AcikYaziHatasi(f"Anthropic API hatası: {e.message}") from e

    return "".join(blok.text for blok in yanit.content if getattr(blok, "type", "") == "text").strip()


def _gemini_cagir(prompt: str, anahtar: str, model: str) -> str:
    from google import genai
    from google.genai import errors as genai_errors

    try:
        client = genai.Client(api_key=anahtar)
        yanit = client.models.generate_content(model=model, contents=prompt)
    except genai_errors.ClientError as e:
        if e.code in (401, 403) or "API_KEY" in str(e).upper():
            raise AcikYaziHatasi("API anahtarı geçersiz veya yetkisiz. `.env` içindeki `GEMINI_API_KEY` değerini kontrol edin.") from e
        if e.code == 429:
            raise AcikYaziHatasi("API kotası doldu (429). Biraz bekleyip tekrar deneyin.") from e
        if e.code == 404:
            raise AcikYaziHatasi(f"Model bulunamadı: `{model}`. `GEMINI_MODEL` değerini kontrol edin.") from e
        raise AcikYaziHatasi(f"API isteği reddedildi ({e.code}): {e.message}") from e
    except genai_errors.ServerError as e:
        raise AcikYaziHatasi(f"Model sunucusu hata verdi ({e.code}). Biraz sonra tekrar deneyin.") from e
    except genai_errors.APIError as e:
        raise AcikYaziHatasi(f"API hatası ({e.code}): {e.message}") from e
    except Exception as e:
        raise AcikYaziHatasi(
            f"Model servisine bağlanılamadı. İnternet bağlantınızı kontrol edin. ({type(e).__name__}: {e})"
        ) from e

    return (getattr(yanit, "text", None) or "").strip()


def json_ayikla(yanit: str) -> dict:
    """Model çıktısından JSON nesnesini çıkarır; <dusunce> bölümünü ve ``` çitlerini atlar."""
    temiz = re.sub(r"<dusunce>.*?</dusunce>", "", yanit, flags=re.DOTALL | re.IGNORECASE)
    adaylar = re.findall(r"```(?:json)?\s*(.*?)```", temiz, flags=re.DOTALL)
    adaylar.append(temiz)

    cozucu = json.JSONDecoder()
    for aday in adaylar:
        for i in [m.start() for m in re.finditer(r"\{", aday)]:
            try:
                nesne, _ = cozucu.raw_decode(aday[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(nesne, dict):
                return nesne
    raise AcikYaziHatasi("Model çıktısı geçerli bir JSON içermiyor.")


def dusunceyi_ayikla(yanit: str) -> str | None:
    m = re.search(r"<dusunce>(.*?)</dusunce>", yanit, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def liste_metni(deger) -> str:
    if isinstance(deger, list):
        return ", ".join(str(x) for x in deger if str(x).strip())
    return str(deger or "").strip()


def eksik_prompt_uyarisi(ad: str) -> None:
    st.warning(
        f"`prompts/{PROMPT_DOSYALARI[ad]}` bulunamadı veya boş. "
        "Bu adım atlandı; prompt dosyası eklendiğinde otomatik kullanılacak."
    )


def analiz_et(metin: str, hedef_dil: str | None, saglayici: str) -> dict:
    sonuc: dict = {"hatalar": [], "atlananlar": []}

    cikarim_sablonu = prompt_yukle("cikarim")
    if not cikarim_sablonu:
        sonuc["atlananlar"].append("cikarim")
        return sonuc

    ham = model_cagir(prompt_doldur(cikarim_sablonu, metin=metin), saglayici)
    sonuc["ham_cikarim"] = ham
    sonuc["dusunce"] = dusunceyi_ayikla(ham)
    try:
        veri = json_ayikla(ham)
    except AcikYaziHatasi as e:
        sonuc["hatalar"].append(str(e))
        return sonuc
    sonuc["veri"] = veri
    sonuc["kontroller"] = cikarimi_dogrula(veri, metin)

    sade_sablonu = prompt_yukle("sadelestirme")
    if not sade_sablonu:
        sonuc["atlananlar"].append("sadelestirme")
        return sonuc
    sade = model_cagir(prompt_doldur(sade_sablonu, json=json.dumps(veri, ensure_ascii=False)), saglayici)
    sonuc["sade"] = sade

    if hedef_dil:
        ceviri_sablonu = prompt_yukle("ceviri")
        if not ceviri_sablonu:
            sonuc["atlananlar"].append("ceviri")
            return sonuc
        ceviri = model_cagir(prompt_doldur(ceviri_sablonu, dil=hedef_dil, sade_metin=sade), saglayici)
        sonuc["ceviri"] = ceviri
        sonuc["ceviri_kayip"] = ceviride_rakam_kontrol(sade, ceviri)

    return sonuc


def kontrol_etiketi(k) -> None:
    if k.durum == "dogrulandi":
        st.markdown(f":green-badge[✓ Doğrulandı] {k.aciklama}")
    elif k.durum == "bulunamadi":
        st.markdown(f":red-badge[⚠ Kontrol edin] {k.aciklama}")
    else:
        st.markdown(f":gray-badge[Belirtilmemiş] {k.aciklama}")


def sonuclari_goster(sonuc: dict, dil_etiketi: str) -> None:
    for ad in sonuc["atlananlar"]:
        eksik_prompt_uyarisi(ad)
    for hata in sonuc["hatalar"]:
        st.error(hata)
        if sonuc.get("ham_cikarim"):
            with st.expander("Modelin ham çıktısı"):
                st.code(sonuc["ham_cikarim"])

    veri = sonuc.get("veri")
    if veri is None:
        return

    kontroller = {k.alan: k for k in sonuc["kontroller"]}
    if any(k.uyari for k in kontroller.values()):
        st.error(
            "Bazı tarih veya tutarlar asıl metinde bulunamadı. "
            "Lütfen kırmızı etiketli alanları yazının aslından kontrol edin."
        )

    with st.container(border=True):
        st.subheader("Yazıdan çıkarılan bilgiler")
        for alan, baslik in JSON_ALANLARI:
            deger = liste_metni(veri.get(alan))
            st.markdown(f"**{baslik}:** {deger or '_Yazıda belirtilmemiş_'}")
            if alan in kontroller:
                kontrol_etiketi(kontroller[alan])

        emin_olunmayanlar = veri.get("emin_olunmayanlar") or []
        if emin_olunmayanlar:
            st.markdown("**Emin olunmayanlar:**")
            for madde in emin_olunmayanlar if isinstance(emin_olunmayanlar, list) else [emin_olunmayanlar]:
                st.markdown(f"- {madde}")

    if sonuc.get("sade"):
        with st.container(border=True):
            st.subheader("Sade açıklama")
            st.markdown(sonuc["sade"])

    if sonuc.get("ceviri"):
        with st.container(border=True):
            st.subheader(f"Çeviri: {dil_etiketi}")
            if "Arapça" in dil_etiketi:
                st.caption(":orange-badge[Deneysel] Arapça çeviri henüz anadili Arapça biri tarafından doğrulanmadı.")
            st.markdown(sonuc["ceviri"])
            if sonuc.get("ceviri_kayip"):
                st.markdown(
                    ":red-badge[⚠ Kontrol edin] Çeviride şu tarih/tutarlar bulunamadı: "
                    + ", ".join(sonuc["ceviri_kayip"])
                )
            else:
                st.markdown(":green-badge[✓ Rakamlar korundu]")

    with st.expander("Ham JSON ve modelin düşünce adımları"):
        st.json(veri)
        if sonuc.get("dusunce"):
            st.text(sonuc["dusunce"])


def main() -> None:
    st.set_page_config(page_title="AçıkYazı", page_icon="📄", layout="centered")
    st.title("AçıkYazı")
    st.caption(
        "Resmî yazıyı yapıştırın; ne dediğini, ne yapmanız gerektiğini ve son tarihi sade dille anlatalım. "
        "Tarih ve tutarlar asıl metinle otomatik karşılaştırılır."
    )
    st.warning(HUKUKI_UYARI, icon="⚖️")

    with st.sidebar:
        st.header("Model")
        secenekler = list(SAGLAYICILAR)
        saglayici = st.radio(
            "Sağlayıcı",
            secenekler,
            index=secenekler.index(env_saglayici()),
            format_func=lambda k: SAGLAYICILAR[k]["ad"],
            help="Varsayılan `.env` içindeki `LLM_PROVIDER` değerinden gelir.",
        )
        st.markdown(f"**Model:** `{model_adi(saglayici)}`")
        st.markdown("**API anahtarı:** " + ("✅ tanımlı" if api_anahtari(saglayici) else "❌ eksik"))
        st.divider()
        st.header("Durum")
        st.markdown("**Promptlar:**")
        for ad, dosya in PROMPT_DOSYALARI.items():
            st.markdown(f"- `{dosya}`: " + ("✅" if prompt_yukle(ad) else "❌ eksik"))
        st.divider()
        st.caption(
            "Uygulama hiçbir metni saklamaz. Yapıştırmadan önce TC kimlik no, adres, plaka "
            "gibi kişisel bilgileri silmenizi öneririz."
        )

    with st.form("girdi"):
        metin = st.text_area(
            "Resmî yazının metni",
            height=260,
            placeholder="Örn. tebligat, ödeme bildirimi veya kurum yazısının metnini buraya yapıştırın…",
        )
        dil_etiketi = st.radio("Açıklama dili", list(DILLER), horizontal=True)
        gonder = st.form_submit_button("Yazıyı açıkla", type="primary", width="stretch")

    if gonder:
        if not metin.strip():
            st.info("Lütfen önce yazının metnini yapıştırın.")
            return
        with st.spinner("Yazı inceleniyor…"):
            try:
                st.session_state["sonuc"] = analiz_et(metin, DILLER[dil_etiketi], saglayici)
                st.session_state["dil_etiketi"] = dil_etiketi
            except AcikYaziHatasi as e:
                st.session_state.pop("sonuc", None)
                st.error(str(e))
                return

    if "sonuc" in st.session_state:
        sonuclari_goster(st.session_state["sonuc"], st.session_state.get("dil_etiketi", ""))


if __name__ == "__main__":
    main()
