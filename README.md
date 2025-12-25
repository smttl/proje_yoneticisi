# 🧬 Oosit Kalite Değerlendirme Platformu

Bu proje, araştırmacılar için tasarlanmış yapay zekâ destekli (YOLOv8) bir **oosit kalite değerlendirme platformudur**.  
Sistem, **.czi (Zeiss)** formatındaki mikroskop görüntülerindeki oositleri otomatik olarak tespit eder ve uzmanların bu tespitleri **A-D sınıflandırması + 4 morfolojik kriter** ile puanlamasına olanak tanır.

![Örnek Arayüz](https://github.com/smttl/proje_yoneticisi/blob/ca677e48722f65e4893b8ac20a19a3782ad043ce/img/uzmanp.png)

Sistemin temel amacı, uzmanlardan toplanan yüksek kaliteli veriyi kullanarak **MobileNetV2** gibi modeller için  
**512x512, kare formatlı bir sınıflandırma veri seti oluşturmak** ve yapay zekâ modellerini eğitmektir.

---

## 🚀 Temel Özellikler

Platform iki ana kullanıcı rolünden oluşur:

- **🧑‍🔬 Uzman (Puanlama yapar)**
- **👑 Admin (Yönetim yapar)**

---
![Örnek](https://github.com/smttl/proje_yoneticisi/blob/ca677e48722f65e4893b8ac20a19a3782ad043ce/img/de.png)
## 🧑‍🔬 Uzman Arayüzü (Puanlama & Düzeltme)

### 📁 .czi Dosya Desteği  
Zeiss mikroskop dosyalarını doğrudan yükleme ve işleme.

### 🤖 Otomatik Tespit (YOLOv8)
Yüklenen görüntüdeki oositlerin otomatik tespiti.

### 🔍 Gelişmiş Görüntüleme
- Pan (kaydırma)
- Zoom (yakınlaştırma)
- Canvas tabanlı inceleme

### 📏 Bilimsel Cetvel  
Görüntü metadata’sındaki ölçek bilgisine dayanarak **µm cinsinden doğru ölçüm** yapabilme.

### 📝 İki Aşamalı Puanlama  
1. **Genel Kalite:** A, B, C, D  
2. **Detaylı Morfoloji Puanları (1–5):**
   - Sitoplazma  
   - Zona  
   - Perivitellin Alan  
   - Kumulus (varsa)

### 🛠 İnsan Denetim Araçları
- **Oosit Ekle:** Eksik tespitleri manuel ekleme  
- **Tespit Sil:** Yanlış tespitleri kolayca kaldırma  

---
![admin](https://github.com/smttl/proje_yoneticisi/blob/ca677e48722f65e4893b8ac20a19a3782ad043ce/img/adminp.png)
## 👑 Admin Paneli (Yönetim & Veri Çıktısı)

### 📊 İstatistik Paneli
- Uzmanlara atanmış görüntüler ve ilerleme yüzdeleri  
- Bir görüntünün kaç uzman tarafından puanlandığı (konsensüs analizi)

### 👤 Kullanıcı Yönetimi
- Yeni uzman ekleme  
- Uzman silme  

### 🖼 Görüntü Yönetimi
- Görüntüleri uzmanlara atama  
- Hatalı / eski görüntüleri tüm skorlarıyla birlikte sistemden silme  

![admin d](https://github.com/smttl/proje_yoneticisi/blob/ca677e48722f65e4893b8ac20a19a3782ad043ce/img/adminpdy.png)

### 📥 Detaylı İnceleme & İndirme
- `.czi` metadata görüntüleme (Objektif, kanallar vb.)  
- Orijinal `.czi`, işlenmiş `.png` ve **LabelMe JSON** indirme  
- Tespit edilmiş her oositin kırpılmış halini (cropped) görme  
- Tüm uzman puanlarını karşılaştırmalı tabloda inceleme  

### 📦 Veri Seti Oluşturma (Yapay Zekâ İçin)
- **Excel Raporu (.xlsx):** Tüm uzman puanları  
- **Sınıflandırma Seti (.zip):**
  - 512×512 pad edilmiş oosit görüntüleri  
  - `labels.csv`  
  - MobileNetV2 eğitimi için hazır içerik  

---
## 🏁 Kurulum ve Çalıştırma

Bu proje **Debian Linux** üzerinde test edilmiştir.

### 1. Sistem Gereksinimleri
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv build-essential libgl1-mesa-glx
2. Projeyi Hazırlama
Bash

git clone 
cd 

# Sanal ortam kurulumu
python3 -m venv venv
source venv/bin/activate

# Kütüphanelerin yüklenmesi
pip install -r requirements.txt
Not: Eğitilmiş best.pt modelinizi modelsv8/ klasörüne kopyalamayı unutmayın.

3. Uygulamayı Başlatma
Veritabanını oluşturun (Varsayılan kullanıcılar: admin/admin, uzman1/123456):

Bash

flask init-db
Sunucuyu başlatın:

Bash

flask run --host=0.0.0.0
Tarayıcıdan erişim: http://<sunucu_ip_adresiniz>:5000

