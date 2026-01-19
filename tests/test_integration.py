
import sys
import os
import unittest
import io
import json
from unittest.mock import MagicMock

# --- MOCKING DEPENDENCIES START ---
sys.modules['aicsimageio'] = MagicMock()
sys.modules['ultralytics'] = MagicMock()
# --- MOCKING DEPENDENCIES END ---

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, User, Image, Detection, bcrypt

class ProjeYoneticisiTest(unittest.TestCase):
    def setUp(self):
        # Test konfigurasyonu
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' 
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['UPLOAD_FOLDER'] = 'tests/uploads' 
        app.config['PREVIEW_FOLDER'] = 'tests/previews'
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['PREVIEW_FOLDER'], exist_ok=True)

        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        
        db.create_all()
        
        # Auth MOCK: Şifre kontrolünü devre dışı bırak
        # Bu sayede hash uyumsuzluğu vb. ile uğraşmayız.
        bcrypt.check_password_hash = MagicMock(return_value=True)
        
        # Kullanıcı oluştur (Şifre önemli değil, mock true dönecek)
        if not User.query.filter_by(username='admin').first():
            self.admin_user = User(username='admin', password='any_password', role='admin')
            db.session.add(self.admin_user)
            db.session.commit()
        else:
            self.admin_user = User.query.filter_by(username='admin').first()
        
        # Giriş yap
        with self.client:
            self.client.post('/login', data={'username': 'admin', 'password': 'admin'})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_02_polygon_annotation(self):
        """Test: Yeni Poligon (Polygon) ekleme ve kaydetme"""
        
        img = Image(
            id='20250120_120000_1',
            file_path='tests/uploads/20250120_120000_1.czi',
            preview_path='previews/20250120_120000_1.png',
            metadata_json={},
            uploader_id=self.admin_user.id
        )
        db.session.add(img)
        db.session.commit()
        
        # API'ye Poligon Tespiti Gönder
        payload = {
            'image_id': img.id,
            'coordinates': [[10, 10], [50, 10], [50, 50], [10, 50]], 
            'shape_type': 'polygon'
        }
        
        response = self.client.post('/api/add_detection', 
                                    data=json.dumps(payload),
                                    content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data['success'])
        
        det = Detection.query.get(json_data['new_detection']['id'])
        self.assertIsNotNone(det)
        self.assertEqual(det.coordinates_labelme['shape_type'], 'polygon')
        self.assertEqual(det.coordinates_labelme['points'], payload['coordinates'])

    def test_03_box_annotation(self):
        """Test: Eski Kutu (Rectangle) ekleme (Geriye uyumluluk)"""
        img_id = '20250120_120000_2'
        img = Image(id=img_id, file_path='x', preview_path='y', uploader_id=self.admin_user.id)
        db.session.add(img)
        db.session.commit()

        payload = {
            'image_id': img_id,
            'coordinates': [[0, 0], [100, 100]],
            'shape_type': 'rectangle'
        }
        response = self.client.post('/api/add_detection', 
                                    data=json.dumps(payload),
                                    content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        det = Detection.query.filter_by(parent_image_id=img_id).first()
        self.assertEqual(det.coordinates_labelme['shape_type'], 'rectangle')

    def test_04_separated_export(self):
        """Test: Kutu ve Poligon verilerinin ayrı ayrı indirilmesi"""
        img_id = 'test_export_img'
        img = Image(id=img_id, file_path='x', preview_path='y', uploader_id=self.admin_user.id)
        db.session.add(img)
        
        box_det = Detection(id='box_1', parent_image_id=img_id, 
                            coordinates_labelme={"shape_type": "rectangle", "points": [[0,0],[1,1]]})
        db.session.add(box_det)
        
        poly_det = Detection(id='poly_1', parent_image_id=img_id, 
                             coordinates_labelme={"shape_type": "polygon", "points": [[0,0],[1,0],[0,1]]})
        db.session.add(poly_det)
        db.session.commit()
        
        resp_box = self.client.get(f'/admin/download/labelme/box/{img_id}')
        data_box = resp_box.get_json()
        self.assertEqual(len(data_box['shapes']), 1)
        self.assertEqual(data_box['shapes'][0]['shape_type'], 'rectangle')
        
        resp_poly = self.client.get(f'/admin/download/labelme/polygon/{img_id}')
        data_poly = resp_poly.get_json()
        self.assertEqual(len(data_poly['shapes']), 1)
        self.assertEqual(data_poly['shapes'][0]['shape_type'], 'polygon')

if __name__ == '__main__':
    unittest.main()
