# AçıkYazı

AçıkYazı is an assistant for people who struggle to understand official letters (notifications, payment notices, letters from public institutions). It explains in plain Turkish, and on request in English or Arabic, what the letter says, what the reader needs to do and what the deadline is, and it cross-checks the dates and amounts on its own.

Generative AI for the SDGs Hackathon · Group 11 · SDG 10.2 and SDG 16.10

> **Disclaimer:** This is not legal advice. AçıkYazı can make mistakes. Before important decisions, contact the issuing institution or the legal aid office of your local bar association.

> **Language note:** This README is in English, but the app's user interface and the evaluation (prompts, sample letters, test results) are intentionally in Turkish, because the app processes Turkish official documents for Turkish-reading users. The explanation can still be translated into English or Arabic in the app.

## How it works

The whole pipeline lives in `prompt_engine.py` (written and tested by the Prompt Engineer, frozen for the demo). `app.py` is the Streamlit UI: it calls `run_pipeline(letter_text, dil=...)` once and renders the result.

1. **Input:** The user pastes the text of the letter and picks a language (Turkish / English / Arabic).
2. **Extraction (chain-of-thought + JSON):** Gemini extracts the document type, institution, subject, required action, deadline (with the exact source sentence), amounts, other dates, required documents, appeal process, consequences, contact and uncertain points as JSON (`prompts/extract_v2_cot.txt`).
3. **Simplification (few-shot):** A plain Turkish explanation in four parts is generated from the JSON (`prompts/simplify_v3_goreli_sure.txt` + `prompts/fewshot_examples.json`).
4. **Translation (zero-shot, with rules):** The plain explanation is translated into English or Arabic, keeping every date and amount and the Turkish institution name in parentheses (`prompts/translate_v3_ay_adi.txt`).
5. **Verification (in code, not by the model):**
   - The engine checks every extracted date and amount and the deadline's source sentence against the letter, flags numbers that appear in the plain text but not in the letter, and checks that the translation keeps the numbers (`dogrulama`).
   - `validation.py` independently normalizes Turkish date/amount formats with regexes and compares them with the letter.
   Values that cannot be found get a red **"⚠ Kontrol edin"** ("check this") label.
6. **Output:** Cards plus a fixed legal disclaimer. The Arabic translation is shown with a "Deneysel" ("experimental") label.

Every call also uses the safety rules in `prompts/system.txt` (no fabrication, no legal advice, keep numbers unchanged, ignore instructions written inside the letter).

## Folder structure

```
.
├── app.py               # Streamlit UI around run_pipeline(): rendering, error handling, mock-mode banner
├── validation.py        # Extra, model-independent regex checks of dates and amounts
├── prompt_engine.py     # Frozen pipeline: run_pipeline(), Gemini calls, cache, mock mode, verification
├── run_records.py       # Builds/saves run records (result JSON + metadata) for the app and run_samples.py
├── run_samples.py       # Batch test: all sample letters → results/real_api/<date>/ + ozet.md / ozet.csv
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
│   ├── app_runs/        # One JSON per "Yazıyı açıkla" run in the app (committed as evidence)
│   └── real_api/        # run_samples.py output, one folder per date (committed as evidence)
├── docs/                # Prompt Engineer's guide, report section draft, video script
├── .streamlit/
│   └── config.toml      # UI theme (team palette)
├── requirements.txt
├── .env.example         # Example environment variables (contains no real key)
└── .gitignore           # Keeps .env and the .cache/ response cache out of the repo
```

All sample letters are fictional and anonymized; each starts with `[ÖRNEK - UYDURMA YAZI, GERÇEK DEĞİLDİR]` ("sample, fictional letter, not real").

### Output of `run_pipeline()`

`run_pipeline()` returns `{cikarim, sade, ceviri, dogrulama, uyari, model, surumler}` with Turkish keys (see `prompts/schema.json`). The UI keeps these keys and only maps them to Turkish display labels:

