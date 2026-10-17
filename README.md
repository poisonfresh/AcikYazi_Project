# AçıkYazı

AçıkYazı is an assistant for people who struggle to understand official letters (notifications, payment notices, letters from public institutions). It explains in plain Turkish, and on request in English or Arabic, what the letter says, what the reader needs to do and what the deadline is, and it cross-checks the dates and amounts on its own.

Generative AI for the SDGs Hackathon · Group 11 · SDG 10.2 and SDG 16.10

> **Disclaimer:** This is not legal advice. If you are unsure, contact the issuing institution or the legal aid office of your local bar association.

## How it works

1. **Input:** The user pastes the text of the letter and picks a language (Turkish / English / Arabic).
2. **Extraction:** The model extracts the institution, subject, required action, deadline, amount, required documents and appeal process as JSON (`prompts/extraction.txt`).
3. **Validation:** The extracted deadline and amount are searched for in the original text with Python regexes. A value that cannot be found gets a red **"Check this"** label. This step is independent of the model (`validation.py`).
4. **Simplification:** A plain-language explanation in three sections is generated from the JSON (`prompts/simplification.txt`).
5. **Translation:** The plain text is translated into the selected language; if a date or amount is lost in translation, a warning is shown again (`prompts/translation.txt`).
6. **Output:** Card view plus a fixed legal disclaimer. The Arabic translation is shown with an "Experimental" label.

## Folder structure

```
.
├── app.py             # Streamlit UI, Gemini/Claude API connection, JSON parsing, error handling
├── validation.py      # Validation layer: date/amount regex checks
├── prompts/           # Prompts (added by the Prompt Engineer role)
├── samples/           # Fictional, anonymized sample letters (added by the Research/Testing role)
├── docs/              # Report PDF and other documents
├── .streamlit/
│   └── config.toml    # UI theme (team palette)
├── requirements.txt
├── .env.example       # Example environment variables (contains no real key)
└── .gitignore         # Keeps the .env file out of the repo
```

### Prompt files

The app reads its prompts from `prompts/` under the following names. If a file is missing, that step is skipped and a warning is shown in the UI; the app does not crash.

| File | Step | Placeholders used |
| --- | --- | --- |
| `prompts/extraction.txt` | Extraction (CoT + JSON) | `{letter_text}` |
| `prompts/simplification.txt` | Simplification (few-shot) | `{json}` |
| `prompts/translation.txt` | Translation (zero-shot) | `{language}`, `{plain_text}` |

`{language}` is filled with `English` or `Arabic`.

After an optional `<thinking>…</thinking>` block, the extraction output must be a JSON object with these fields:

```json
{"institution":"","subject":"","required_action":"","deadline":"","amount":"",
 "required_documents":[],"appeal_process":"","uncertain_fields":[]}
```

The app also finds the JSON when it comes inside a ` ```json ` fence. If there is no valid JSON, the user sees an error and the model's raw output.

## Setup

Requires Python 3.10 or later.

```bash
git clone <repo-url>
cd <repo-folder>

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## API key configuration

The app supports two model providers; a key for at least one of them is enough:

