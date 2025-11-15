# app.py
import os
import json
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, flash, abort,
    jsonify, session, send_file, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from functools import wraps
import pandas as pd
import io
from PIL import Image as PILImage

# Yerel modülleri import et
from models import db, User, Image, Detection, Score, ImageAssignment
from processing import process_czi_image

# --- UYGULAMA KONFİGÜRASYONU ---
app = Flask(__name__)
# ... (app.config kodlarınızın tamamı aynı kalıyor) ...
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
db_path = os.path.join(instance_dir, 'proje.db')
app.config['SECRET_KEY'] = 'COK_GIZLI_BIR_ANAHTAR_12345'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}' 
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['PREVIEW_FOLDER'] = os.path.join(basedir, 'static/previews')
app.config['ALLOWED_EXTENSIONS'] = {'czi'}
app.config['YOLO_MODEL_PATH'] = 'modelsv8/best.pt' 
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
    # ... (init-db kodunuz aynı kalıyor) ...
    db.create_all()
    if not User.query.filter_by(username='uzman1').first():
        hashed_password = bcrypt.generate_password_hash('123456').decode('utf-8')
        new_user = User(username='uzman1', password=hashed_password, role='uzman')
        db.session.add(new_user)
        print("Kullanıcı 'uzman1' oluşturuldu.")
    if not User.query.filter_by(username='admin').first():
        hashed_password = bcrypt.generate_password_hash('admin').decode('utf-8')
        new_user = User(username='admin', password=hashed_password, role='admin')
        db.session.add(new_user)
        print("Kullanıcı 'admin' oluşturuldu.")
    db.session.commit()
    print("Veritabanı başarıyla oluşturuldu/güncellendi.")

# === Admin Yetki Kontrolü ===
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
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... (login kodunuz aynı kalıyor) ...
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=True)
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