| Engine key | Shown in the UI as |
| --- | --- |
| `cikarim` | Yazıdan çıkarılan bilgiler |
| `belge_turu`, `kurum`, `konu`, `istenen_islem` | Belge türü, Kurum, Konu, İstenen işlem |
| `son_tarih` (`deger`, `aciklama`, `kaynak_alinti`) | Son tarih (value, note, source quote) |
| `tutarlar`, `diger_tarihler` | Tutarlar, Diğer tarihler |
| `gerekli_belgeler`, `itiraz_yolu`, `yaptirim`, `iletisim`, `emin_olunmayanlar` | Gerekli belgeler, İtiraz yolu, Yapmazsanız ne olur?, İletişim, Emin olunmayanlar |
| `sade` / `ceviri` (`bu_yazi_ne`, `ne_yapmalisiniz`, `son_tarih_ve_yardim`, `dikkat`) | Sade açıklama / Çeviri (Bu yazı ne?, Ne yapmalısınız?, Son tarih ve yardım, Dikkat) |
| `dogrulama` | Red verification warnings and "Motor: …" badges |
| `uyari`, `model`, `surumler`, `analiz_adimlari` | "Motor ayrıntıları" expander |

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
2. Choose the explanation language ("Açıklama dili") and press **Yazıyı açıkla** ("explain the letter").
3. In the "Yazıdan çıkarılan bilgiler" card, each deadline and amount gets a **✓ Doğrulandı** (verified) / **⚠ Kontrol edin** (check this) / **Belirtilmemiş** (not specified) label from `validation.py` and a **Motor: ✓ bulundu** / **Motor: ⚠ bulunamadı** (engine: found / not found) label from the engine.

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

### Saving results (JSON)

After every **Yazıyı açıkla** run the app saves the full `run_pipeline()` result to `results/app_runs/<YYYY-MM-DD_HHMMSS>_<slug>.json` and shows a **JSON'u indir** (download JSON) button. Saving can be switched off with the **Kayıt** toggle in the sidebar; the download button always works. Each record contains:

- `saved_at`, `origin` (`app` or `run_samples`), `model`, `prompt_versions`, `language`, `mock`
- `source`: the sample letter name if the pasted text is one of `samples/` (e.g. `test_set/t1_trafik_cezasi`, also used as the slug), otherwise `null`; plus the text length and the SHA-256 of its first 200 characters
- `our_validation`: the `validation.py` checks (and missing translation values)
- `result`: the complete engine output, including the engine's own warnings

Saved runs are meant to be committed as evidence, so they are not in `.gitignore`. Mock runs get a `_mock` suffix. The API key is never written (saving refuses a record that would contain it).

**Personal data:** The full letter text is never stored, but the saved result contains the extracted information (institution, dates, amounts, quotes). Before pasting a real letter, remove personal data such as national ID numbers, addresses and license plates, or switch saving off.

## Validation layer (`validation.py`)

`validation.py` runs independently of the model and of the engine's own check. It recognizes:

- **Date:** `30.11.2026`, `30/11/2026`, `30-11-26`, `2026-11-30`, `30 Kasım 2026`, `30 November 2026`
- **Amount:** `1.250,50 TL`, `₺1.250,50`, `350 TL`, `1250 TRY`, `Türk Lirası`, `Turkish Lira`, `EUR`, `USD`
- **Relative deadline:** `tebliğden itibaren 15 gün`, `30 gün içinde`, `15 (on beş) gün`, `iki hafta`, `1 ay`, `10 iş günü` (digits or Turkish number words; units gün, iş günü, hafta, ay, yıl)

Whatever format the model uses, the value is normalized and compared with the dates/amounts in the original text. A relative deadline whose number and unit (e.g. 15 gün) appear in the letter gets the green **"✓ Göreli süre: yazıda bulundu"** ("relative period: found in the letter") badge instead of a warning; the exact date then depends on the delivery (tebliğ) date, which the letter does not contain. If the period is not in the letter, it stays red. The engine's own check (`dogrula()` in `prompt_engine.py`) is shown separately in the "Prompt motorunun kendi uyarıları" box as an extra safety layer; the red summary at the top ("Tarih/tutar kontrolümüz: …") reflects only `validation.py`. Since the Prompt Engineer's second version of the engine, `dogrula()` no longer raises false alarms for relative deadlines or `kaynak_alinti` quotes ending in "..."; it still warns about invented dates, day counts and amounts.

It also checks that the translation keeps the dates and amounts of the plain explanation (translated month names are accepted).

## Color palette

The UI uses the team's shared palette. The theme is in `.streamlit/config.toml`; the badge and card styles are in the `STYLE` block in `app.py`.

