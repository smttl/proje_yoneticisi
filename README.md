Oosit Kalite Değerlendirme Platformu
Bu proje, embriyologlar ve araştırmacılar için tasarlanmış, yapay zekâ destekli (YOLOv8) bir web uygulamasıdır. Bu araç, .czi (Zeiss) formatındaki mikroskop görüntülerindeki oositleri otomatik olarak tespit eder ve uzmanların "İnsan destekli bir arayüzle bu tespitleri puanlamasına (A-D sınıflandırması ve detaylı morfolojik puanlama) olanak tanır.

Sistemin asıl amacı, uzmanların bu arayüzle oluşturduğu yüksek kaliteli veriyi toplayarak, MobileNetV2 gibi sınıflandırma modellerini eğitmek için 512x512 boyutunda, kareye oturtulmuş bir eğitim veri seti oluşturmaktır.

🚀 Temel Özellikler
Platform, iki ana kullanıcı rolü üzerine kuruludur: Uzman (Puanlama yapar) ve Admin (Yönetim yapar).

🧑‍🔬 Uzman Arayüzü (Puanlama & Düzeltme)
.czi Dosya Desteği: Zeiss mikroskop dosyalarını doğrudan yükleme ve işleme.

Otomatik Tespit: YOLOv8 modeli ile yüklenen görüntüdeki oositlerin otomatik olarak bulunması.

Gelişmiş Görüntüleme: Görüntü üzerinde kaydırma (pan) ve yakınlaştırma (zoom) araçları.

Bilimsel Cetvel: Görüntüye gömülü metadata'yı (ölçek) okuyarak, yakınlaştırmadan bağımsız olarak mikrometre (µm) cinsinden hassas ölçüm yapabilme.

İki Aşamalı Puanlama:

Genel Kalite: Oosit için A, B, C, D olarak ana sınıflandırma.

Detaylı Puanlama: 4 morfolojik kriter (Sitoplazma, Zona vb.) için 1-5 arası hızlı puanlama butonları.

İnsan Denetim Araçları:

Oosit Ekle: Modelin kaçırdığı oositleri manuel olarak kutu içine alıp puanlama listesine ekleme.

Tespit Sil: Modelin hatalı bulduğu (örn. bir çöp veya artefakt) tespitleri tek tıkla silme.

👑 Admin Paneli (Yönetim & Veri Çıktısı)
İstatistik Paneli:

Hangi uzmana kaç resim atandığını ve ilerleme durumlarını (% tamamlanma) görme.

Hangi görüntünün kaç farklı uzman tarafından puanlandığını (konsensüs) görme.

Kullanıcı Yönetimi:

Sisteme yeni uzman kullanıcılar ekleme.

Mevcut uzmanları sistemden silme.

Görüntü Yönetimi:

Görüntüleri belirli uzmanlara atama.

Hatalı/eski görüntüleri tüm verileriyle (puanlar, tespitler) birlikte sistemden kalıcı olarak silme.

Detaylı İnceleme & İndirme:

Her görüntünün detaylı metadata'sını (Objektif, Çekim Tarihi, Kanal İsimleri) görme.

Orijinal .czi dosyasını, işlenmiş .png dosyasını ve tüm tespitleri içeren ana LabelMe .json dosyasını indirme.

Tespit edilen her oositi kırpılmış (cropped) olarak görme ve tüm uzmanların verdiği puanları karşılaştırmalı bir tabloda inceleme.

Veri Seti Oluşturma (Yapay Zekâ İçin):

Excel Raporu: Tüm uzmanların tüm puanlarını içeren detaylı bir Excel (.xlsx) raporu indirme.

Sınıflandırma Veri Seti (.zip): Puanlanmış tüm oositleri 512x512 (siyah arka plana ortalanmış, en-boy oranı korunmuş) .png görüntüleri ve bu görüntülere ait puanları içeren bir labels.csv dosyası olarak indirme. (MobileNetV2 eğitimi için hazır)

🛠️ Kullanılan Teknolojiler
Backend: Flask, SQLAlchemy (Flask-SQLAlchemy)

Frontend: HTML5, CSS3, Vanilla JavaScript (Fetch API, Canvas API)

Kimlik Doğrulama: Flask-Login, Flask-Bcrypt

Görüntü İşleme: aicsimageio (CZI okuma), Pillow (PIL) (Kırpma, Padding), NumPy

Yapay Zekâ (Tespit): ultralytics (YOLOv8)

Veri Aktarımı & Raporlama: pandas, openpyxl, zipfile

🏁 Kurulum ve Çalıştırma
Bu proje bir Linux (Debian) sunucusu üzerinde geliştirilmiş ve test edilmiştir.

1. Sistem Gereksinimleri (Debian)
Önce gerekli sistem kütüphanelerini kurun:

Bash

sudo apt update
sudo apt install -y python3 python3-pip python3-venv build-essential libgl1-mesa-glx
2. Proje Kurulumu
Projeyi klonlayın:

Bash

git clone https://github.com/kullanici-adiniz/proje-adiniz.git
cd proje-adiniz
Python sanal ortamını (virtual environment) oluşturun ve aktifleştirin:

Bash

python3 -m venv venv
source venv/bin/activate
Gerekli tüm Python kütüphanelerini kurun:

Bash

pip install -r requirements.txt
Eğitilmiş YOLOv8 modelinizi (best.pt) modelsv8/ klasörüne kopyalayın.

3. Çalıştırma
Veritabanını Başlatın: (Bu komut instance/proje.db dosyasını oluşturur ve 'admin' (şifre: admin) ile 'uzman1' (şifre: 123456) kullanıcılarını yaratır.)

Bash

flask init-db
Sunucuyu Başlatın: (Dışarıdan erişim için --host=0.0.0.0 gereklidir.)

Bash

flask run --host=0.0.0.0
Tarayıcınızdan http://<sunucu_ip_adresiniz>:5000 adresine gidin.

🧠 Yapay Zekâ Eğitim Akışı
Bu platform iki aşamalı bir yapay zekâ model eğitimini destekler:

1. Aşama: Tespit Modelini İyileştirme (YOLOv8)
Veri Toplama: Uzmanlar, görüntüleri puanlarken "Oosit Ekle" ve "Tespit Sil" araçlarını kullanarak YOLOv8'in hatalarını (kaçırılan veya yanlış tespit edilen) düzeltir.

Veri İndirme: Admin, admin_image_detail sayfasından düzeltilmiş LabelMe .json dosyalarını indirir.

Yeniden Eğitim: Bu yeni ve temiz veriler, YOLOv8 modelini yeniden eğitmek (retrain) için kullanılır.

2. Aşama: Sınıflandırma Modelini Eğitme (MobileNetV2)
Veri Toplama: Uzmanlar, sistemdeki oositlere A-D arası genel puanlar ve 1-5 arası morfolojik puanlar verir.

Veri İndirme: Admin, admin_dashboard üzerinden "Sınıflandırma Veri Setini İndir (.zip)" butonuna tıklar.

Yeniden Eğitim: Sistem, her puanlanmış oositi 512x512 boyutuna getirir ve bir labels.csv dosyasıyla eşleştirir. Bu veri seti, oosit kalitesini (A-D) veya alt puanları (1-5) tahmin edecek bir MobileNetV2 (veya benzeri) modelini eğitmek için kullanılır.