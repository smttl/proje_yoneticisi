# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.sql import func 

db = SQLAlchemy()

class ImageAssignment(db.Model):
    __tablename__ = 'image_assignments'
    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(db.String(300), db.ForeignKey('images.id'), nullable=False)
    expert_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False) 
    assigned_at = db.Column(db.DateTime, server_default=func.now())
    __table_args__ = (db.UniqueConstraint('image_id', 'expert_id', name='_image_expert_uc'),)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='uzman')
    
    assigned_images = db.relationship('ImageAssignment', backref='expert', lazy=True, cascade="all, delete-orphan")
    uploaded_images = db.relationship('Image', backref='uploader', lazy=True) 
    scores_given = db.relationship('Score', backref='user', lazy=True)


class Image(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.String(300), primary_key=True) 
    file_path = db.Column(db.String(500), nullable=False) 
    preview_path = db.Column(db.String(500), nullable=False) 
    metadata_json = db.Column(db.JSON, nullable=True) 
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    detections = db.relationship('Detection', backref='parent_image', lazy=True, cascade="all, delete-orphan")
    assignments = db.relationship('ImageAssignment', backref='image', lazy=True, cascade="all, delete-orphan")


class Detection(db.Model):
    __tablename__ = 'detections'
    id = db.Column(db.String(350), primary_key=True) 
    parent_image_id = db.Column(db.String(300), db.ForeignKey('images.id'), nullable=False)
    coordinates_labelme = db.Column(db.JSON, nullable=False)
    scores = db.relationship('Score', backref='detection', lazy=True, cascade="all, delete-orphan")


class Score(db.Model):
    __tablename__ = 'scores'
    id = db.Column(db.Integer, primary_key=True)
    detection_id = db.Column(db.String(350), db.ForeignKey('detections.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    
    # === YENİ SÜTUN: A, B, C, D Sınıflaması ===
    grade = db.Column(db.String(1), nullable=True)
    
    # 1-5 arası alt puanlamalar
    score_sitoplazma = db.Column(db.Integer)
    score_zona = db.Column(db.Integer)
    score_kumulus = db.Column(db.Integer)
    score_oopla = db.Column(db.Integer)
    
    timestamp = db.Column(db.DateTime, server_default=func.now())
    __table_args__ = (db.UniqueConstraint('detection_id', 'user_id', name='_detection_user_uc'),)