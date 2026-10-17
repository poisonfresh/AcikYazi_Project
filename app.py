"""AçıkYazı: an assistant that explains official letters in plain language and cross-checks their dates and amounts."""

from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from validation import find_missing_in_translation, validate_extraction

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_FILES = {
    "extraction": "extraction.txt",
    "simplification": "simplification.txt",
    "translation": "translation.txt",
}
PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "key_env": ("ANTHROPIC_API_KEY",),
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-opus-5-5",
    },
}
DEFAULT_PROVIDER = "gemini"
ANTHROPIC_MAX_TOKENS = 4096
LANGUAGES = {"Turkish": None, "English": "English", "العربية (Arabic)": "Arabic"}
LEGAL_DISCLAIMER = (
    "This is not legal advice. If you are unsure, contact the issuing institution "
    "or the legal aid office of your local bar association."
)
JSON_FIELDS = [
    ("institution", "Institution"),
    ("subject", "Subject"),
    ("required_action", "Required action"),
    ("deadline", "Deadline"),
    ("amount", "Amount"),
    ("required_documents", "Required documents"),
    ("appeal_process", "How to appeal"),
]
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


def load_prompt(name: str) -> str | None:
    path = PROMPTS_DIR / PROMPT_FILES[name]
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, IsADirectoryError):
        return None
    return content or None


def fill_prompt(template: str, **values: str) -> str:
    # Not str.format: it would break the literal JSON braces inside the prompts.
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def provider_from_env() -> str:
    value = (os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    return value if value in PROVIDERS else DEFAULT_PROVIDER


def get_api_key(provider: str) -> str | None:
    for env_name in PROVIDERS[provider]["key_env"]:
        key = os.getenv(env_name)
        if not key:
            try:
                key = st.secrets.get(env_name)
            except Exception:
                key = None
        if key and key.strip():
            return key.strip()
    return None


def get_model_name(provider: str) -> str:
    info = PROVIDERS[provider]
    return (os.getenv(info["model_env"]) or info["default_model"]).strip()


def call_model(prompt: str, provider: str) -> str:
    key = get_api_key(provider)
    if not key:
        env_name = PROVIDERS[provider]["key_env"][0]
        raise AcikYaziError(
            f"No API key found for {PROVIDERS[provider]['name']}. Create a `.env` file in the project folder "
            f"and add a `{env_name}=...` line (see `.env.example` and the README)."
        )
    model = get_model_name(provider)
    if provider == "anthropic":
        text = _call_anthropic(prompt, key, model)
    else:
        text = _call_gemini(prompt, key, model)
    if not text:
        raise AcikYaziError("The model returned an empty response (it may have been blocked by a content filter).")
    return text


def _call_anthropic(prompt: str, key: str, model: str) -> str:
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise AcikYaziError(
            "The Anthropic API key is invalid or unauthorized. Check `ANTHROPIC_API_KEY` in your `.env` file."
        ) from e
    except anthropic.RateLimitError as e:
        raise AcikYaziError("Anthropic API quota or rate limit reached (429). Wait a moment and try again.") from e
    except anthropic.NotFoundError as e:
        raise AcikYaziError(f"Model not found: `{model}`. Check the `ANTHROPIC_MODEL` value.") from e
    except anthropic.APIConnectionError as e:
        raise AcikYaziError(
            f"Could not connect to the Anthropic service. Check your internet connection. ({type(e).__name__})"
        ) from e
    except anthropic.InternalServerError as e:
        raise AcikYaziError(f"The model server returned an error ({e.status_code}). Try again later.") from e
    except anthropic.APIStatusError as e:
        raise AcikYaziError(f"The Anthropic API rejected the request ({e.status_code}): {e.message}") from e
    except anthropic.APIError as e:
        raise AcikYaziError(f"Anthropic API error: {e.message}") from e

    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()


def _call_gemini(prompt: str, key: str, model: str) -> str:
    from google import genai
    from google.genai import errors as genai_errors

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model=model, contents=prompt)
    except genai_errors.ClientError as e:
        if e.code in (401, 403) or "API_KEY" in str(e).upper():
            raise AcikYaziError("The API key is invalid or unauthorized. Check `GEMINI_API_KEY` in your `.env` file.") from e
        if e.code == 429:
            raise AcikYaziError("API quota reached (429). Wait a moment and try again.") from e
        if e.code == 404:
            raise AcikYaziError(f"Model not found: `{model}`. Check the `GEMINI_MODEL` value.") from e
        raise AcikYaziError(f"The API rejected the request ({e.code}): {e.message}") from e
    except genai_errors.ServerError as e:
        raise AcikYaziError(f"The model server returned an error ({e.code}). Try again later.") from e
    except genai_errors.APIError as e:
        raise AcikYaziError(f"API error ({e.code}): {e.message}") from e
    except Exception as e:
        raise AcikYaziError(
            f"Could not connect to the model service. Check your internet connection. ({type(e).__name__}: {e})"
        ) from e

    return (getattr(response, "text", None) or "").strip()


