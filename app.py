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
from validation import find_missing_in_translation, validate_extraction  # noqa: E402

KEY_ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
LANGUAGES = {"Turkish": "tr", "English": "en", "العربية (Arabic)": "ar"}
LEGAL_DISCLAIMER = (
    "This is not legal advice. AçıkYazı can make mistakes. Before important decisions, contact the "
    "issuing institution or the legal aid office of your local bar association."
)

# Display labels for the engine's Turkish keys. The keys themselves are the engine's data contract.
EXTRACTION_LABELS = {
    "belge_turu": "Document type",
    "kurum": "Institution",
    "konu": "Subject",
    "istenen_islem": "Required action",
    "son_tarih": "Deadline",
    "tutarlar": "Amounts",
    "diger_tarihler": "Other dates",
    "gerekli_belgeler": "Required documents",
    "itiraz_yolu": "How to appeal",
    "yaptirim": "If you don't act",
    "iletisim": "Contact",
    "emin_olunmayanlar": "Uncertain",
}
HIDDEN_EXTRACTION_KEYS = {"analiz_adimlari"}
PLAIN_LABELS = {
    "bu_yazi_ne": "What is this letter?",
    "ne_yapmalisiniz": "What should you do?",
    "son_tarih_ve_yardim": "Deadline and help",
    "dikkat": "Watch out",
}
ENGINE_CHECK_LABELS = {"son_tarih": "Deadline", "tutar": "Amount", "tarih": "Other date"}

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
            "No Gemini API key found. Create a `.env` file in the project folder and add a "
            "`GEMINI_API_KEY=...` line (see `.env.example` and the README), or set `ACIKYAZI_MOCK=1` "
            "to try the app with fake responses."
        )
    model = prompt_engine.MODEL
    try:
        return run_pipeline(letter_text, dil=language)
    except genai_errors.ClientError as e:
        if e.code in (401, 403) or "API_KEY" in str(e).upper():
            raise AcikYaziError("The API key is invalid or unauthorized. Check `GEMINI_API_KEY` in your `.env` file.") from e
        if e.code == 429:
            raise AcikYaziError("API quota reached (429), even after retries. Wait a moment and try again.") from e
        if e.code == 404:
            raise AcikYaziError(f"Model not found: `{model}`. Check the `ACIKYAZI_MODEL` value.") from e
        raise AcikYaziError(f"The API rejected the request ({e.code}): {e.message}") from e
    except genai_errors.ServerError as e:
        raise AcikYaziError(f"The model server returned an error ({e.code}). Try again later.") from e
    except genai_errors.APIError as e:
        raise AcikYaziError(f"API error ({e.code}): {e.message}") from e
    except (json.JSONDecodeError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise AcikYaziError(
            f"The model's answer could not be read as the expected JSON. Try again. ({type(e).__name__}: {e})"
        ) from e
    except FileNotFoundError as e:
        raise AcikYaziError(f"A prompt file is missing: `{e.filename}`.") from e
    except Exception as e:
        raise AcikYaziError(
            f"Could not reach the model service. Check your internet connection. ({type(e).__name__}: {e})"
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
        html = badge_html("verified", "✓ Verified")
    elif check.status == "not_found":
        html = badge_html("warning", "⚠ Check this")
    else:
        html = badge_html("empty", "Not specified")
    if engine_found is True:
        html += badge_html("verified", "Engine: ✓ found")
    elif engine_found is False:
        html += badge_html("warning", "Engine: ⚠ not found")
    st.markdown(html + f'<span class="badge-note">{escape(check.message)}</span>', unsafe_allow_html=True)


def show_value_list(title: str, items: list, checks: list, engine_found: dict) -> None:
    st.markdown(f"**{title}:**" + ("" if items or checks else " _Not specified in the letter_"))
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

    engine_warnings = verification.get("uyarilar") or []
    if engine_warnings:
        st.error("**Verification warnings from the engine:**\n" + "\n".join(f"- {w}" for w in engine_warnings))
    if any(c.is_warning for c in checks):
        st.error(
            "Some dates or amounts were not found in the original letter. "
            "Please check the fields marked in red against the original."
        )

    with st.container(border=True, key="card-extraction"):
        st.subheader("Extracted from the letter")
        for key, value in extraction.items():
            if key in HIDDEN_EXTRACTION_KEYS:
                continue
            title = EXTRACTION_LABELS.get(key, key)
            if key == "son_tarih":
                deadline = value if isinstance(value, dict) else {"deger": as_text(value)}
                st.markdown(f"**{title}:** {as_text(deadline.get('deger')) or '_Not specified in the letter_'}")
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
                    st.markdown(f"**{title}:** _Not specified in the letter_")
            else:
                st.markdown(f"**{title}:** {as_text(value) or '_Not specified in the letter_'}")

    with st.container(border=True, key="card-plain"):
        st.subheader("Plain-language explanation (Turkish)")
        show_sections(plain)
        new_numbers = verification.get("sade_yeni_rakam") or []
        if new_numbers:
            badge("warning", "⚠ Check this", "Numbers not in the original letter: " + ", ".join(new_numbers))

    if translation is not None and LANGUAGES.get(language_label, "tr") != "tr":
        with st.container(border=True, key="card-translation"):
            st.subheader(f"Translation: {language_label}")
            if LANGUAGES.get(language_label) == "ar":
                st.caption(":orange-badge[Experimental] The Arabic translation has not yet been reviewed by a native speaker.")
            show_sections(translation)
            missing = find_missing_in_translation(plain, translation)
            if missing:
                badge("warning", "⚠ Check this", "These dates/amounts are missing from the translation: " + ", ".join(missing))
            else:
                badge("verified", "✓ Numbers preserved")
            if verification.get("ceviri_rakam_korundu") is False:
                badge("warning", "Engine: ⚠ numbers changed", "Some dates or amounts may differ; rely on the Turkish text.")
            elif verification.get("ceviri_rakam_korundu") is True:
                badge("verified", "Engine: ✓ numbers preserved")

    with st.expander("Engine details: model, prompt versions, reasoning steps and raw JSON"):
        st.markdown(f"**Model:** `{result.get('model', '')}`")
        st.markdown("**Prompt versions:** " + ", ".join(f"`{k}`: `{v}`" for k, v in (result.get("surumler") or {}).items()))
        if result.get("uyari"):
            st.markdown(f"**Engine disclaimer:** {result['uyari']}")
        if extraction.get("analiz_adimlari"):
            st.markdown("**Reasoning steps:**")
            for step in extraction["analiz_adimlari"]:
                st.markdown(f"- {as_text(step)}")
        st.json(result)


def main() -> None:
    st.set_page_config(page_title="AçıkYazı", page_icon="📄", layout="centered")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.title("AçıkYazı")
    st.caption(
        "Paste an official letter; we explain in plain language what it says, what you need to do and the deadline. "
        "Dates and amounts are automatically cross-checked against the original text."
    )
    st.warning(LEGAL_DISCLAIMER, icon="⚖️")
    if mock_mode():
        st.info("Mock mode is on (`ACIKYAZI_MOCK=1`): the model is not called and the answers are fake.")

    with st.sidebar:
        st.header("Model")
        st.markdown("**Provider:** Google Gemini")
        st.markdown(f"**Model:** `{prompt_engine.MODEL}`")
        if mock_mode():
            st.markdown("**Mode:** 🧪 mock (no API calls)")
        else:
            st.markdown("**API key:** " + ("✅ set" if get_api_key() else "❌ missing"))
        st.divider()
        st.header("Prompts")
        for stage, version in prompt_engine.VARSAYILAN.items():
            st.markdown(f"- {stage}: `{version}`")
        st.divider()
        st.caption(
            "The app does not store any text. Before pasting, we recommend removing personal data "
            "such as national ID numbers, addresses and license plates."
        )

    with st.form("input"):
        letter_text = st.text_area(
            "Text of the official letter",
            height=260,
            placeholder="e.g. paste the text of a notification, payment notice or institutional letter here…",
        )
        language_label = st.radio("Explanation language", list(LANGUAGES), horizontal=True)
        submitted = st.form_submit_button("Explain the letter", type="primary", width="stretch")

    if submitted:
        if not letter_text.strip():
            st.info("Please paste the text of the letter first.")
            return
        with st.spinner("Reading the letter…"):
            try:
                st.session_state["result"] = analyze(letter_text, LANGUAGES[language_label])
                st.session_state["letter_text"] = letter_text
                st.session_state["language_label"] = language_label
            except AcikYaziError as e:
                st.session_state.pop("result", None)
                st.error(str(e))
                return

    if "result" in st.session_state:
        show_results(
            st.session_state["result"],
            st.session_state.get("letter_text", ""),
            st.session_state.get("language_label", "Turkish"),
        )


if __name__ == "__main__":
    main()
