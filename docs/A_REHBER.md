# A · Prompt Mühendisi Rehberi

Bu pakette senin rolün için gereken her şey hazır. Senin işin artık **çalıştırmak, gözlemek, iyileştirmek ve kaydetmek.**

## Paket içeriği
| Dosya | Ne işe yarar | Kimin |
|---|---|---|
| `prompts/system.txt` | Her çağrıda giden sistem promptu (6 güvenlik kuralı) | A |
| `prompts/extract_v1_zeroshot.txt`, `extract_v2_cot.txt` | Çıkarım: baseline ve chain-of-thought | A |
| `prompts/simplify_v1_zeroshot.txt`, `simplify_v2_fewshot.txt` | Sadeleştirme: baseline ve few-shot | A |
| `prompts/translate_v0_naive.txt`, `translate_v1_rules.txt` | Çeviri: baseline ve kurallı zero-shot | A |
| `prompts/fewshot_examples.json` | 2 uydurma örnek (su borcu, kurs daveti) | A |
| `prompts/schema.json` | **B ile sözleşme**: JSON alanları | A → B |
| `prompt_engine.py` | B'nin import edeceği modül: `run_pipeline(metin, dil)` + doğrulama | A → B |
| `run_experiments.py` | Sürümleri karşılaştırır, metrik hesaplar, LOG.md'ye tablo ekler | A |
| `dev_letters/` | 5 uydurma geliştirme yazısı + cevap anahtarı (tuzaklı) | A |
| `LOG.md` | Prompt günlüğü: rapor bölümünün kaynağı | A → C |
| `docs/rapor_prompt_bolumu.md` | Raporun prompt bölümü taslağı | A → C |
| `docs/video_A_script.md` | Videodaki 1 dakikalık İngilizce bölümün | A → D |

Bu klasör doğrudan repo köküne kopyalanabilir. B kendi `app.py`'sini yanına koyar.

## Kurulum (10 dk)
1. https://aistudio.google.com adresinden API anahtarı al.
2. Klasörde `.env.example` dosyasını `.env` olarak kopyala, anahtarı yaz. **`.env` asla repoya girmez** (`.gitignore` hazır).
3. `pip install -r requirements.txt`
4. Önce API'siz dene: `python run_experiments.py --stage all --mock`. Tablolar çıkıyorsa kurulum tamam. (Mock sonuçları anlamsızdır. LOG.md'ye eklenen MOCK bölümlerini sil.)
5. Gerçek tek deneme: `python prompt_engine.py dev_letters/d1_emlak_vergisi.txt en`
6. AI Studio'da modelin kotasına bak. Ücretsiz kota düşükse `--sleep` değerini artır. Önbellek sayesinde aynı prompt ikinci kez kota yemez.

**Kota hesabı:** `--stage all` dev setinde yaklaşık 5 × (2 + 3 + 4) = 45 çağrı yapar (önbellek tekrarları düşer). Kota darsa aşamaları ayrı ayrı ve `--only d1_emlak_vergisi d2_trafik_cezasi` ile çalıştır.

## Zaman çizelgen
| Saat | İş | Bitiş kriteri |
|---|---|---|
| Cmt 17:00–17:30 | Kurulum + mock + tek gerçek deneme | `d1` için mantıklı bir JSON geliyor |
| Cmt 17:30 | **B'ye gönder:** `prompt_engine.py` + `schema.json` (aşağıdaki mesaj) | B arayüzü sahte modla (`ACIKYAZI_MOCK=1`) geliştirmeye başlayabilir |
| Cmt 17:30–18:30 | `python run_experiments.py --stage extract` → tabloyu oku, LOG'a gözlem yaz | v1 ile v2 farkı not edildi |
| Cmt 18:00 | C'den ilk 4 test yazısını al | — |
| Cmt 19:00–20:30 | `--stage simplify`, `--stage translate --lang en` → gözlemler | Her aşamada kazanan sürüm belli |
| Cmt 20:30–21:00 | En zayıf çıktıyı düzelt (aşağıdaki iyileştirme döngüsü) → yeni sürüm dosyası (`_v3`) | v3 en az bir metrikte daha iyi |
| Cmt 21:00 | **B'ye kesin şema**; `prompt_engine.py`'de `VARSAYILAN` kazanan sürümlere ayarlı | Şema donduruldu |
| Cmt 23:00 | B'nin v1'inde 5 dev yazısını uçtan uca dene | — |
| Paz 10:00–12:00 | C'nin 8 yazılık test setinde: `--letters <C klasörü> --stage all`, Arapça için `--lang ar` | Test sonuçları LOG'da |
| Paz 12:00 | **Son sürüm promptlar** (bundan sonra prompt değişmez) | — |
| Paz 13:00–14:00 | `docs/rapor_prompt_bolumu.md` içindeki `[X]` alanlarını gerçek sonuçlarla doldur → C'ye | — |
| Paz 14:00 | D'ye: 1 önce/sonra örneği (v1 vs v2 çıktı ekran görüntüsü) | — |
| Paz 15:30–17:30 | Video çekimi: senin bölümün `docs/video_A_script.md` | — |