def extract_json(response: str) -> dict:
    """Pulls the JSON object out of the model output, skipping the <thinking> block and ``` fences."""
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", response, flags=re.DOTALL | re.IGNORECASE)
    candidates = re.findall(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    candidates.append(cleaned)

    decoder = json.JSONDecoder()
    for candidate in candidates:
        for i in [m.start() for m in re.finditer(r"\{", candidate)]:
            try:
                obj, _ = decoder.raw_decode(candidate[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    raise AcikYaziError("The model output does not contain valid JSON.")


def extract_thinking(response: str) -> str | None:
    m = re.search(r"<thinking>(.*?)</thinking>", response, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def as_text(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(x) for x in value if str(x).strip())
    return str(value or "").strip()


def missing_prompt_warning(name: str) -> None:
    st.warning(
        f"`prompts/{PROMPT_FILES[name]}` is missing or empty. "
        "This step was skipped; it will run automatically once the prompt file is added."
    )


def analyze(letter_text: str, target_language: str | None, provider: str) -> dict:
    result: dict = {"errors": [], "skipped": []}

    extraction_template = load_prompt("extraction")
    if not extraction_template:
        result["skipped"].append("extraction")
        return result

    raw = call_model(fill_prompt(extraction_template, letter_text=letter_text), provider)
    result["raw_extraction"] = raw
    result["thinking"] = extract_thinking(raw)
    try:
        data = extract_json(raw)
    except AcikYaziError as e:
        result["errors"].append(str(e))
        return result
    result["data"] = data
    result["checks"] = validate_extraction(data, letter_text)

    simplification_template = load_prompt("simplification")
    if not simplification_template:
        result["skipped"].append("simplification")
        return result
    plain = call_model(fill_prompt(simplification_template, json=json.dumps(data, ensure_ascii=False)), provider)
    result["plain_text"] = plain

    if target_language:
        translation_template = load_prompt("translation")
        if not translation_template:
            result["skipped"].append("translation")
            return result
        translation = call_model(
            fill_prompt(translation_template, language=target_language, plain_text=plain), provider
        )
        result["translation"] = translation
        result["translation_missing"] = find_missing_in_translation(plain, translation)

    return result


def badge(kind: str, label: str, note: str = "") -> None:
    """kind: "warning" (red), "verified" (green) or "empty" (gray)."""
    html = f'<span class="badge badge-{kind}">{escape(label)}</span>'
    if note:
        html += f'<span class="badge-note">{escape(note)}</span>'
    st.markdown(html, unsafe_allow_html=True)


def check_badge(check) -> None:
    if check.status == "verified":
        badge("verified", "✓ Verified", check.message)
    elif check.status == "not_found":
        badge("warning", "⚠ Check this", check.message)
    else:
        badge("empty", "Not specified", check.message)


def show_results(result: dict, language_label: str) -> None:
    for name in result["skipped"]:
        missing_prompt_warning(name)
    for error in result["errors"]:
        st.error(error)
        if result.get("raw_extraction"):
            with st.expander("Raw model output"):
                st.code(result["raw_extraction"])

    data = result.get("data")
    if data is None:
        return

    checks = {c.field: c for c in result["checks"]}
    if any(c.is_warning for c in checks.values()):
        st.error(
            "Some dates or amounts were not found in the original letter. "
            "Please check the fields marked in red against the original."
        )

    with st.container(border=True, key="card-extraction"):
        st.subheader("Extracted from the letter")
        for field, title in JSON_FIELDS:
            value = as_text(data.get(field))
            st.markdown(f"**{title}:** {value or '_Not specified in the letter_'}")
            if field in checks:
                check_badge(checks[field])

        uncertain = data.get("uncertain_fields") or []
        if uncertain:
            st.markdown("**Uncertain:**")
            for item in uncertain if isinstance(uncertain, list) else [uncertain]:
                st.markdown(f"- {item}")

    if result.get("plain_text"):
        with st.container(border=True, key="card-plain"):
            st.subheader("Plain-language explanation")
            st.markdown(result["plain_text"])

    if result.get("translation"):
        with st.container(border=True, key="card-translation"):
            st.subheader(f"Translation: {language_label}")
            if "Arabic" in language_label:
                st.caption(":orange-badge[Experimental] The Arabic translation has not yet been reviewed by a native speaker.")
            st.markdown(result["translation"])
            if result.get("translation_missing"):
                badge(
                    "warning",
                    "⚠ Check this",
                    "These dates/amounts are missing from the translation: " + ", ".join(result["translation_missing"]),
                )
            else:
                badge("verified", "✓ Numbers preserved")

    with st.expander("Raw JSON and the model's reasoning steps"):
        st.json(data)
        if result.get("thinking"):
            st.text(result["thinking"])


def main() -> None:
    st.set_page_config(page_title="AçıkYazı", page_icon="📄", layout="centered")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.title("AçıkYazı")
    st.caption(
        "Paste an official letter; we explain in plain language what it says, what you need to do and the deadline. "
        "Dates and amounts are automatically cross-checked against the original text."
    )
    st.warning(LEGAL_DISCLAIMER, icon="⚖️")

    with st.sidebar:
        st.header("Model")
        options = list(PROVIDERS)
        provider = st.radio(
            "Provider",
            options,
            index=options.index(provider_from_env()),
            format_func=lambda k: PROVIDERS[k]["name"],
            help="Defaults to the `LLM_PROVIDER` value in `.env`.",
        )
        st.markdown(f"**Model:** `{get_model_name(provider)}`")
        st.markdown("**API key:** " + ("✅ set" if get_api_key(provider) else "❌ missing"))
        st.divider()
        st.header("Status")
        st.markdown("**Prompts:**")
        for name, filename in PROMPT_FILES.items():
            st.markdown(f"- `{filename}`: " + ("✅" if load_prompt(name) else "❌ missing"))
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
                st.session_state["result"] = analyze(letter_text, LANGUAGES[language_label], provider)
                st.session_state["language_label"] = language_label
            except AcikYaziError as e:
                st.session_state.pop("result", None)
                st.error(str(e))
                return

    if "result" in st.session_state:
        show_results(st.session_state["result"], st.session_state.get("language_label", ""))


if __name__ == "__main__":
    main()
