# AçıkYazı örnek yazı testi — 2026-10-17

- Çalıştırma zamanı: 2026-10-17T22:56:38+03:00
- Model: `gemini-3.5-flash-lite` (deneme/mock modu: cevaplar sahte)
- Prompt sürümleri: `extract`: `extract_v2_cot`, `simplify`: `simplify_v3_goreli_sure`, `translate`: `translate_v3_ay_adi`
- Açıklama dili: `en`
- Yazı sayısı: 13 — Geçti: 3, Kontrol gerekli: 0, Kaldı: 10, Hata: 0

| Yazı | Son tarih doğru mu | Tutarlar doğru mu | Motor uyarısı | Bizim uyarımız | Genel sonuç |
|---|---|---|---|---|---|
| d1_emlak_vergisi | Evet | Evet (1/1) | Yok | Yok | Geçti |
| d2_trafik_cezasi | Hayır | Evet (2/2) | Yok | Yok | Kaldı |
| d3_bilgilendirme | Hayır | Evet (beklenen tutar yok) | Yok | Yok | Kaldı |
| d4_ikamet_randevu | Evet | Evet (beklenen tutar yok) | Yok | Yok | Geçti |
| d5_enjeksiyon | Hayır | Evet (1/1) | Yok | Yok | Kaldı |
| t1_trafik_cezasi | Hayır | Evet (2/2) | Yok | Yok | Kaldı |
| t2_ctv_borcu | Hayır | Evet (1/1) | Yok | Yok | Kaldı |
| t3_goc_eksik_evrak | Hayır | Evet (beklenen tutar yok) | Yok | Yok | Kaldı |
| t4_sgk_odeme_emri | Hayır | Evet (1/1) | Yok | Yok | Kaldı |
| t5_okul_katki_payi | Hayır | Evet (1/1) | Yok | Yok | Kaldı |
| t6_vergi_ihbarnamesi | Hayır | Evet (1/1) | Yok | Yok | Kaldı |
| t7_kira_ihtarnamesi | Hayır | Evet (2/2) | Yok | Yok | Kaldı |
| t8_altyapi_bilgi | Evet | Evet (beklenen tutar yok) | Yok | Yok | Geçti |

**Sütunlar:**
- *Son tarih doğru mu*: modelin bulduğu son tarih `answers.json` ile karşılaştırılır (`run_experiments.py` ile aynı kural; göreli sürelerde tarih hesaplanmışsa yanlış sayılır).
- *Tutarlar doğru mu*: `answers.json` içindeki tutarlardan kaçının bulunduğu.
- *Motor uyarısı*: `prompt_engine.dogrula()` uyarıları (güvenlik katmanı).
- *Bizim uyarımız*: `validation.py` kontrolleri (tarih/tutar yazıda yok, çeviride eksik bilgi).
- *Genel sonuç*: Geçti = doğru ve uyarı yok; Kontrol gerekli = doğru ama en az bir uyarı var; Kaldı = son tarih veya tutar yanlış; Hata = API/işlem hatası.

Her yazının tam sonucu bu klasördeki `<yazı>.json` dosyasındadır.
**Mock modu:** motor son tarih olarak yazıdaki son tarihi döndürür; bu tablo yalnızca betiğin çalıştığını gösterir, doğruluk kanıtı değildir.
Cevap anahtarlarında `kurum` alanı olmadığı için kurum karşılaştırması yapılmadı.