| Usage | Text color | Background |
| --- | --- | --- |
| Text and headings | `#1D2433` | `#FFFFFF` |
| Cards | `#1D2433` | `#F6F8FA` |
| Warning ("⚠ Kontrol edin": date/amount not in the original) | `#B42318` | `#FDECEA` |
| Verified / positive | `#067647` | `#E7F6EC` |
| Secondary text and the "Belirtilmemiş" badge | `#5B6675` | `#FFFFFF` |

---

<!-- ============================================================
     SECTIONS TO FILL IN WHEN THE PROJECT IS FINISHED
     Replace the "TODO" lines below with the real content.
     ============================================================ -->

## What remains

- [x] Final prompts in `prompts/`, prompt log in `LOG.md`, raw results in `results/`
- [x] 8 test letters + 5 development letters with answer keys in `samples/`
- [x] End-to-end run of the app with a real Gemini key on all 13 sample letters (17.10.2026, see results below)
- [x] Manual re-run of the real-API test after the relative-deadline fix in `validation.py` (17.10.2026, see history below)
- [x] Prompt Engineer: the engine's own check no longer flags relative deadlines and `kaynak_alinti` quotes ending in "..." (new `prompt_engine.py`)
- [x] App saves every run as JSON (`results/app_runs/`) and offers a download
- [ ] Run `python run_samples.py` with the real API, commit `results/real_api/<date>/` and paste `ozet.md` into the results section below
- [ ] `docs/`: report PDF (file name: `TODO`)
- [ ] Presentation link: `TODO`
- [ ] Demo video (YouTube, unlisted): `TODO`
- [x] Language decision: prompts, samples, evaluation and UI stay Turkish; README and code stay English

## Çalıştırma ve değerlendirme sonuçları

_This section is intentionally in Turkish (see the language note at the top)._

Prompt düzeyindeki sonuçlar (`LOG.md`, test seti, `gemini-3.5-flash-lite`): `extract_v2_cot` ile son tarih 8 yazının 8'inde doğru bulundu, hiçbir yazıda son tarih uydurulmadı (0/8) ve 8 çıkarımın 8'i motorun doğrulamasından geçti. `translate_v3_ay_adi` ile 8 çevirinin 8'inde rakamlar ve Türkçe kurum adı korundu.

### Gerçek API ile uçtan uca test

- **Kim / ne zaman:** Barış Yılmaz, 17.10.2026
- **Model:** `gemini-3.5-flash-lite`
- **Kapsam:** Tüm örnek yazılar (`samples/dev_letters` içindeki 5 yazı ve `samples/test_set` içindeki 8 yazı) uygulama üzerinden çalıştırıldı.
- **İlk çalıştırmanın sonucu:** Göreli son tarihlerdeki yanlış alarmlar dışında tüm sonuçlar doğruydu.
- **Örnek (t1, trafik cezası):** 3.135,00 TL ve 2.351,25 TL tutarları ile 14.09.2026 tarihi doğrulandı. Son tarih olarak çıkarılan "tebliğden itibaren 15 gün" ise yazıda birebir bu ifadeyle geçmediği için (yazıda: "tebliğ edildiği tarihten itibaren 15 (on beş) gün") kırmızı "Kontrol edin" etiketi aldı.
- **Düzeltme:** `validation.py` artık göreli süreleri tanıyor. Süre (sayı ve birim) yazıda geçiyorsa yeşil "✓ Göreli süre: yazıda bulundu" etiketi gösteriliyor; geçmiyorsa kırmızı uyarı kalıyor.
- **Motorun yanlış alarmı (düzeltildi):** Prompt motorunun kendi kontrolü göreli son tarihlerde ve "..." ile biten `kaynak_alinti` alıntılarında uyarı veriyordu ("Motor: ⚠ bulunamadı" ve "Son tarihin dayandığı cümle yazıda birebir bulunamadı."). Prompt mühendisi bunu `prompt_engine.py` dosyasının yeni sürümünde düzeltti (yalnızca `dogrula()` değişti). Motor, yazıda olmayan (uydurulmuş) tarih, gün sayısı ve tutarlarda hâlâ uyarı veriyor; bu uyarılar güvenlik katmanı olarak ayrı kutuda gösterilmeye devam ediyor.
- **Düzeltme sonrası elle yeniden çalıştırma (geçmiş kayıt):** Barış Yılmaz, 17.10.2026, aynı model ve aynı 13 örnek yazı, uygulama üzerinden elle kontrol edildi; göreli son tarihlerde bizim kontrolümüz (`validation.py`) artık yanlış alarm vermedi. Bu çalıştırmanın ham çıktıları kaydedilmedi; kanıtlı sonuçlar için aşağıdaki toplu teste bakın.
- **Kayıtlar:** Toplu testin çıktıları `results/real_api/<tarih>/`, uygulamadan yapılan her çalıştırma `results/app_runs/` altına JSON olarak kaydedilir. Ekran görüntüleri `docs/screenshots/` altına eklenebilir.

