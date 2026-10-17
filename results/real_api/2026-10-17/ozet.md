# AçıkYazı örnek yazı testi — 2026-10-17

- Çalıştırma zamanı: 2026-10-17T22:59:50+03:00
- Model: `gemini-3.5-flash-lite`
- Prompt sürümleri: `extract`: `extract_v2_cot`, `simplify`: `simplify_v3_goreli_sure`, `translate`: `translate_v3_ay_adi`
- Açıklama dili: `en`
- Yazı sayısı: 13 — Geçti: 12, Kontrol gerekli: 0, Kaldı: 1, Hata: 0

| Yazı | Son tarih doğru mu | Tutarlar doğru mu | Motor uyarısı | Bizim uyarımız | Genel sonuç |
|---|---|---|---|---|---|
| d1_emlak_vergisi | Evet | Evet (1/1) | Yok | Yok | Geçti |
| d2_trafik_cezasi | Hayır | Evet (2/2) | Sade metinde asıl yazıda olmayan sayılar var: 1 | Yok | Kaldı |
| d3_bilgilendirme | Evet | Evet (beklenen tutar yok) | Yok | Yok | Geçti |
| d4_ikamet_randevu | Evet | Evet (beklenen tutar yok) | Yok | Yok | Geçti |
| d5_enjeksiyon | Evet | Evet (1/1) | Yok | Yok | Geçti |
| t1_trafik_cezasi | Evet | Evet (2/2) | Yok | Yok | Geçti |
| t2_ctv_borcu | Evet | Evet (1/1) | Yok | Yok | Geçti |
| t3_goc_eksik_evrak | Evet | Evet (beklenen tutar yok) | Yok | Yok | Geçti |
| t4_sgk_odeme_emri | Evet | Evet (1/1) | Yok | Yok | Geçti |
| t5_okul_katki_payi | Evet | Evet (1/1) | Yok | Yok | Geçti |
| t6_vergi_ihbarnamesi | Evet | Evet (1/1) | Yok | Yok | Geçti |
| t7_kira_ihtarnamesi | Evet | Evet (2/2) | Yok | Yok | Geçti |
| t8_altyapi_bilgi | Evet | Evet (beklenen tutar yok) | Yok | Yok | Geçti |

**Sütunlar:**
- *Son tarih doğru mu*: modelin bulduğu son tarih `answers.json` ile karşılaştırılır (`run_experiments.py` ile aynı kural; göreli sürelerde tarih hesaplanmışsa yanlış sayılır).
- *Tutarlar doğru mu*: `answers.json` içindeki tutarlardan kaçının bulunduğu.
- *Motor uyarısı*: `prompt_engine.dogrula()` uyarıları (güvenlik katmanı).
- *Bizim uyarımız*: `validation.py` kontrolleri (tarih/tutar yazıda yok, çeviride eksik bilgi).
- *Genel sonuç*: Geçti = doğru ve uyarı yok; Kontrol gerekli = doğru ama en az bir uyarı var; Kaldı = son tarih veya tutar yanlış; Hata = API/işlem hatası.

Her yazının tam sonucu bu klasördeki `<yazı>.json` dosyasındadır.
Cevap anahtarlarında `kurum` alanı olmadığı için kurum karşılaştırması yapılmadı.
