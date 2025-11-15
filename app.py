# app.py (İsimlendirme Düzeltmesi Yapılmış)
import os
import json
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, flash, abort,
    jsonify, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

# Yerel modülleri import et
from models import db, User, Image, Detection, Score
from processing import process_czi_image

# --- UYGULAMA KONFİGÜRASYONU ---
app = Flask(__name__)

# Proje ana dizinini (app.py'nin olduğu yer) bul
basedir = os.path.abspath(os.path.dirname(__file__))

# Instance klasörünün tam (mutlak) yolunu oluştur
instance_dir = os.path.join(basedir, 'instance')
# Veritabanı dosyasının tam (mutlak) yolunu oluştur
db_path = os.path.join(instance_dir, 'proje.db')

app.config['SECRET_KEY'] = 'COK_GIZLI_BIR_ANAHTAR_12345'
# Veritabanı yolu (Mutlak)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

# === DÜZELTME: Yolları mutlak (absolute) olarak tanımla ===
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['PREVIEW_FOLDER'] = os.path.join(basedir, 'static/previews')
# ==========================================================

app.config['ALLOWED_EXTENSIONS'] = {'czi'}
# Kendi YOLOv8 modelinizin yolunu buraya girin (Göreli yol)
app.config['YOLO_MODEL_PATH'] = 'modelsv8/best.pt'

