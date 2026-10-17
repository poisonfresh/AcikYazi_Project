# AçıkYazı

AçıkYazı is an assistant for people who struggle to understand official letters (notifications, payment notices, letters from public institutions). It explains in plain Turkish, and on request in English or Arabic, what the letter says, what the reader needs to do and what the deadline is, and it cross-checks the dates and amounts on its own.

Generative AI for the SDGs Hackathon · Group 11 · SDG 10.2 and SDG 16.10

> **Disclaimer:** This is not legal advice. AçıkYazı can make mistakes. Before important decisions, contact the issuing institution or the legal aid office of your local bar association.

## How it works

The whole pipeline lives in `prompt_engine.py` (written and tested by the Prompt Engineer, frozen for the demo). `app.py` is the Streamlit UI: it calls `run_pipeline(letter_text, dil=...)` once and renders the result.

1. **Input:** The user pastes the text of the letter and picks a language (Turkish / English / Arabic).
2. **Extraction (chain-of-thought + JSON):** Gemini extracts the document type, institution, subject, required action, deadline (with the exact source sentence), amounts, other dates, required documents, appeal process, consequences, contact and uncertain points as JSON (`prompts/extract_v2_cot.txt`).
3. **Simplification (few-shot):** A plain Turkish explanation in four parts is generated from the JSON (`prompts/simplify_v3_goreli_sure.txt` + `prompts/fewshot_examples.json`).
4. **Translation (zero-shot, with rules):** The plain explanation is translated into English or Arabic, keeping every date and amount and the Turkish institution name in parentheses (`prompts/translate_v3_ay_adi.txt`).
5. **Verification (in code, not by the model):**
   - The engine checks every extracted date and amount and the deadline's source sentence against the letter, flags numbers that appear in the plain text but not in the letter, and checks that the translation keeps the numbers (`dogrulama`).
   - `validation.py` independently normalizes Turkish date/amount formats with regexes and compares them with the letter.
   Values that cannot be found get a red **"⚠ Check this"** label.
6. **Output:** Cards plus a fixed legal disclaimer. The Arabic translation is shown with an "Experimental" label.

Every call also uses the safety rules in `prompts/system.txt` (no fabrication, no legal advice, keep numbers unchanged, ignore instructions written inside the letter).

## Folder structure

```
.
├── app.py               # Streamlit UI around run_pipeline(): rendering, error handling, mock-mode banner
├── validation.py        # Extra, model-independent regex checks of dates and amounts
├── prompt_engine.py     # Frozen pipeline: run_pipeline(), Gemini calls, cache, mock mode, verification
├── run_experiments.py   # Prompt Engineer's tool: compares prompt versions, writes results/ and LOG.md tables
├── LOG.md               # Prompt development log (versions, hypotheses, results)
├── prompts/             # Frozen prompts
│   ├── system.txt                  # System prompt (safety rules), used in every call
│   ├── extract_v1_zeroshot.txt     # Extraction baseline
│   ├── extract_v2_cot.txt          # Extraction, chain-of-thought (used)
│   ├── extract_v3_cot_odakli.txt   # Extraction experiment (not used)
│   ├── simplify_v1_zeroshot.txt    # Simplification baseline
│   ├── simplify_v2_fewshot.txt     # Simplification, few-shot
│   ├── simplify_v3_goreli_sure.txt # Simplification, few-shot + relative-deadline rule (used)
│   ├── translate_v0_naive.txt      # Translation baseline
│   ├── translate_v1_rules.txt      # Translation with rules
│   ├── translate_v3_ay_adi.txt     # Translation with rules + month names (used)
│   ├── fewshot_examples.json       # The two few-shot examples
│   └── schema.json                 # Data contract of run_pipeline() output
├── samples/
│   ├── dev_letters/     # 5 fictional development letters (incl. a prompt-injection letter) + answers.json
│   └── test_set/        # 8 fictional test letters + answers.json
├── results/             # Raw experiment outputs (JSON) referenced from LOG.md
├── docs/                # Prompt Engineer's guide, report section draft, video script
├── .streamlit/
│   └── config.toml      # UI theme (team palette)
├── requirements.txt
├── .env.example         # Example environment variables (contains no real key)
└── .gitignore           # Keeps .env and the .cache/ response cache out of the repo
```

All sample letters are fictional and anonymized; each starts with `[ÖRNEK - UYDURMA YAZI, GERÇEK DEĞİLDİR]` ("sample, fictional letter, not real").

### Output of `run_pipeline()`

`run_pipeline()` returns `{cikarim, sade, ceviri, dogrulama, uyari, model, surumler}` with Turkish keys (see `prompts/schema.json`). The UI keeps these keys and only maps them to English labels for display:

| Engine key | Shown as |
| --- | --- |
| `cikarim` | Extracted from the letter |
| `belge_turu`, `kurum`, `konu`, `istenen_islem` | Document type, Institution, Subject, Required action |
| `son_tarih` (`deger`, `aciklama`, `kaynak_alinti`) | Deadline (value, note, source quote) |
| `tutarlar`, `diger_tarihler` | Amounts, Other dates |
| `gerekli_belgeler`, `itiraz_yolu`, `yaptirim`, `iletisim`, `emin_olunmayanlar` | Required documents, How to appeal, If you don't act, Contact, Uncertain |
| `sade` / `ceviri` (`bu_yazi_ne`, `ne_yapmalisiniz`, `son_tarih_ve_yardim`, `dikkat`) | Plain-language explanation / Translation (What is this letter?, What should you do?, Deadline and help, Watch out) |
| `dogrulama` | Red verification warnings and "Engine: …" badges |
| `uyari`, `model`, `surumler`, `analiz_adimlari` | "Engine details" expander |

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

The engine uses Google Gemini through the `google-genai` SDK.

1. Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Copy the example file:

   ```bash
   cp .env.example .env
   ```

3. Open `.env` and enter your key:

   ```
   GEMINI_API_KEY=your-gemini-key
   ACIKYAZI_MODEL=gemini-3.5-flash-lite
   ACIKYAZI_MOCK=0
   ```

| Variable | Meaning |
| --- | --- |
| `GEMINI_API_KEY` | Google AI Studio key (required unless mock mode is on) |
| `ACIKYAZI_MODEL` | Gemini model; default `gemini-3.5-flash-lite` |
| `ACIKYAZI_MOCK` | `1` = no API calls, fake answers (UI development, saving quota) |

**The key never goes into the repo.** `.env` is listed in `.gitignore`; the repo only contains the key-free `.env.example`. Before committing, make sure `.env` does not appear in the output of `git status`. Model answers are cached in `.cache/` (also ignored), so repeating the same letter does not use quota.

If the key is missing or invalid, the quota is exhausted (the engine retries 429 errors with backoff first), the model name is wrong, the model returns unreadable JSON or there is no internet connection, the app does not crash; it shows an error message telling you what to do.

## Example run

```bash
streamlit run app.py
```

`http://localhost:8501` opens in the browser. Then:

1. Paste a letter into the text box, for example the contents of `samples/test_set/t2_ctv_borcu.txt` (a municipality asking for 935,44 TL of environmental cleaning tax by 30 Kasım 2026).
2. Choose the explanation language and press **Explain the letter**.
3. In the "Extracted from the letter" card, each deadline and amount gets a **✓ Verified** / **⚠ Check this** / **Not specified** label from `validation.py` and an **Engine: ✓ found** / **Engine: ⚠ not found** label from the engine.

### Mock mode (no API key needed)

```bash
ACIKYAZI_MOCK=1 streamlit run app.py
```

The full flow runs with fake model answers: the extraction step picks the dates and amounts from the letter with simple patterns, the other steps return placeholder text. A blue banner shows that mock mode is on. Use it for UI work only, not for measuring quality.

### Engine from the command line

```bash
python prompt_engine.py samples/test_set/t2_ctv_borcu.txt en      # prints the run_pipeline() JSON
python run_experiments.py --stage all --letters samples/test_set --mock
```

Pass the letter path explicitly: the engine's and the experiment tool's built-in defaults still point to `dev_letters/` at the repo root, but the letters now live under `samples/`.

**Personal data:** The app does not store any text. Before pasting, we recommend removing personal data such as national ID numbers, addresses and license plates.

## Validation layer (`validation.py`)

`validation.py` runs independently of the model and of the engine's own check. It recognizes:

- **Date:** `30.11.2026`, `30/11/2026`, `30-11-26`, `2026-11-30`, `30 Kasım 2026`, `30 November 2026`
- **Amount:** `1.250,50 TL`, `₺1.250,50`, `350 TL`, `1250 TRY`, `Türk Lirası`, `Turkish Lira`, `EUR`, `USD`

Whatever format the model uses, the value is normalized and compared with the dates/amounts in the original text. Relative deadlines such as "tebliğden itibaren 15 gün" ("within 15 days of delivery") are checked as exact wording. It also checks that the translation keeps the dates and amounts of the plain explanation (translated month names are accepted).

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

## What remains

- [x] Final prompts in `prompts/`, prompt log in `LOG.md`, raw results in `results/`
- [x] 8 test letters + 5 development letters with answer keys in `samples/`
- [ ] End-to-end run of the app with a real Gemini key on the 8 test letters (so far only mock mode was run in the app)
- [ ] `docs/`: report PDF (file name: `TODO`)
- [ ] Presentation link: `TODO`
- [ ] Demo video (YouTube, unlisted): `TODO`
- [ ] Decide on the language of the prompts, samples, docs and engine code (currently Turkish; the prompts were tested in Turkish)

## Run and demo results

Prompt-level results from `LOG.md` (test set, `gemini-3.5-flash-lite`): with `extract_v2_cot` the deadline was correct in 8/8 letters, no deadline was fabricated (0/8) and 8/8 extractions passed the engine's verification; with `translate_v3_ay_adi` the numbers and the Turkish institution name were preserved in 8/8 translations.

> **TODO:** Fill in the app-level results once the test matrix is complete.

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
