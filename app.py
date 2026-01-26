# app.py
import os
import json
import pandas as pd
import io
import zipfile 
import csv     
from PIL import Image as PILImage 
# ...
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, flash, abort,
    jsonify, session, send_file, send_from_directory, Response
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
            file_extension = os.path.splitext(filename)[1]
            
            # YENI ISIMLENDIRME FORMATI: YYYYMMDD_HHMMSS_GunlukSira
            now = datetime.now()
            date_part = now.strftime('%Y%m%d')
            time_part = now.strftime('%H%M%S')
            
            # Bugün eklenen dosya sayısını bul (ID bu tarihle başlayanlar)
            daily_count = Image.query.filter(Image.id.like(f"{date_part}%")).count()
            daily_index = daily_count + 1
            
            image_id = f"{date_part}_{time_part}_{daily_index}"
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
                flash(f"Görüntü {image_id} başarıyla yüklendi ve {len(detections)} oosit bulundu.", 'success')
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
    shape_type = data.get('shape_type', 'rectangle') # YENİ: shape_type parametresi (polygon/rectangle)
    
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
            coordinates_labelme={
                "shape_type": shape_type, # Polygon veya Rectangle
                "points": coordinates
            }
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
@app.route('/admin/download/labelme/box/<image_id>')
@login_required
@admin_required
def admin_download_labelme_box(image_id):
    return _generate_labelme_json(image_id, filter_shape='rectangle')

@app.route('/admin/download/labelme/polygon/<image_id>')
@login_required
@admin_required
def admin_download_labelme_polygon(image_id):
    return _generate_labelme_json(image_id, filter_shape='polygon')

# Eski route, default olarak rectangle (kutu) döndürsün
@app.route('/admin/download/labelme/image/<image_id>')
@login_required
@admin_required
def admin_download_labelme_image(image_id):
    return _generate_labelme_json(image_id, filter_shape='rectangle')

# === YENİ: Pascal VOC XML (LabelImg) Export ===
import xml.etree.ElementTree as ET

@app.route('/admin/download/xml/<image_id>')
@login_required
@admin_required
def admin_download_xml(image_id):
    xml_content, filename = _generate_pascal_voc_xml(image_id)
    return Response(
        xml_content,
        mimetype='application/xml',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )

@app.route('/admin/download_all_xml_dataset')
@login_required
@admin_required
def admin_download_all_xml_dataset():
    # 1. Hafızada bir ZIP buffer oluştur
    zip_buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
            images = Image.query.all()
            count = 0
            
            for img in images:
                # A. PNG Dosyasını Ekle
                png_filename = f"{img.id}.png"
                preview_full_path = os.path.join(app.config['PREVIEW_FOLDER'], png_filename)
                
                if os.path.exists(preview_full_path):
                    zip_f.write(preview_full_path, arcname=png_filename)
                    
                    # B. XML Dosyasını Ekle
                    # Helper fonksiyondan XML içeriğini al
                    xml_content, xml_filename = _generate_pascal_voc_xml(img.id)
                    zip_f.writestr(xml_filename, xml_content)
                    
                    count += 1
        
        zip_buffer.seek(0)
        flash(f"{count} adet görüntü ve XML dosyası başarıyla sıkıştırıldı.", "success")
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'Tum_Veri_Seti_LabelImg_{datetime.now().strftime("%Y%m%d")}.zip'
        )
        
    except Exception as e:
        flash(f"Zip oluşturulurken hata: {e}", "danger")
        return redirect(url_for('admin_dashboard'))

