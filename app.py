# app.py
import os
import json
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, flash, abort,
    jsonify, session, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from functools import wraps
import pandas as pd
import io

# Yerel modülleri import et
from models import db, User, Image, Detection, Score, ImageAssignment
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

# === Yolları mutlak (absolute) olarak tanımla ===
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['PREVIEW_FOLDER'] = os.path.join(basedir, 'static/previews')

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
    """Veritabanı tablolarını ve ilk kullanıcıları oluşturur."""
    db.create_all()
    
    # 'uzman1' kullanıcısını oluştur
    if not User.query.filter_by(username='uzman1').first():
        hashed_password = bcrypt.generate_password_hash('123456').decode('utf-8')
        new_user = User(username='uzman1', password=hashed_password, role='uzman') # Rolü 'uzman'
        db.session.add(new_user)
        print("Kullanıcı 'uzman1' oluşturuldu.")

    # 'admin' kullanıcısını oluştur (şifre: admin)
    if not User.query.filter_by(username='admin').first():
        hashed_password = bcrypt.generate_password_hash('admin').decode('utf-8')
        new_user = User(username='admin', password=hashed_password, role='admin') # Rolü 'admin'
        db.session.add(new_user)
        print("Kullanıcı 'admin' oluşturuldu.")
        
    db.session.commit()
    print("Veritabanı başarıyla oluşturuldu/güncellendi.")

# === YENİ: Admin Yetki Kontrolü ===
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Bu sayfaya erişmek için admin yetkisi gereklidir.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
            # YENİ: Admin ise admin paneline, değilse uzman paneline yönlendir
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
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

# === UZMAN DASHBOARD (GÜNCELLENDİ) ===
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        # --- DOSYA YÜKLEME MANTIĞI ---
        if 'file' not in request.files:
            flash('Dosya kısmı yok', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Dosya seçilmedi', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            
            # 1. Orijinal adı al ve güvenli hale getir
            filename = secure_filename(file.filename)
            
            # 2. Dosya adını ve uzantısını ayır
            base_name, file_extension = os.path.splitext(filename)
            
            # 3. Benzersiz bir zaman damgası oluştur
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # 4. YENİ ID: Orijinal ad + zaman damgası
            image_id = f"{base_name}_{timestamp}"
            
            # 5. Sunucuya kaydedilecek tam dosya adı
            czi_filename_on_server = f"{image_id}{file_extension}"
            
            # 6. Dosyayı kaydet
            czi_save_path = os.path.join(app.config['UPLOAD_FOLDER'], czi_filename_on_server)
            file.save(czi_save_path)

            try:
                metadata, preview_path, detections = process_czi_image(
                    czi_save_path,
                    image_id, 
                    app.config['PREVIEW_FOLDER'],
                    app.config['YOLO_MODEL_PATH']
                )

                # GÜNCELLEME: Yükleyen kişiyi (uploader_id) kaydet
                new_image = Image(
                    id=image_id,
                    file_path=czi_save_path,
                    preview_path=preview_path, 
                    metadata_json=metadata,
                    uploader_id=current_user.id # <-- YENİ
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
                flash(f"Görüntü {image_id} başarıyla yüklendi.", 'success')

            except Exception as e:
                db.session.rollback()
                if os.path.exists(czi_save_path):
                    os.remove(czi_save_path)
                try:
                    error_preview_path_rel = f"previews/{image_id}.png"
                    error_preview_path_abs = os.path.join(basedir, 'static', error_preview_path_rel)
                    if os.path.exists(error_preview_path_abs):
                        os.remove(error_preview_path_abs)
                except:
                    pass 
                flash(f"Görüntü işlenemedi: {e}", 'danger')

            return redirect(url_for('dashboard'))

    # === GET İSTEĞİ (Sayfa Yüklendiğinde) ===
    # 1. Bu uzmanın yüklediği resimleri bul
    uploaded_images = Image.query.filter_by(uploader_id=current_user.id).order_by(Image.id.desc()).all()
    
    # 2. Bu uzmana atanan resimleri bul
    assigned_images = Image.query.join(
        ImageAssignment, Image.id == ImageAssignment.image_id
    ).filter(
        ImageAssignment.expert_id == current_user.id
    ).order_by(
        Image.id.desc()
    ).all()
    
    return render_template(
        'dashboard.html', 
        uploaded_images=uploaded_images, 
        assigned_images=assigned_images
    )

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
        image=image, 
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

# =====================================================================
# ===  ADMIN PANELİ ROTALARI (YENİ)
# =====================================================================

@app.route('/admin')
@login_required
@admin_required # Sadece Adminler girebilir
def admin_dashboard():
    # Tüm resimleri ve uzmanları çek
    images = Image.query.order_by(Image.id.desc()).all()
    experts = User.query.filter_by(role='uzman').all()
    
    return render_template(
        'admin_dashboard.html', 
        images=images, 
        experts=experts
    )

@app.route('/admin/assign/<image_id>', methods=['POST'])
@login_required
@admin_required
def admin_assign_image(image_id):
    expert_id = request.form.get('expert_id')
    if not expert_id:
        flash('Uzman seçilmedi.', 'danger')
        return redirect(url_for('admin_dashboard'))

    # Bu atama zaten var mı diye kontrol et
    existing_assignment = ImageAssignment.query.filter_by(
        image_id=image_id, 
        expert_id=expert_id
    ).first()
    
    if existing_assignment:
        flash('Bu görüntü zaten bu uzmana atanmış.', 'info')
    else:
        # Yeni atama oluştur
        new_assignment = ImageAssignment(
            image_id=image_id,
            expert_id=expert_id
        )
        db.session.add(new_assignment)
        db.session.commit()
        flash('Görüntü başarıyla uzmana atandı.', 'success')
        
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/image/<image_id>')
@login_required
@admin_required
def admin_image_detail(image_id):
    image = Image.query.get_or_404(image_id)
    return render_template('admin_image_detail.html', image=image)


@app.route('/admin/download_scores')
@login_required
@admin_required
def admin_download_scores():
    # Veritabanından TÜM puanları çek
    query = db.session.query(
        Image.id.label('Resim_ID'),
        Detection.id.label('Oosit_ID'),
        User.username.label('Uzman_Adı'),
        Score.score_sitoplazma.label('Sitoplazma'),
        Score.score_zona.label('Zona'),
        Score.score_kumulus.label('Kumulus'),
        Score.score_oopla.label('Ooplazma'),
        Score.timestamp.label('Puanlama_Zamanı')
    ).join(
        Detection, Image.id == Detection.parent_image_id
    ).join(
        Score, Detection.id == Score.detection_id
    ).join(
        User, Score.user_id == User.id
    ).order_by(
        Image.id, User.username
    )
    
    df = pd.read_sql(query.statement, db.engine)
    
    # Excel dosyasını hafızada oluştur
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Tum_Puanlar', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'Oosit_Puanlari_Raporu_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')