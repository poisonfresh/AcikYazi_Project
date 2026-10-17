"""AçıkYazı: an assistant that explains official letters in plain language and cross-checks their dates and amounts.

The pipeline (prompts, model calls, verification) lives in `prompt_engine.py` and is
frozen; this file is only the Streamlit UI around `run_pipeline()`.
"""

from __future__ import annotations

import json
import os
from html import escape

import streamlit as st
from dotenv import load_dotenv
from google.genai import errors as genai_errors

load_dotenv()

import prompt_engine  # noqa: E402  (reads .env and ACIKYAZI_MODEL at import time)
from prompt_engine import run_pipeline  # noqa: E402
import run_records  # noqa: E402
from validation import find_missing_in_translation, validate_extraction  # noqa: E402

KEY_ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
LANGUAGES = {"Türkçe": "tr", "İngilizce (English)": "en", "Arapça (العربية)": "ar"}
LEGAL_DISCLAIMER = (
    "Bu bir hukuki tavsiye değildir. AçıkYazı hata yapabilir. Önemli kararlardan önce yazıyı "
    "gönderen kuruma veya barodaki adli yardım bürosuna danışın."
)

# Display labels for the engine's Turkish keys. The keys themselves are the engine's data contract.
EXTRACTION_LABELS = {
    "belge_turu": "Belge türü",
    "kurum": "Kurum",
    "konu": "Konu",
    "istenen_islem": "İstenen işlem",
    "son_tarih": "Son tarih",
    "tutarlar": "Tutarlar",
    "diger_tarihler": "Diğer tarihler",
    "gerekli_belgeler": "Gerekli belgeler",
    "itiraz_yolu": "İtiraz yolu",
    "yaptirim": "Yapmazsanız ne olur?",
    "iletisim": "İletişim",
    "emin_olunmayanlar": "Emin olunmayanlar",
}
HIDDEN_EXTRACTION_KEYS = {"analiz_adimlari"}
PLAIN_LABELS = {
    "bu_yazi_ne": "Bu yazı ne?",
    "ne_yapmalisiniz": "Ne yapmalısınız?",
    "son_tarih_ve_yardim": "Son tarih ve yardım",
    "dikkat": "Dikkat",
}
ENGINE_CHECK_LABELS = {"son_tarih": "Son tarih", "tutar": "Tutar", "tarih": "Diğer tarih"}

# Team palette; theme colors live in .streamlit/config.toml.
STYLE = """
<style>
h1, h2, h3 { color: #1D2433; }
[data-testid="stCaptionContainer"], .badge-note { color: #5B6675; opacity: 1; }
[class*="st-key-card-"] {
    background-color: #F6F8FA;
    border: 1px solid #E3E7EC;
    border-radius: 0.75rem;
    padding: 1rem 1.25rem;
}
.badge {
    display: inline-block;
    padding: 0.1rem 0.55rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-right: 0.4rem;
}
.badge-warning { color: #B42318; background-color: #FDECEA; border: 1px solid #B42318; }
.badge-verified { color: #067647; background-color: #E7F6EC; border: 1px solid #067647; }
.badge-empty { color: #5B6675; background-color: #FFFFFF; border: 1px solid #5B6675; }
</style>
"""


class AcikYaziError(Exception):
    """Error with a user-facing, actionable message."""


def mock_mode() -> bool:
    return os.getenv("ACIKYAZI_MOCK") == "1"


def get_api_key() -> str | None:
    for env_name in KEY_ENV_NAMES:
        key = os.getenv(env_name)
        if not key:
            try:
                key = st.secrets.get(env_name)
            except Exception:
                key = None
            if key:
                # The engine's genai.Client() only reads the key from the environment.
                os.environ[env_name] = key
        if key and key.strip():
            return key.strip()
    return None


