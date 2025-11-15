# processing.py
import numpy as np
from PIL import Image as PILImage
from ultralytics import YOLO
import os

# Kütüphaneyi değiştiriyoruz: aicspylibczi -> aicsimageio
from aicsimageio import AICSImage

def process_czi_image(czi_path, image_id, preview_folder, yolo_model_path):
    """
    Bir .czi dosyasını aicsimageio kullanarak işler, metadata'yı çıkarır, 
    PNG önizlemesi oluşturur ve YOLOv8 ile oositleri tespit eder.
    """
    
    # 1. Görüntüyü AICSImage ile aç
    # Bu nesne, metadata ve görüntü verisine standart erişim sağlar.
    try:
        img = AICSImage(czi_path)
    except Exception as e:
        raise ValueError(f"CZI dosyası AICSImageIO ile açılamadı: {e}")

    try:
        # --- 1. Metadata ve Ölçek Çıkarımı ---
        
        # aicsimageio, ölçek bilgisine 'physical_pixel_sizes' ile
        # doğrudan ve güvenilir bir şekilde erişir.
        if img.physical_pixel_sizes.X is None:
            raise ValueError("Metadata içinde fiziksel piksel boyutu (X) bulunamadı.")
        
        # Değer metre cinsindendir (örn: 0.0000005)
        scale_x_meters = img.physical_pixel_sizes.X
        
        # Metreyi mikrometreye (µm) çevir
        scale_um_per_pixel = scale_x_meters * 1_000_000 
        
        metadata = {
            'scale_um_per_pixel': scale_um_per_pixel,
            'dimensions': img.dims.order, # 'TCZYX' gibi
            'size_bytes': os.path.getsize(czi_path)
        }

        # --- 2. PNG Önizlemesi Oluşturma ---
        # Görüntü verisini numpy dizisi olarak al
        # Ortadaki Z dilimini, ilk kanalı ve ilk zamanı alıyoruz
        z_slice = img.dims.Z // 2
        
        # get_image_data("YX", ...) sadece 2 boyutlu (Y, X) bir dilim döndürür
        img_data = img.get_image_data("YX", Z=z_slice, C=0, T=0)
        
        # Görüntüyü 8-bit'e normalize et (0-255)
        img_data = img_data.astype(np.float32)
        img_min = np.min(img_data)
        img_max = np.max(img_data)
        
        if img_max == img_min:
            img_data = np.zeros_like(img_data, dtype=np.uint8)
        else:
            img_data = (img_data - img_min) / (img_max - img_min)
            img_data = (img_data * 255).astype(np.uint8)
        
        pil_img = PILImage.fromarray(img_data)

    except Exception as e:
        # Hata ne olursa olsun (XML, Görüntü okuma vb.)
        raise e
    
    # Not: aicsimageio dosyaları otomatik kapattığı için 'finally' bloğuna gerek yok.

   # --- 3. PNG Kaydetme ---
    preview_filename = f"{image_id}.png"
    # 'preview_folder' artık '/path/to/project/static/previews'
    preview_full_path = os.path.join(preview_folder, preview_filename)
    pil_img.save(preview_full_path)
    
    # === DÜZELTME: Yolu manuel olarak ve her zaman (/) ile birleştir ===
    # HTML/url_for için veritabanına kaydedilecek yol
    # "previews" + "/" + "IMG...png" = "previews/IMG...png"
    preview_path_relative = f"previews/{preview_filename}"

    # --- 4. YOLOv8 Tespiti ---
    model = YOLO(yolo_model_path)
    results = model.predict(preview_full_path)
    
    detections = []
    for i, box in enumerate(results[0].boxes):
        xyxy = box.xyxy[0].cpu().numpy()
        x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
        
        detection_id = f"{image_id}_{i+1}"
        coordinates_labelme = {
            "shape_type": "rectangle",
            "points": [ [x1, y1], [x2, y2] ]
        }
        
        detections.append({
            "id": detection_id,
            "coordinates_labelme": coordinates_labelme
        })

    return metadata, preview_path_relative, detections