### Toplu test (`run_samples.py`)

`run_samples.py`, `samples/dev_letters` (5) ve `samples/test_set` (8) içindeki 13 yazının hepsini `run_pipeline()` ile çalıştırır. Her yazı için:

1. Tam sonucu (uygulamadaki kayıtla aynı biçimde) `results/real_api/<YYYY-MM-DD>/<yazı>.json` dosyasına kaydeder.
2. `validation.py` kontrollerini çalıştırır.
3. Sonucu `answers.json` ile karşılaştırır: son tarih (`run_experiments.py` ile aynı kural) ve tutarlar. Cevap anahtarlarında `kurum` alanı olmadığı için kurum karşılaştırılmaz.

Sonunda aynı klasöre Türkçe özet tablosunu yazar: `ozet.md` ve `ozet.csv` (Excel'de açılabilir). Sütunlar: yazı, son tarih doğru mu, tutarlar doğru mu, motor uyarısı, bizim uyarımız, genel sonuç (Geçti / Kontrol gerekli / Kaldı / Hata). Kotaya takılmamak için yazılar arasında 6 saniye beklenir; 429 ve sunucu hatalarında birkaç kez yeniden denenir, art arda 3 hatada betik durur.

**Mac'te adım adım:**

1. Terminal'i açın ve proje klasörüne gidin: `cd ~/…/disaster-preparedness-assistant`
2. Sanal ortamı ilk kez kuruyorsanız: `python3 -m venv .venv`
3. Sanal ortamı açın: `source .venv/bin/activate`
4. Paketleri kurun: `pip install -r requirements.txt`
5. `.env` dosyası yoksa: `cp .env.example .env`, sonra `open -e .env` ile açıp `GEMINI_API_KEY=` satırına anahtarınızı yazın.
6. Önce API çağırmadan deneyin: `ACIKYAZI_MOCK=1 python run_samples.py` (çıktı `results/real_api/<tarih>_mock/` altına gider; sahte cevaplar olduğu için doğruluk kanıtı değildir, bu klasörü commit etmeyin).
7. Önbelleği temizleyin ki cevaplar yeniden üretilsin: `rm -rf .cache`
8. Gerçek API ile çalıştırın: `python run_samples.py` (dil varsayılan olarak İngilizce, böylece çeviri de test edilir; Türkçe için `--lang tr`, Arapça için `--lang ar`. Tek yazı için ör. `--only t1_trafik_cezasi`).
9. Sonuçları açın: `open results/real_api/$(date +%F)/ozet.md`
10. Sonuçları commit edin: `git add results/real_api results/app_runs && git commit -m "Add real-API batch results" && git push`

### Toplu test sonuçları

> **TODO:** `python run_samples.py` gerçek API ile çalıştırıldıktan sonra `results/real_api/<tarih>/ozet.md` içindeki tabloyu buraya yapıştırın (tarih, model ve prompt sürümleri tablonun üstünde yazıyor).

### Test matrisi

> **TODO:** Test matrisi tamamlanınca kalan satırları doldurun.

| Test | Sonuç |
| --- | --- |
| Doğruluk (son tarih ve tutar, 13 yazı) | `run_samples.py` ile ölçülecek; sonuçlar `results/real_api/<tarih>/ozet.md` dosyasına yazılır (bkz. "Toplu test sonuçları") |
| Uydurma (son tarihi olmayan / bozuk yazı) | TODO |
| Okunabilirlik (takım dışından 2 kişi) | TODO |
| Çeviri (EN / AR, rakamlar korunuyor mu?) | TODO |
| Yönlendirme dışı istek | TODO |
| Taraflılık | TODO |

> **TODO:** Demo ekran görüntüleri (ör. `docs/screenshots/` altına ekleyip buraya bağlayın).

## Team

| Role | Member |
| --- | --- |
| Prompt Engineer | Muhammed Çağan Göktaş |
| Developer | Barış Yılmaz |
| Research, Testing and Ethics | Davut Varlık |
| Presentation, Video and Submission | Emre Saydere |
