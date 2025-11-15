# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Image(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.String(100), primary_key=True) # "IMG_001"
    file_path = db.Column(db.String(300), nullable=False) # Orijinal .czi yolu
    preview_path = db.Column(db.String(300), nullable=False) # Gösterim için .png yolu
    metadata_json = db.Column(db.JSON, nullable=True) # Ölçek bilgisi dahil tüm metadata
    detections = db.relationship('Detection', backref='parent_image', lazy=True)

class Detection(db.Model):
    __tablename__ = 'detections'
    id = db.Column(db.String(150), primary_key=True) # "IMG_001_1"
    parent_image_id = db.Column(db.String(100), db.ForeignKey('images.id'), nullable=False)
    coordinates_labelme = db.Column(db.JSON, nullable=False) # LabelMe formatı
    scores = db.relationship('Score', backref='detection', lazy=True)

class Score(db.Model):
    __tablename__ = 'scores'
    id = db.Column(db.Integer, primary_key=True)
    detection_id = db.Column(db.String(150), db.ForeignKey('detections.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    score_sitoplazma = db.Column(db.Integer)
    score_zona = db.Column(db.Integer)
    score_kumulus = db.Column(db.Integer)
    score_oopla = db.Column(db.Integer)
    
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    
    # Bir uzmanın bir oositi sadece bir kez puanlamasını sağlamak için
    __table_args__ = (db.UniqueConstraint('detection_id', 'user_id', name='_detection_user_uc'),)