def _generate_pascal_voc_xml(image_id):
    image = Image.query.get_or_404(image_id)
    preview_full_path = os.path.join(app.config['PREVIEW_FOLDER'], f"{image.id}.png")
    
    # XML Kök Elementi
    annotation = ET.Element('annotation')
    
    ET.SubElement(annotation, 'folder').text = 'images'
    ET.SubElement(annotation, 'filename').text = f"{image.id}.png"
    ET.SubElement(annotation, 'path').text = preview_full_path
    
    source = ET.SubElement(annotation, 'source')
    ET.SubElement(source, 'database').text = 'Unknown'
    
    # Resim Boyutları
    width, height, depth = 0, 0, 3
    try:
        with PILImage.open(preview_full_path) as pil_img:
            width, height = pil_img.width, pil_img.height
    except Exception: pass
    
    size = ET.SubElement(annotation, 'size')
    ET.SubElement(size, 'width').text = str(width)
    ET.SubElement(size, 'height').text = str(height)
    ET.SubElement(size, 'depth').text = str(depth)
    
    ET.SubElement(annotation, 'segmented').text = '0'
    
    # Tespitler
    detections = Detection.query.filter_by(parent_image_id=image_id).all()
    for det in detections:
        obj = ET.SubElement(annotation, 'object')
        ET.SubElement(obj, 'name').text = 'oocyte' # Sınıf adı sabit 'oocyte'
        ET.SubElement(obj, 'pose').text = 'Unspecified'
        ET.SubElement(obj, 'truncated').text = '0'
        ET.SubElement(obj, 'difficult').text = '0'
        
        # Bounding Box Hesapla (Poligon olsa bile box'a çevir)
        points = det.coordinates_labelme['points']
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        
        bndbox = ET.SubElement(obj, 'bndbox')
        ET.SubElement(bndbox, 'xmin').text = str(int(min(xs)))
        ET.SubElement(bndbox, 'ymin').text = str(int(min(ys)))
        ET.SubElement(bndbox, 'xmax').text = str(int(max(xs)))
        ET.SubElement(bndbox, 'ymax').text = str(int(max(ys)))
        
    xml_str = ET.tostring(annotation, encoding='utf-8')
    return xml_str, f"{image.id}.xml"

