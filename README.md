📦 Stok ve Reçete Yönetim Sistemi (Inventory & Recipe Manager)
Bu proje, Python ve Tkinter kullanılarak geliştirilmiş, küçük ve orta ölçekli üretim yapan işletmeler veya hobiler için tasarlanmış bir Masaüstü Stok ve Üretim Takip Uygulamasıdır.

Uygulama, ham madde stoklarını takip etmenize, ürün reçeteleri (formüller) oluşturmanıza ve sipariş geldiğinde kullanılan malzemeleri otomatik olarak stoktan düşmenize olanak tanır.

🚀 Özellikler
📊 Gelişmiş Stok Yönetimi:

Malzeme ekleme, güncelleme ve silme.

Kritik Eşik Uyarı Sistemi: Stoğu azalan ürünler için görsel uyarılar (Kırmızı/Sarı renk kodları).

Anlık stok durumu görüntüleme.

📑 Reçete (Ürün) Yönetimi:

Nihai ürünler için reçete oluşturma.

Bir ürüne birden fazla ham maddeyi belirli miktarlarda bağlama.

Dinamik reçete düzenleme (Bileşen ekleme/çıkarma).

⚙️ Otomatik Üretim ve Stok Düşümü:

Sipariş girildiğinde reçeteye göre gerekli malzemeleri hesaplar.

Stok yetersizse üretim öncesi uyarı verir ve eksik malzemeleri listeler.

Onay durumunda tüm bileşenleri stoktan otomatik düşer.

📜 İşlem Geçmişi (Loglama):

Yapılan tüm ekleme, silme ve üretim işlemlerini tarih ve saat bilgisiyle kaydeder.

Geçmiş kayıtlarını inceleme ve temizleme imkanı.

📂 Veri Dışa Aktarım:

Mevcut stok durumunu tek tıkla Excel (CSV) formatında dışa aktarma.

🎨 Modern Arayüz:

ttk ve özel stiller kullanılarak tasarlanmış, kullanıcı dostu, sekmeli ve renkli arayüz.

Kolay gezinim için sol kenar çubuğu (sidebar).

🛠️ Kurulum ve Çalıştırma
Bu proje Python'un standart kütüphanelerini kullanır, bu nedenle harici bir kütüphane yüklemenize (pip install vb.) gerek yoktur.

Projeyi Bilgisayarınıza İndirin:

Bash

git clone https://github.com/kullaniciadi/proje-adi.git
cd proje-adi
Uygulamayı Başlatın:

Bash

python main.py
(Not: Kodunuzun olduğu dosya adını main.py olarak varsayılmıştır, farklıysa değiştirin.)

💻 Ekran Görüntüleri
(Buraya uygulamanızdan aldığınız ekran görüntülerini ekleyebilirsiniz. Örneğin ana ekran, reçete ekranı vb.)

Not: Uygulama ilk açıldığında veritabanı dosyası (malzeme_takip_v2.db) otomatik olarak oluşturulur.

🗂️ Proje Yapısı
main.py: Uygulamanın ana kaynak kodu (Arayüz ve Backend).

malzeme_takip_v2.db: Uygulama çalıştığında oluşan SQLite veritabanı dosyası.

README.md: Proje dokümantasyonu.

🔧 Kullanılan Teknolojiler
Dil: Python 3

Arayüz (GUI): Tkinter & ttk

Veritabanı: SQLite3

Veri İşleme: CSV, ContextLib

🤝 Katkıda Bulunma
Bu projeyi Fork'layın.

Yeni bir özellik dalı (feature branch) oluşturun (git checkout -b yeni-ozellik).

Değişikliklerinizi yapın ve Commit'leyin (git commit -m 'Yeni özellik eklendi').

Dalınızı (Branch) Push'layın (git push origin yeni-ozellik).

Bir Pull Request oluşturun.

📝 Lisans
Bu proje MIT lisansı ile lisanslanmıştır.