| Provider | `LLM_PROVIDER` | Key variable | Model variable (default) | Where to get a key |
| --- | --- | --- | --- | --- |
| Google Gemini | `gemini` | `GEMINI_API_KEY` | `GEMINI_MODEL` (`gemini-2.5-flash`) | [Google AI Studio](https://aistudio.google.com/apikey) (has a free tier) |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` (`claude-opus-5-5`) | [Anthropic Console](https://console.anthropic.com/settings/keys) |

1. Get an API key from the provider you want to use.
2. Copy the example file:

   ```bash
   cp .env.example .env
   ```

3. Open `.env`, enter your key(s) and choose the default provider:

   ```
   LLM_PROVIDER=anthropic          # or gemini

   GEMINI_API_KEY=your-gemini-key
   GEMINI_MODEL=gemini-2.5-flash

   ANTHROPIC_API_KEY=your-anthropic-key
   ANTHROPIC_MODEL=claude-opus-5-5
   ```

   You can leave the key of a provider you don't use empty. The model variables are optional; if empty, the default from the table is used.

4. You can also switch providers while the app is running: the **Provider** selector in the sidebar overrides `LLM_PROVIDER` for that session. The selected provider's model and key status (✅ / ❌) are shown right below it.

**The key never goes into the repo.** `.env` is listed in `.gitignore`; the repo only contains the key-free `.env.example`. Before committing, make sure `.env` does not appear in the output of `git status`.

If the key is missing or invalid, the quota or rate limit is exhausted, the model name is wrong or there is no internet connection, the app does not crash with either provider; it shows an error message in the UI telling you what to do. The sidebar shows the status of the key and of the prompt files.

## Example run

```bash
streamlit run app.py
```

`http://localhost:8501` opens in the browser. Then:

1. Paste a sample letter into the text box. Letters are in Turkish, for example (a municipality reminding a taxpayer that their 2026 environmental cleaning tax of 1,250.50 TL is due by 30.11.2026):

   ```
   T.C. X BELEDİYESİ
   Sayın mükellef, 2026 yılı çevre temizlik vergisi borcunuz 1.250,50 TL'dir.
   Borcun en geç 30.11.2026 tarihine kadar ödenmesi gerekmektedir.
   ```

2. Choose the explanation language and press **Explain the letter**.
3. In the "Extracted from the letter" card, a **✓ Verified** or **⚠ Check this** label appears next to the deadline and the amount.

**Personal data:** The app does not store any text. Before pasting, we recommend removing personal data such as national ID numbers, addresses and license plates.

## Validation layer

`validation.py` runs independently of the model and recognizes these formats:

- **Date:** `30.11.2026`, `30/11/2026`, `30-11-26`, `2026-11-30`, `30 Kasım 2026`, `30 November 2026`
- **Amount:** `1.250,50 TL`, `₺1.250,50`, `350 TL`, `1250 TRY`, `Türk Lirası`, `Turkish Lira`, `EUR`, `USD`

Whatever format the model uses, the value is normalized and compared with the dates/amounts in the original text. If it is not found, the user sees a red warning.

## Color palette

The UI uses the team's shared palette. The theme is in `.streamlit/config.toml`; the badge and card styles are in the `STYLE` block in `app.py`.

| Usage | Text color | Background |
| --- | --- | --- |
| Text and headings | `#1D2433` | `#FFFFFF` |
| Cards | `#1D2433` | `#F6F8FA` |
| Warning ("⚠ Check this": date/amount not in the original) | `#B42318` | `#FDECEA` |
| Verified / positive | `#067647` | `#E7F6EC` |
| Secondary text and the "Not specified" badge | `#5B6675` | `#FFFFFF` |

---

<!-- ============================================================
     SECTIONS TO FILL IN WHEN THE PROJECT IS FINISHED
     Replace the "TODO" lines below with the real content.
     ============================================================ -->

## Project files (to be filled in when the project is finished)

> **TODO:** Update this list once the final files are added to the repo.

- [ ] `prompts/extraction.txt`, `prompts/simplification.txt`, `prompts/translation.txt`: final prompts
- [ ] `prompts/LOG.md`: prompt version experiments and notes
- [ ] `samples/`: 8 sample letters and answer key
- [ ] `docs/`: report PDF (file name: `TODO`)
- [ ] Presentation link: `TODO`
- [ ] Demo video (YouTube, unlisted): `TODO`

## Run and demo results (to be filled in when the project is finished)

> **TODO:** Fill in the results once the test matrix is complete.

| Test | Result |
| --- | --- |
| Accuracy (deadline and amount, 8 letters) | TODO / 8 |
| Hallucination (letter without a deadline / corrupted letter) | TODO |
| Readability (2 people outside the team) | TODO |
| Translation (EN / AR, are the numbers preserved?) | TODO |
| Out-of-scope request | TODO |
| Bias | TODO |

> **TODO:** Demo screenshots (e.g. add them under `docs/` and link them here).

## Team

| Role | Member |
| --- | --- |
| Prompt Engineer | TODO |
| Developer | Barış |
| Research, Testing and Ethics | TODO |
| Presentation, Video and Submission | TODO |