@app.route('/admin/rename/image/<image_id>', methods=['POST'])
@login_required
@admin_required
def admin_rename_image(image_id):
    old_image = Image.query.get_or_404(image_id)
    new_image_id = request.form.get('new_image_id', '').strip()

    if not new_image_id:
        flash('Yeni görsel adı boş olamaz.', 'danger')
        return redirect(url_for('admin_image_detail', image_id=image_id))

    if new_image_id == image_id:
        flash('Yeni ad eski ad ile aynı olamaz.', 'warning')
        return redirect(url_for('admin_image_detail', image_id=image_id))

    # 1. Yeni ID'nin benzersiz olduğunu kontrol et
    if Image.query.get(new_image_id):
        flash(f"Bu ID ('{new_image_id}') zaten kullanımda. Lütfen başka bir ad seçin.", 'danger')
        return redirect(url_for('admin_image_detail', image_id=image_id))

    # 2. Dosya Yolları
    old_czi_path = old_image.file_path
    old_preview_path = os.path.join(app.config['PREVIEW_FOLDER'], os.path.basename(old_image.preview_path))
    
    # Uzantıyı koruyarak yeni dosya adlarını oluştur
    extension = os.path.splitext(old_czi_path)[1]
    new_czi_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{new_image_id}{extension}")
    new_preview_filename = f"{new_image_id}.png"
    new_preview_path_abs = os.path.join(app.config['PREVIEW_FOLDER'], new_preview_filename)
    new_preview_path_rel = f"previews/{new_preview_filename}"

    try:
        # 3. Dosyaları Fiziksel Olarak Yeniden Adlandır
        if os.path.exists(old_czi_path):
            os.rename(old_czi_path, new_czi_path)
        
        if os.path.exists(old_preview_path):
            os.rename(old_preview_path, new_preview_path_abs)

        # 4. Veritabanı İşlemleri (Transaction)
        # Yeni Image kaydını oluştur
        new_image = Image(
            id=new_image_id,
            file_path=new_czi_path,
            preview_path=new_preview_path_rel,
            metadata_json=old_image.metadata_json,
            uploader_id=old_image.uploader_id
        )
        db.session.add(new_image)
        db.session.flush() # ID'nin oluşması için

        # Atamaları Taşı
        for assignment in old_image.assignments:
            new_assignment = ImageAssignment(
                image_id=new_image_id,
                expert_id=assignment.expert_id,
                assigned_at=assignment.assigned_at
            )
            db.session.add(new_assignment)

        # Tespitleri (ve Puanları) Taşı
        # detection id formatı: {image_id}_{index}
        for old_det in old_image.detections:
            try:
                # index'i eski ID'den çıkar
                index_part = old_det.id.split('_')[-1]
            except:
                # Eğer index bulunamazsa rastgele bir şey vermek yerine loop index kullanabiliriz ama genelde formatımız belli
                index_part = "0"
            
            new_det_id = f"{new_image_id}_{index_part}"
            
            new_det = Detection(
                id=new_det_id,
                parent_image_id=new_image_id,
                coordinates_labelme=old_det.coordinates_labelme
            )
            db.session.add(new_det)
            db.session.flush() # new_det.id oluşması için

            # Puanları eski tespitten yeni tespite taşı
            for old_score in old_det.scores:
                new_score = Score(
                    detection_id=new_det_id,
                    user_id=old_score.user_id,
                    grade=old_score.grade,
                    score_sitoplazma=old_score.score_sitoplazma,
                    score_zona=old_score.score_zona,
                    score_kumulus=old_score.score_kumulus,
                    score_oopla=old_score.score_oopla,
                    timestamp=old_score.timestamp
                )
                db.session.add(new_score)

        # Eski kaydı sil (Cascade ile eski Detection, Score ve Assignment'lar silinecek)
        db.session.delete(old_image)
        db.session.commit()

        flash(f"Görüntü adı '{image_id}' -> '{new_image_id}' olarak başarıyla değiştirildi.", 'success')
        return redirect(url_for('admin_image_detail', image_id=new_image_id))

    except Exception as e:
        db.session.rollback()
        # Dosya yeniden adlandırmayı geri almaya çalış (Rollback File System)
        try:
            if os.path.exists(new_czi_path): os.rename(new_czi_path, old_czi_path)
            if os.path.exists(new_preview_path_abs): os.rename(new_preview_path_abs, old_preview_path)
        except:
            pass # Geri alma sırasında hata olursa yapacak bir şey yok, kritik loglanabilir
            
        flash(f"Ad değiştirme sırasında bir hata oluştu: {e}", 'danger')
        return redirect(url_for('admin_image_detail', image_id=image_id))