# --- UZMAN SAYFALARI ---
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # ... (dashboard kodunuz aynı kalıyor) ...
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Dosya kısmı yok', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Dosya seçilmedi', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            base_name, file_extension = os.path.splitext(filename)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            image_id = f"{base_name}_{timestamp}"
            czi_filename_on_server = f"{image_id}{file_extension}"
            czi_save_path = os.path.join(app.config['UPLOAD_FOLDER'], czi_filename_on_server)
            file.save(czi_save_path)
            try:
                metadata, preview_path, detections = process_czi_image(
                    czi_save_path, image_id,
                    app.config['PREVIEW_FOLDER'],
                    app.config['YOLO_MODEL_PATH']
                )
                new_image = Image(
                    id=image_id, file_path=czi_save_path,
                    preview_path=preview_path, 
                    metadata_json=metadata,
                    uploader_id=current_user.id 
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
                if os.path.exists(czi_save_path): os.remove(czi_save_path) 
                try:
                    error_preview_path_rel = f"previews/{image_id}.png"
                    error_preview_path_abs = os.path.join(basedir, 'static', error_preview_path_rel)
                    if os.path.exists(error_preview_path_abs):
                        os.remove(error_preview_path_abs)
                except: pass 
                flash(f"Görüntü işlenemedi: {e}", 'danger')
            return redirect(url_for('dashboard'))

    # GET isteği
    uploaded_images = Image.query.filter_by(uploader_id=current_user.id).order_by(Image.id.desc()).all()
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
    
    # GÜNCELLEME: 'grade' (A/B/C/D) verisini de çek
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
                "grade": score.grade if score else None, # YENİ
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
    # === GÜNCELLENDİ: 'grade' verisini al ===
    data = request.json
    detection_id = data.get('detection_id')
    scores = data.get('scores')
    grade = data.get('grade') # YENİ: A/B/C/D bilgisini al

    if not detection_id or not scores:
        return jsonify({'success': False, 'error': 'Eksik veri'}), 400

    score_obj = Score.query.filter_by(
        detection_id=detection_id,
        user_id=current_user.id
    ).first()
    
    if not score_obj:
        score_obj = Score(detection_id=detection_id, user_id=current_user.id)
        db.session.add(score_obj)

    score_obj.grade = grade # YENİ: 'grade'i kaydet
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

@app.route('/api/add_detection', methods=['POST'])
@login_required
def api_add_detection():
    # ... (add_detection API'niz aynı kalıyor, DİKKAT: 'grade' ekledik) ...
    data = request.json
    image_id = data.get('image_id')
    coordinates = data.get('coordinates')
    if not image_id or not coordinates:
        return jsonify({'success': False, 'error': 'Eksik veri'}), 400
    image = Image.query.get(image_id)
    if not image:
        return jsonify({'success': False, 'error': 'İlişkili resim bulunamadı.'}), 404
    try:
        existing_detections = Detection.query.filter_by(parent_image_id=image_id).all()
        max_index = 0
        for det in existing_detections:
            try:
                index = int(det.id.split('_')[-1])
                if index > max_index: max_index = index
            except ValueError: pass
        new_index = max_index + 1
        new_detection_id = f"{image_id}_{new_index}"
        new_detection = Detection(
            id=new_detection_id,
            parent_image_id=image_id,
            coordinates_labelme={"shape_type": "rectangle", "points": coordinates}
        )
        db.session.add(new_detection)
        db.session.commit()
        # Yeni tespit verisine 'grade: None' ekle
        new_detection_data = {
            "id": new_detection.id,
            "coordinates_labelme": new_detection.coordinates_labelme,
            "scores": { 
                "grade": None, # YENİ
                "sitoplazma": None, "zona": None, "kumulus": None, "oopla": None 
            }
        }
        return jsonify({'success': True, 'new_detection': new_detection_data})
    except Exception as e:
        db.session.rollback()
        print(f"HATA: /api/add_detection: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete_detection', methods=['POST'])
@login_required
def api_delete_detection():
    # ... (delete_detection API'niz aynı kalıyor) ...
    data = request.json
    detection_id = data.get('detection_id')
    if not detection_id:
        return jsonify({'success': False, 'error': 'Eksik veri: detection_id eksik.'}), 400
    detection_to_delete = Detection.query.get(detection_id)
    if not detection_to_delete:
        return jsonify({'success': False, 'error': 'Tespit bulunamadı.'}), 404
    try:
        db.session.delete(detection_to_delete)
        db.session.commit()
        return jsonify({'success': True, 'deleted_id': detection_id})
    except Exception as e:
        db.session.rollback()
        print(f"HATA: /api/delete_detection: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================================
# ===  ADMIN PANELİ ROTALARI
# =====================================================================

@app.route('/admin')
@login_required
@admin_required 
def admin_dashboard():
    # ... (admin_dashboard istatistikleriniz aynı kalıyor) ...
    experts = User.query.filter_by(role='uzman').all()
    expert_stats = []
    for expert in experts:
        assigned_count = ImageAssignment.query.filter_by(expert_id=expert.id).count()
        scored_images_count = db.session.query(
            func.count(db.distinct(Detection.parent_image_id))
        ).join(Score).filter(Score.user_id == expert.id).scalar()
        expert_stats.append({
            'user': expert,
            'assigned_count': assigned_count,
            'scored_images_count': scored_images_count
        })
    images = Image.query.order_by(Image.id.desc()).all()
    image_stats = []
    for img in images:
        scorer_count = db.session.query(
            func.count(db.distinct(Score.user_id))
        ).join(Detection).filter(Detection.parent_image_id == img.id).scalar()
        image_stats.append({
            'image': img,
            'scorer_count': scorer_count
        })
    return render_template(
        'admin_dashboard.html', 
        image_stats=image_stats, 
        expert_stats=expert_stats 
    )

@app.route('/admin/assign/<image_id>', methods=['POST'])
@login_required
@admin_required
def admin_assign_image(image_id):
    # ... (Bu rota aynı kalıyor) ...
    expert_id = request.form.get('expert_id')
    if not expert_id:
        flash('Uzman seçilmedi.', 'danger')
        return redirect(url_for('admin_dashboard'))
    existing_assignment = ImageAssignment.query.filter_by(
        image_id=image_id, 
        expert_id=expert_id
    ).first()
    if existing_assignment:
        flash('Bu görüntü zaten bu uzmana atanmış.', 'info')
    else:
        new_assignment = ImageAssignment(image_id=image_id, expert_id=expert_id)
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
    # === GÜNCELLENDİ: Excel Raporuna 'Genel_Kalite' (grade) eklendi ===
    query = db.session.query(
        Image.id.label('Resim_ID'),
        Detection.id.label('Oosit_ID'),
        User.username.label('Uzman_Adı'),
        Score.grade.label('Genel_Kalite (A-D)'), # YENİ
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

@app.route('/admin/delete/image/<image_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_image(image_id):
    # ... (Bu rota aynı kalıyor) ...
    img = Image.query.get_or_404(image_id)
    try:
        if os.path.exists(img.file_path): os.remove(img.file_path)
        preview_filename = os.path.basename(img.preview_path)
        preview_full_path = os.path.join(app.config['PREVIEW_FOLDER'], preview_filename)
        if os.path.exists(preview_full_path): os.remove(preview_full_path)
    except OSError as e:
        flash(f"Disk üzerinden dosya silinirken bir hata oluştu: {e}", 'danger')
        return redirect(url_for('admin_dashboard'))
    db.session.delete(img)
    db.session.commit()
    flash(f"Görüntü '{image_id}' ve tüm ilişkili veriler kalıcı olarak silindi.", 'success')
    return redirect(url_for('admin_dashboard'))

# ... (Tüm /admin/download/ rotaları aynı kalıyor) ...
@app.route('/admin/download/czi/<image_id>')
@login_required
@admin_required
def admin_download_czi(image_id):
    img = Image.query.get_or_404(image_id)
    try:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], os.path.basename(img.file_path), as_attachment=True
        )
    except FileNotFoundError: abort(404, "Dosya bulunamadı.")
@app.route('/admin/download/png/<image_id>')
@login_required
@admin_required
def admin_download_png(image_id):
    img = Image.query.get_or_404(image_id)
    try:
        return send_from_directory(
            app.config['PREVIEW_FOLDER'], os.path.basename(img.preview_path), as_attachment=True
        )
    except FileNotFoundError: abort(404, "Dosya bulunamadı.")
@app.route('/admin/download/labelme/image/<image_id>')
@login_required
@admin_required
def admin_download_labelme_image(image_id):
    image = Image.query.get_or_404(image_id)
    labelme_output = {
        "version": "5.0.1", "flags": {}, "shapes": [],
        "imagePath": f"{image.id}.png", "imageData": None,
        "imageHeight": None, "imageWidth": None
    }
    try:
        preview_full_path = os.path.join(app.config['PREVIEW_FOLDER'], f"{image.id}.png")
        with PILImage.open(preview_full_path) as pil_img:
            labelme_output["imageWidth"] = pil_img.width
            labelme_output["imageHeight"] = pil_img.height
    except Exception: pass 
    detections = Detection.query.filter_by(parent_image_id=image_id).all()
    for det in detections:
        shape = {
            "label": det.id, "points": det.coordinates_labelme['points'],
            "group_id": None, "shape_type": "rectangle", "flags": {}
        }
        labelme_output["shapes"].append(shape)
    return jsonify(labelme_output), 200, {
        'Content-Disposition': f'attachment; filename={image.id}.json',
        'Content-Type': 'application/json'
    }

# ... (admin_image_crop rotası aynı kalıyor) ...
@app.route('/admin/image_crop/<detection_id>')
@login_required
@admin_required
def admin_image_crop(detection_id):
    det = Detection.query.get_or_404(detection_id)
    img = det.parent_image
    preview_filename = os.path.basename(img.preview_path)
    preview_full_path = os.path.join(app.config['PREVIEW_FOLDER'], preview_filename)
    if not os.path.exists(preview_full_path): abort(404, "Ana önizleme dosyası bulunamadı.")
    try:
        with PILImage.open(preview_full_path) as base_img:
            coords = det.coordinates_labelme['points']
            box = (int(coords[0][0]), int(coords[0][1]), int(coords[1][0]), int(coords[1][1]))
            cropped_img = base_img.crop(box)
            img_io = io.BytesIO()
            cropped_img.save(img_io, 'PNG')
            img_io.seek(0)
            return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"Görüntü kırpma hatası (ID: {detection_id}): {e}")
        abort(500, "Görüntü kırpılamadı.")

# ... (admin_create_user rotası aynı kalıyor) ...
@app.route('/admin/create_user', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        flash('Kullanıcı adı ve şifre alanları zorunludur.', 'danger')
        return redirect(url_for('admin_dashboard'))
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash(f"'{username}' kullanıcı adı zaten mevcut. Lütfen başka bir ad seçin.", 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password, role='uzman')
        db.session.add(new_user)
        db.session.commit()
        flash(f"Yeni uzman '{username}' başarıyla oluşturuldu.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Kullanıcı oluşturulurken bir hata oluştu: {e}", 'danger')
    return redirect(url_for('admin_dashboard'))

# ... (admin_delete_user rotası aynı kalıyor) ...
@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.id == current_user.id or user_to_delete.role == 'admin':
        flash('Admin kullanıcısı silinemez.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        username = user_to_delete.username
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f"Uzman '{username}' başarıyla silindi.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Uzman silinirken bir hata oluştu: {e}", 'danger')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')