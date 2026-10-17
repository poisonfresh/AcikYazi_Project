# AçıkYazı

AçıkYazı, resmî yazıları (tebligat, ödeme bildirimi, kurum yazısı) anlamakta zorlanan kişilere, yazının ne dediğini, ne yapmaları gerektiğini ve son tarihi sade Türkçeyle ve istenirse İngilizce/Arapça olarak anlatan, rakam ve tarihleri kendi kendine kontrol eden bir asistandır.

SDG'ler için Üretken Yapay Zekâ Hackathonu · Grup 11 · SDG 10.2 ve SDG 16.10

> **Uyarı:** Bu bir hukuki tavsiye değildir; emin olmadığınızda kuruma veya baro adli yardım bürosuna başvurun.

## Nasıl çalışır?

1. **Girdi:** Kullanıcı yazının metnini yapıştırır ve dil seçer (Türkçe / English / العربية).
2. **Çıkarım:** Model yazıdan kurum, konu, istenen işlem, son tarih, tutar, gerekli belgeler ve itiraz yolunu JSON olarak çıkarır (`prompts/cikarim.txt`).
3. **Doğrulama:** Çıkan son tarih ve tutar, Python regex kontrolüyle asıl metinde aranır. Bulunamayan değer kırmızı **"Kontrol edin"** etiketi alır. Bu adım modelden bağımsızdır (`validation.py`).
4. **Sadeleştirme:** JSON'dan üç bölümlü sade açıklama üretilir (`prompts/sadelestirme.txt`).
5. **Çeviri:** Sade metin seçilen dile çevrilir; çeviride tarih/tutar kaybolursa yine uyarı gösterilir (`prompts/ceviri.txt`).
6. **Çıktı:** Kart görünümü + sabit hukuki uyarı. Arapça çeviri "deneysel" etiketiyle gösterilir.

## Klasör yapısı

```
.
├── app.py             # Streamlit arayüzü, Gemini API bağlantısı, JSON ayrıştırma, hata yakalama
├── validation.py      # Doğrulama katmanı: tarih/tutar regex kontrolü
├── prompts/           # Promptlar (Prompt Mühendisi rolü ekler)
├── samples/           # Uydurma, anonim örnek resmî yazılar (Araştırma/Test rolü ekler)
├── docs/              # Rapor PDF'i ve diğer belgeler
├── requirements.txt
├── .env.example       # Örnek ortam değişkenleri (gerçek anahtar içermez)
└── .gitignore         # .env dosyasını repo dışında tutar
```

### Prompt dosyaları

Uygulama promptları `prompts/` klasöründen şu adlarla okur. Dosya yoksa ilgili adım atlanır ve arayüzde uyarı gösterilir; uygulama çökmez.

| Dosya | Adım | Kullanılan yer tutucular |
| --- | --- | --- |
| `prompts/cikarim.txt` | Çıkarım (CoT + JSON) | `{metin}` |
| `prompts/sadelestirme.txt` | Sadeleştirme (few-shot) | `{json}` |
| `prompts/ceviri.txt` | Çeviri (zero-shot) | `{dil}`, `{sade_metin}` |

Çıkarım çıktısı `<dusunce>…</dusunce>` bölümünden sonra şu alanları içeren bir JSON olmalıdır:

```json
{"kurum":"","konu":"","istenen_islem":"","son_tarih":"","tutar":"",
 "gerekli_belgeler":[],"itiraz_yolu":"","emin_olunmayanlar":[]}
```

JSON, ` ```json ` çiti içinde de gelse uygulama onu bulur. Geçerli JSON yoksa kullanıcıya hata ve modelin ham çıktısı gösterilir.

## Kurulum

Python 3.10 veya üzeri gerekir.

```bash
git clone <repo-adresi>
cd <repo-klasoru>

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## API anahtarı ayarı

Uygulama Google AI Studio üzerinden **Gemini** modelini kullanır (ücretsiz katman yeterlidir).