def _generate_labelme_json(image_id, filter_shape=None):
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
        # shape_type veritabanından, yoksa default 'rectangle'
        shape_type = det.coordinates_labelme.get('shape_type', 'rectangle')
        
        # Filtreleme: Eğer spesifik bir tip istenmişse ve uymuyorsa atla
        if filter_shape and shape_type != filter_shape:
            continue
            
        shape = {
            "label": det.id,
            "points": det.coordinates_labelme['points'],
            "group_id": None,
            "shape_type": shape_type,
            "flags": {}
        }
        labelme_output["shapes"].append(shape)
        
    return jsonify(labelme_output), 200, {
        'Content-Disposition': f'attachment; filename={image.id}_{filter_shape or "all"}.json',
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

# === YENİ: SINIFLANDIRMA (MOBILENETV2) VERİ SETİ İNDİRME ROTASI ===
@app.route('/admin/download_classification_dataset')
@login_required
@admin_required
def admin_download_classification_dataset():
    
    # 1. Hafızada (in-memory) bir ZIP dosyası oluştur
    zip_buffer = io.BytesIO()
    
    # 2. Hafızada bir CSV dosyası oluştur
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)
    
    # CSV başlık satırını yaz
    csv_writer.writerow([
        'dosya_adi', 
        'genel_puan', # A, B, C, D
        'sitoplazma', # 1-5
        'zona',       # 1-5
        'kumulus',    # 1-5
        'oopla'       # 1-5
    ])

    try:
        # 3. Veritabanından "A, B, C, D" notu verilmiş TÜM puanları çek
        scored_items = db.session.query(
            Score, Detection, Image
        ).join(
            Detection, Score.detection_id == Detection.id
        ).join(
            Image, Detection.parent_image_id == Image.id
        ).filter(
            Score.grade.in_(['A', 'B', 'C', 'D'])
        ).all()
        
        if not scored_items:
            flash('Sınıflandırma veri seti oluşturulamadı. Henüz A, B, C veya D olarak puanlanmış oosit yok.', 'danger')
            return redirect(url_for('admin_dashboard'))

        # 4. ZIP dosyasını yazma modunda aç
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
            
            processed_count = 0
            
            # 5. Her puanlanmış oosit için döngüye gir
            for score, detection, image in scored_items:
                
                # Benzersiz dosya adı: OositID_UzmanID_Puan.png
                png_filename = f"{detection.id}_u{score.user.id}_g{score.grade}.png"

                try:
                    # Ana PNG dosyasını aç
                    preview_full_path = os.path.join(app.config['PREVIEW_FOLDER'], f"{image.id}.png")
                    
                    with PILImage.open(preview_full_path) as base_img:
                        # Orijinal koordinatları al
                        coords = detection.coordinates_labelme['points']
                        box = (int(coords[0][0]), int(coords[0][1]), int(coords[1][0]), int(coords[1][1]))
                        
                        # Oositi Kırp
                        cropped_img = base_img.crop(box)
                        
                        # === 512x512 PADDING (BOZULMAYI ÖNLEME) ===
                        
                        # 1. Kırpılmış görüntüyü en-boy oranını koruyarak 512 sınırına küçült/büyüt
                        # LANCZOS en yüksek kaliteli yeniden örnekleme filtresidir
                        cropped_img.thumbnail((512, 512), PILImage.Resampling.LANCZOS)
                        
                        # 2. Siyah (RGB=0,0,0) 512x512 bir arka plan oluştur
                        # (Kırpılmış resim RGB değilse diye 'RGB'ye çeviriyoruz)
                        padded_img = PILImage.new("RGB", (512, 512), (0, 0, 0))
                        
                        # 3. Kırpılmış görüntüyü bu siyah arka planın ortasına yapıştır
                        paste_x = (512 - cropped_img.width) // 2
                        paste_y = (512 - cropped_img.height) // 2
                        padded_img.paste(cropped_img.convert("RGB"), (paste_x, paste_y))
                        
                        # 4. Son 512x512 görüntüyü hafızada bir tampona kaydet
                        img_io = io.BytesIO()
                        padded_img.save(img_io, 'PNG')
                        img_io.seek(0)
                        
                        # 5. Bu görüntüyü ZIP dosyasına ekle
                        zip_f.writestr(png_filename, img_io.getvalue())
                        
                        # 6. CSV dosyasına ilgili satırı ekle
                        csv_writer.writerow([
                            png_filename,
                            score.grade,
                            score.score_sitoplazma,
                            score.score_zona,
                            score.score_kumulus,
                            score.score_oopla
                        ])
                        
                        processed_count += 1

                except Exception as e:
                    print(f"HATA: Veri seti oluşturulurken {detection.id} işlenemedi: {e}")
            
            # 6. CSV dosyasını ZIP'e ekle
            zip_f.writestr('labels.csv', csv_buffer.getvalue())

        zip_buffer.seek(0)
        
        flash(f'Başarılı: {processed_count} adet görüntü ve 1 adet labels.csv dosyası ile .zip arşivi oluşturuldu.', 'success')
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'MobileNet_VeriSeti_{datetime.now().strftime("%Y%m%d")}.zip'
        )
        
    except Exception as e:
        flash(f"Veri seti oluşturulurken bir hata oluştu: {e}", 'danger')
        print(f"HATA: /admin/download_classification_dataset: {e}")
        return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')