# Gerekli klasörleri oluştur (Artık mutlak yolu kullanıyor)
os.makedirs(instance_dir, exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PREVIEW_FOLDER'], exist_ok=True)

# --- EKLENTİLERİ BAŞLATMA ---
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Lütfen bu sayfaya erişmek için giriş yapın.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- VERİTABANINI OLUŞTURMAK İÇİN ÖZEL KOMUT ---
@app.cli.command("init-db")
def init_db_command():
    """Veritabanı tablolarını ve ilk kullanıcıyı oluşturur."""
    db.create_all()

    if not User.query.filter_by(username='uzman1').first():
        hashed_password = bcrypt.generate_password_hash('123456').decode('utf-8')
        new_user = User(username='uzman1', password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        print("Veritabanı ve 'uzman1' kullanıcısı başarıyla oluşturuldu.")
    else:
        print("Veritabanı zaten mevcut.")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- KULLANICI GİRİŞ/ÇIKIŞ SAYFALARI ---
# Hem ana sayfa hem de /login yolu için GET ve POST metodlarını kabul et
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        else:
            flash('Giriş başarısız. Bilgileri kontrol edin.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ANA UYGULAMA SAYFALARI ---
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Dosya kısmı yok', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Dosya seçilmedi', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            
            # === İSİMLENDİRME GÜNCELLEMESİ ===
            # 1. Orijinal adı al ve güvenli hale getir
            filename = secure_filename(file.filename)
            
            # 2. Dosya adını ve uzantısını ayır
            base_name, file_extension = os.path.splitext(filename)
            
            # 3. Benzersiz bir zaman damgası oluştur
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # 4. YENİ ID: Orijinal ad + zaman damgası (örn: "Deneme_1_20251115203000")
            image_id = f"{base_name}_{timestamp}"
            
            # 5. Sunucuya kaydedilecek tam dosya adı (örn: "Deneme_1_20251115203000.czi")
            czi_filename_on_server = f"{image_id}{file_extension}"
            
            # 6. Dosyayı kaydet
            czi_save_path = os.path.join(app.config['UPLOAD_FOLDER'], czi_filename_on_server)
            file.save(czi_save_path)
            # === İSİMLENDİRME SONU ===

            try:
                # process_czi_image fonksiyonuna mutlak yolları gönderiyoruz
                metadata, preview_path, detections = process_czi_image(
                    czi_save_path,
                    image_id, # (Artık yeni formatta, örn: "Deneme_1_20251115203000")
                    app.config['PREVIEW_FOLDER'], # Mutlak yol
                    app.config['YOLO_MODEL_PATH']
                )

                # preview_path'ın "previews/YENI_ID.png" formatında 
                # (göreceli ve / ile) geldiğini varsayıyoruz (processing.py düzeltmesi)
                
                new_image = Image(
                    id=image_id,
                    file_path=czi_save_path,
                    preview_path=preview_path, # DB'ye "previews/Deneme_1_....png" olarak kaydedilir
                    metadata_json=metadata
                )
                db.session.add(new_image)

                for det_data in detections:
                    new_detection = Detection(
                        id=det_data['id'],
                        parent_image_id=image_id,
                        coordinates_labelme=det_data['coordinates_labelme']
                    )
                    db.session.add(new_detection)

                db.session.commit()
                flash(f"Görüntü {image_id} başarıyla yüklendi ve {len(detections)} oosit bulundu.", 'success')

            except Exception as e:
                db.session.rollback()
                # Hata durumunda CZI dosyasını sil
                if os.path.exists(czi_save_path):
                    os.remove(czi_save_path)

                # Önizleme PNG'si oluşturulduysa onu da sil
                try:
                    # 'processing.py'nin 'previews/image_id.png' döndürdüğünü varsayarak
                    # 'static/' ile birleştirip mutlak yolunu buluyoruz
                    error_preview_path_rel = f"previews/{image_id}.png"
                    error_preview_path_abs = os.path.join(basedir, 'static', error_preview_path_rel)
                    if os.path.exists(error_preview_path_abs):
                        os.remove(error_preview_path_abs)
                except:
                    pass # Silme işlemi de hata verirse görmezden gel

                flash(f"Görüntü işlenemedi: {e}", 'danger')

            return redirect(url_for('dashboard'))

    # GET isteği (sayfa yüklendiğinde)
    images = Image.query.order_by(Image.id.desc()).all()
    return render_template('dashboard.html', images=images)

@app.route('/annotate/<image_id>')
@login_required
def annotate_image(image_id):
    image = Image.query.get_or_404(image_id)

    detections_query = db.session.query(
        Detection, Score
    ).outerjoin(
        Score,
        (Score.detection_id == Detection.id) & (Score.user_id == current_user.id)
    ).filter(
        Detection.parent_image_id == image_id
    ).all()

    detections_data = []
    for det, score in detections_query:
        detections_data.append({
            "id": det.id,
            "coordinates_labelme": det.coordinates_labelme,
            "scores": {
                "sitoplazma": score.score_sitoplazma if score else None,
                "zona": score.score_zona if score else None,
                "kumulus": score.score_kumulus if score else None,
                "oopla": score.score_oopla if score else None
            }
        })

    return render_template(
        'annotate.html',
        image=image, # image.preview_path = "previews/Deneme_1_....png"
        detections_json=json.dumps(detections_data),
        metadata_json=json.dumps(image.metadata_json)
    )

@app.route('/api/save_score', methods=['POST'])
@login_required
def save_score():
    data = request.json
    detection_id = data.get('detection_id')
    scores = data.get('scores')

    if not detection_id or not scores:
        return jsonify({'success': False, 'error': 'Eksik veri'}), 400

    score_obj = Score.query.filter_by(
        detection_id=detection_id,
        user_id=current_user.id
    ).first()

    if not score_obj:
        score_obj = Score(detection_id=detection_id, user_id=current_user.id)
        db.session.add(score_obj)

    score_obj.score_sitoplazma = scores.get('sitoplazma')
    score_obj.score_zona = scores.get('zona')
    score_obj.score_kumulus = scores.get('kumulus')
    score_obj.score_oopla = scores.get('oopla')
    score_obj.timestamp = datetime.utcnow()

    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Debian'da dışarıdan erişim için 'host=0.0.0.0' eklemeyi unutmayın
    # 'flask run' kullanıyorsanız: flask run --host=0.0.0.0
    app.run(debug=True, host='0.0.0.0')