def analyze(letter_text: str, language: str) -> dict:
    if not mock_mode() and not get_api_key():
        raise AcikYaziError(
            "Gemini API anahtarı bulunamadı. Proje klasöründe bir `.env` dosyası oluşturup "
            "`GEMINI_API_KEY=...` satırını ekleyin (bkz. `.env.example` ve README) ya da uygulamayı sahte "
            "cevaplarla denemek için `ACIKYAZI_MOCK=1` ayarlayın."
        )
    model = prompt_engine.MODEL
    try:
        return run_pipeline(letter_text, dil=language)
    except genai_errors.ClientError as e:
        if e.code in (401, 403) or "API_KEY" in str(e).upper():
            raise AcikYaziError("API anahtarı geçersiz veya yetkisiz. `.env` içindeki `GEMINI_API_KEY` değerini kontrol edin.") from e
        if e.code == 429:
            raise AcikYaziError("API kotası doldu (429); yeniden denemeler de başarısız oldu. Biraz bekleyip tekrar deneyin.") from e
        if e.code == 404:
            raise AcikYaziError(f"Model bulunamadı: `{model}`. `ACIKYAZI_MODEL` değerini kontrol edin.") from e
        raise AcikYaziError(f"API isteği reddetti ({e.code}): {e.message}") from e
    except genai_errors.ServerError as e:
        raise AcikYaziError(f"Model sunucusu hata verdi ({e.code}). Biraz sonra tekrar deneyin.") from e
    except genai_errors.APIError as e:
        raise AcikYaziError(f"API hatası ({e.code}): {e.message}") from e
    except (json.JSONDecodeError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise AcikYaziError(
            f"Modelin cevabı beklenen JSON olarak okunamadı. Tekrar deneyin. ({type(e).__name__}: {e})"
        ) from e
    except FileNotFoundError as e:
        raise AcikYaziError(f"Bir prompt dosyası eksik: `{e.filename}`.") from e
    except Exception as e:
        raise AcikYaziError(
            f"Model servisine ulaşılamadı. İnternet bağlantınızı kontrol edin. ({type(e).__name__}: {e})"
        ) from e


def as_text(value) -> str:
    if isinstance(value, list):
        return ", ".join(as_text(x) for x in value if as_text(x))
    if isinstance(value, dict):
        return as_text(value.get("deger")) if "deger" in value else json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def badge_html(kind: str, label: str) -> str:
    """kind: "warning" (red), "verified" (green) or "empty" (gray)."""
    return f'<span class="badge badge-{kind}">{escape(label)}</span>'


def badge(kind: str, label: str, note: str = "") -> None:
    html = badge_html(kind, label)
    if note:
        html += f'<span class="badge-note">{escape(note)}</span>'
    st.markdown(html, unsafe_allow_html=True)


def check_badges(check, engine_found: bool | None) -> None:
    if check.status == "verified":
        html = badge_html("verified", "✓ Doğrulandı")
    elif check.status == "relative":
        html = badge_html("verified", "✓ Göreli süre: yazıda bulundu")
    elif check.status == "not_found":
        html = badge_html("warning", "⚠ Kontrol edin")
    else:
        html = badge_html("empty", "Belirtilmemiş")
    if engine_found is True:
        html += badge_html("verified", "Motor: ✓ bulundu")
    elif engine_found is False:
        html += badge_html("warning", "Motor: ⚠ bulunamadı")
    st.markdown(html + f'<span class="badge-note">{escape(check.message)}</span>', unsafe_allow_html=True)


def show_value_list(title: str, items: list, checks: list, engine_found: dict) -> None:
    st.markdown(f"**{title}:**" + ("" if items or checks else " _Yazıda belirtilmemiş_"))
    values = [x for x in items if as_text(x)]
    if not values and checks:
        check_badges(checks[0], None)
    for item, check in zip(values, checks):
        value = as_text(item)
        note = item.get("aciklama", "") if isinstance(item, dict) else ""
        st.markdown(f"- {value}" + (f" — {note}" if note else ""))
        check_badges(check, engine_found.get(value))


def show_sections(section: dict) -> None:
    for key, value in section.items():
        title = PLAIN_LABELS.get(key, key)
        if isinstance(value, list):
            if not value:
                continue
            st.markdown(f"**{title}**")
            for item in value:
                st.markdown(f"- {as_text(item)}")
        elif as_text(value):
            st.markdown(f"**{title}**")
            st.markdown(as_text(value))


def show_results(result: dict, letter_text: str, language_label: str) -> None:
    extraction = result.get("cikarim") or {}
    plain = result.get("sade") or {}
    translation = result.get("ceviri")
    verification = result.get("dogrulama") or {}

    checks = validate_extraction(extraction, letter_text)
    checks_by_field: dict[str, list] = {}
    for c in checks:
        checks_by_field.setdefault(c.field, []).append(c)
    engine_found: dict[str, dict] = {}
    for k in verification.get("kontroller") or []:
        engine_found.setdefault(k.get("alan"), {})[str(k.get("deger", "")).strip()] = bool(k.get("bulundu"))

    # Our summary reflects only validation.py; the engine's own warnings are shown separately below it.
    if any(c.is_warning for c in checks):
        st.error(
            "**Tarih/tutar kontrolümüz:** Bazı tarih veya tutarlar asıl yazıda bulunamadı. "
            "Lütfen kırmızı \"⚠ Kontrol edin\" etiketli alanları yazının aslından kontrol edin."
        )
    engine_warnings = verification.get("uyarilar") or []
    if engine_warnings:
        st.error(
            "**Prompt motorunun kendi uyarıları** (bizim kontrolümüzden ayrı; \"Motor:\" etiketleri):\n"
            + "\n".join(f"- {w}" for w in engine_warnings)
        )

    with st.container(border=True, key="card-extraction"):
        st.subheader("Yazıdan çıkarılan bilgiler")
        for key, value in extraction.items():
            if key in HIDDEN_EXTRACTION_KEYS:
                continue
            title = EXTRACTION_LABELS.get(key, key)
            if key == "son_tarih":
                deadline = value if isinstance(value, dict) else {"deger": as_text(value)}
                st.markdown(f"**{title}:** {as_text(deadline.get('deger')) or '_Yazıda belirtilmemiş_'}")
                check_badges(checks_by_field["son_tarih"][0], engine_found.get("son_tarih", {}).get(as_text(deadline.get("deger"))))
                if deadline.get("aciklama"):
                    st.caption(deadline["aciklama"])
                if deadline.get("kaynak_alinti"):
                    st.markdown(f"> {deadline['kaynak_alinti']}")
            elif key == "tutarlar":
                show_value_list(title, value or [], checks_by_field.get("tutarlar", []), engine_found.get("tutar", {}))
            elif key == "diger_tarihler":
                if value:
                    show_value_list(title, value, checks_by_field.get("diger_tarihler", []), engine_found.get("tarih", {}))
            elif isinstance(value, list):
                if value:
                    st.markdown(f"**{title}:**")
                    for item in value:
                        st.markdown(f"- {as_text(item)}")
                elif key != "emin_olunmayanlar":
                    st.markdown(f"**{title}:** _Yazıda belirtilmemiş_")
            else:
                st.markdown(f"**{title}:** {as_text(value) or '_Yazıda belirtilmemiş_'}")

    with st.container(border=True, key="card-plain"):
        st.subheader("Sade açıklama")
        show_sections(plain)
        new_numbers = verification.get("sade_yeni_rakam") or []
        if new_numbers:
            badge("warning", "⚠ Kontrol edin", "Asıl yazıda olmayan sayılar: " + ", ".join(new_numbers))

    if translation is not None and LANGUAGES.get(language_label, "tr") != "tr":
        with st.container(border=True, key="card-translation"):
            st.subheader(f"Çeviri: {language_label}")
            if LANGUAGES.get(language_label) == "ar":
                st.caption(":orange-badge[Deneysel] Arapça çeviri henüz anadili Arapça biri tarafından kontrol edilmedi.")
            show_sections(translation)
            missing = find_missing_in_translation(plain, translation)
            if missing:
                badge("warning", "⚠ Kontrol edin", "Çeviride şu tarih/tutarlar bulunamadı: " + ", ".join(missing))
            else:
                badge("verified", "✓ Rakamlar korundu")
            if verification.get("ceviri_rakam_korundu") is False:
                badge("warning", "Motor: ⚠ rakamlar değişmiş", "Bazı tarih veya tutarlar farklı olabilir; Türkçe metni esas alın.")
            elif verification.get("ceviri_rakam_korundu") is True:
                badge("verified", "Motor: ✓ rakamlar korundu")

    with st.expander("Motor ayrıntıları: model, prompt sürümleri, düşünme adımları ve ham JSON"):
        st.markdown(f"**Model:** `{result.get('model', '')}`")
        st.markdown("**Prompt sürümleri:** " + ", ".join(f"`{k}`: `{v}`" for k, v in (result.get("surumler") or {}).items()))
        if result.get("uyari"):
            st.markdown(f"**Motorun uyarı metni:** {result['uyari']}")
        if extraction.get("analiz_adimlari"):
            st.markdown("**Düşünme adımları:**")
            for step in extraction["analiz_adimlari"]:
                st.markdown(f"- {as_text(step)}")
        st.json(result)


def make_record(result: dict, letter_text: str, language_label: str) -> dict:
    language = LANGUAGES.get(language_label, "tr")
    translation = result.get("ceviri")
    translation_missing = (
        find_missing_in_translation(result.get("sade") or {}, translation)
        if translation is not None and language != "tr"
        else None
    )
    return run_records.build_record(
        result,
        letter_text,
        language=language,
        checks=validate_extraction(result.get("cikarim") or {}, letter_text),
        translation_missing=translation_missing,
        source=run_records.detect_sample_source(letter_text),
        mock=mock_mode(),
        origin="app",
    )


def save_run(record: dict) -> str | None:
    """Saves the record under results/app_runs/; returns the repo-relative path or None on failure."""
    stem = f"{run_records.timestamp_for_filename()}_{run_records.record_slug(record)}"
    try:
        path = run_records.save_record(record, run_records.APP_RUNS_DIR, stem)
    except (OSError, ValueError) as e:
        st.warning(f"Sonuç kaydedilemedi: {e}")
        return None
    return str(path.relative_to(run_records.ROOT))


def show_record_actions(record: dict, saved_path: str | None) -> None:
    with st.container(border=True, key="card-record"):
        st.subheader("Sonuç kaydı (JSON)")
        if saved_path:
            st.markdown(f"Kaydedildi: `{saved_path}`")
        else:
            st.caption("Bu çalıştırma diske kaydedilmedi (kenar çubuğundaki kayıt seçeneği kapalı olabilir).")
        filename = (
            os.path.basename(saved_path)
            if saved_path
            else f"{run_records.timestamp_for_filename()}_{run_records.record_slug(record)}.json"
        )
        st.download_button(
            "JSON'u indir",
            data=run_records.to_json(record).encode("utf-8"),
            file_name=filename,
            mime="application/json",
            on_click="ignore",
        )


def main() -> None:
    st.set_page_config(page_title="AçıkYazı", page_icon="📄", layout="centered")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.title("AçıkYazı")
    st.caption(
        "Resmî yazıyı yapıştırın; ne dediğini, ne yapmanız gerektiğini ve son tarihi sade dille anlatalım. "
        "Tarih ve tutarlar asıl metinle otomatik olarak karşılaştırılır."
    )
    st.warning(LEGAL_DISCLAIMER, icon="⚖️")
    if mock_mode():
        st.info("Deneme (mock) modu açık (`ACIKYAZI_MOCK=1`): model çağrılmıyor, cevaplar sahte.")

    with st.sidebar:
        st.header("Model")
        st.markdown("**Sağlayıcı:** Google Gemini")
        st.markdown(f"**Model:** `{prompt_engine.MODEL}`")
        if mock_mode():
            st.markdown("**Mod:** 🧪 deneme (API çağrısı yok)")
        else:
            st.markdown("**API anahtarı:** " + ("✅ tanımlı" if get_api_key() else "❌ eksik"))
        st.divider()
        st.header("Promptlar")
        for stage, version in prompt_engine.VARSAYILAN.items():
            st.markdown(f"- {stage}: `{version}`")
        st.divider()
        st.header("Kayıt")
        save_enabled = st.toggle(
            "Sonuçları `results/app_runs/` klasörüne kaydet",
            value=True,
            help="Her çalıştırmanın sonuç JSON'u kanıt olarak kaydedilir. Yazının tam metni ve API anahtarı kaydedilmez.",
        )
        st.divider()
        st.caption(
            "Yazının tam metni hiçbir yerde saklanmaz; kayıt açıksa yalnızca çıkarılan bilgiler ve sonuçlar "
            "`results/app_runs/` altına yazılır. Yapıştırmadan önce TC kimlik no, adres, plaka gibi "
            "kişisel bilgileri silmenizi öneririz."
        )

    with st.form("input"):
        letter_text = st.text_area(
            "Resmî yazının metni",
            height=260,
            placeholder="Örn. tebligat, ödeme bildirimi veya kurum yazısının metnini buraya yapıştırın…",
        )
        language_label = st.radio("Açıklama dili", list(LANGUAGES), horizontal=True)
        submitted = st.form_submit_button("Yazıyı açıkla", type="primary", width="stretch")

    if submitted:
        if not letter_text.strip():
            st.info("Lütfen önce yazının metnini yapıştırın.")
            return
        with st.spinner("Yazı inceleniyor…"):
            try:
                result = analyze(letter_text, LANGUAGES[language_label])
                st.session_state["result"] = result
                st.session_state["letter_text"] = letter_text
                st.session_state["language_label"] = language_label
                record = make_record(result, letter_text, language_label)
                st.session_state["record"] = record
                st.session_state["saved_path"] = save_run(record) if save_enabled else None
            except AcikYaziError as e:
                for key in ("result", "record", "saved_path"):
                    st.session_state.pop(key, None)
                st.error(str(e))
                return

    if "result" in st.session_state:
        show_results(
            st.session_state["result"],
            st.session_state.get("letter_text", ""),
            st.session_state.get("language_label", "Türkçe"),
        )
        if "record" in st.session_state:
            show_record_actions(st.session_state["record"], st.session_state.get("saved_path"))


if __name__ == "__main__":
    main()