1. [Google AI Studio](https://aistudio.google.com/apikey) üzerinden bir API anahtarı alın.
2. Örnek dosyayı kopyalayın:

   ```bash
   cp .env.example .env
   ```

3. `.env` dosyasını açıp anahtarınızı yazın:

   ```
   GEMINI_API_KEY=anahtariniz
   # İsteğe bağlı, varsayılan: gemini-2.5-flash
   # GEMINI_MODEL=gemini-2.5-flash
   ```

**Anahtar asla repoya girmez.** `.env` dosyası `.gitignore` içinde listelidir; repoda yalnızca anahtarsız `.env.example` bulunur. Commit atmadan önce `git status` çıktısında `.env` görünmediğinden emin olun.

Anahtar eksik veya geçersizse, kota dolduysa ya da internet bağlantısı yoksa uygulama çökmez; arayüzde ne yapmanız gerektiğini söyleyen bir hata mesajı gösterir. Kenar çubuğunda anahtarın ve prompt dosyalarının durumu görünür.

## Örnek çalıştırma

```bash
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` açılır. Ardından:

1. Metin kutusuna örnek bir yazı yapıştırın, örneğin:

   ```
   T.C. X BELEDİYESİ
   Sayın mükellef, 2026 yılı çevre temizlik vergisi borcunuz 1.250,50 TL'dir.
   Borcun en geç 30.11.2026 tarihine kadar ödenmesi gerekmektedir.
   ```

2. Açıklama dilini seçin ve **Yazıyı açıkla** düğmesine basın.
3. "Yazıdan çıkarılan bilgiler" kartında son tarih ve tutarın yanında **✓ Doğrulandı** veya **⚠ Kontrol edin** etiketi görünür.

**Kişisel veri:** Uygulama hiçbir metni saklamaz. Yapıştırmadan önce TC kimlik no, adres, plaka gibi kişisel bilgileri silmenizi öneririz.

## Doğrulama katmanı

`validation.py` modelden bağımsız çalışır ve şu biçimleri tanır:

- **Tarih:** `30.11.2026`, `30/11/2026`, `30-11-26`, `2026-11-30`, `30 Kasım 2026`
- **Tutar:** `1.250,50 TL`, `₺1.250,50`, `350 TL`, `1250 TRY`, `Türk Lirası`, `EUR`, `USD`

Model hangi biçimde yazarsa yazsın değer normalize edilip asıl metindeki tarih/tutarlarla karşılaştırılır. Bulunamazsa kullanıcıya kırmızı uyarı gösterilir.

---

<!-- ============================================================
     PROJE BİTİNCE DOLDURULACAK BÖLÜMLER
     Aşağıdaki "TODO" satırlarını gerçek içerikle değiştirin.
     ============================================================ -->

## Proje dosyaları (proje bitince doldurulacak)

> **TODO:** Son sürüm dosyalar repoya eklenince bu listeyi güncelleyin.

- [ ] `prompts/cikarim.txt`, `prompts/sadelestirme.txt`, `prompts/ceviri.txt`: son sürüm promptlar
- [ ] `prompts/LOG.md`: prompt sürüm denemeleri ve notlar
- [ ] `samples/`: 8 örnek yazı ve cevap anahtarı
- [ ] `docs/`: rapor PDF'i (dosya adı: `TODO`)
- [ ] Sunum linki: `TODO`
- [ ] Demo videosu (YouTube, liste dışı): `TODO`

## Çalıştırma ve demo sonuçları (proje bitince doldurulacak)

> **TODO:** Test matrisi tamamlanınca sonuçları buraya yazın.

| Test | Sonuç |
| --- | --- |
| Doğruluk (son tarih ve tutar, 8 yazı) | TODO / 8 |
| Uydurma (son tarihi olmayan / bozuk yazı) | TODO |
| Okunabilirlik (takım dışından 2 kişi) | TODO |
| Çeviri (EN / AR, rakamlar korunuyor mu) | TODO |
| Yönlendirme dışı istek | TODO |
| Taraflılık | TODO |

> **TODO:** Demo ekran görüntüleri (ör. `docs/` altına ekleyip buraya bağlayın).

## Takım

| Rol | Üye |
| --- | --- |
| Prompt Mühendisi | TODO |
| Geliştirici | Barış |
| Araştırma, Test ve Etik | TODO |
| Sunum, Video ve Teslim | TODO |