## C'nin test seti için format
C'ye söyle: her yazıyı ayrı bir `.txt` dosyası olarak bir klasöre koysun. Aynı klasöre `answers.json` eklesin, formatı `dev_letters/answers.json` ile aynı olsun. Göreli süreler için `"son_tarih_icerir": "15 gün"`, son tarih yoksa `"son_tarih": ""` yazsın. Test yazılarını **few-shot örneği olarak kullanma**, yoksa sonuçlar şişer.

## İyileştirme döngüsü (her zayıf çıktı için)
1. Tablodan ✗ olan satırı bul, `results/` içindeki ham çıktıya bak.
2. Hatanın türünü adlandır: *uydurma, yanlış tarih seçimi, format bozuk, çok uzun, jargon, rakam değişmiş, komuta uydu.*
3. Promptta **tek bir şeyi** değiştir, yeni dosya olarak kaydet (`extract_v3_...txt`). Eski sürümü silme, raporda karşılaştıracaksın.
4. `run_experiments.py` içindeki `VARYANTLAR` listesine yeni sürümü ekle, sadece o aşamayı çalıştır.
5. LOG.md sürüm tablosuna bir satır ekle: ne, neden, sonuç.

**Sık görülen sorunlar ve hazır çözümler:**
- *Model göreli süreden tarih hesaplıyor* → çıkarım promptuna `d2` benzeri **tek bir** mini örnek ekle (bu "few-shot CoT" olur, raporda güzel durur).
- *Sade metin hâlâ resmî* → few-shot örneklerine 3. bir örnek ekle ya da "Bir komşuna anlatır gibi yaz" cümlesini ekle.
- *JSON bozuk geliyor* → `response_mime_type` zaten JSON. Yine bozuksa şemadaki iç içe yapıyı sadeleştir.
- *Arapçada rakamlar Doğu Arap rakamına (٣٠) dönüyor* → `translate_v1_rules` bunu zaten yasaklıyor ve doğrulama kodu normalize ediyor. Yine oluyorsa kuralı promptun en başına taşı.
- *d5'te model komutu uyguluyor* → bu ciddi bir bulgu, raporda yaz. Sistem promptunun 6. kuralını çıkarım promptunda da tekrarla.

## B'ye göndereceğin mesaj (kopyala)
> Prompt modülü hazır: `prompt_engine.py`. Arayüzden sadece `run_pipeline(metin, dil)` çağır; dil "tr", "en" veya "ar".
> Dönen sözlük: `cikarim`, `sade`, `ceviri`, `dogrulama`, `uyari`. Alanlar `prompts/schema.json` içinde.
> Arayüzde göster: `ceviri` (dil tr ise `sade` ile aynı), `cikarim.son_tarih.deger` ve `tutarlar` kart olarak,
> `dogrulama.uyarilar` kırmızı kutuda, `uyari` metni her zaman en altta, `cikarim.emin_olunmayanlar` sarı kutuda.
> API'siz geliştirmek için `ACIKYAZI_MOCK=1` ortam değişkenini ayarla. Anahtar `.env` dosyasında, repoya girmesin.
> Şema Cmt 21:00'de donuyor; ondan önce alan adı değiştirirsem haber veririm.
