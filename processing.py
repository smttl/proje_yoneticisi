# processing.py
import numpy as np
from PIL import Image as PILImage
from aicspylibczi import CziFile
from ultralytics import YOLO
import os

def process_czi_image(czi_path, image_id, preview_folder, yolo_model_path):
    """
    Bir .czi dosyasını işler, metadata'yı çıkarır, PNG önizlemesi oluşturur
    ve YOLOv8 ile oositleri tespit eder.
    """
    
    try:
        czi = CziFile(czi_path)
    except Exception as e:
        raise ValueError(f"CZI dosyası açılamadı veya bozuk: {e}")

    try:
        # --- 1. Metadata ve Ölçek Çıkarımı ---
        dims_str = czi.dims
        
        # === DÜZELTME BURADA ===
        # Özelliğin doğru adı '.scale' değil, '.pixel_sizes'
        scale_tuple = czi.pixel_sizes
        # =======================
        
        # 'X' (genişlik) boyutunun dizedeki indeksini bul
        x_index = dims_str.find('X')
        if x_index == -1:
            raise ValueError("CZI metadata içinde 'X' boyutu bulunamadı.")
        
        # Ölçek bilgisini al (metre cinsinden)
        scale_x = scale_tuple[x_index]
        if scale_x is None or scale_x == 0:
            raise ValueError("CZI metadata içinde X ölçeği okunamadı (değer 'None' veya 0).")
            
        # Metreyi mikrometreye (µm) çevir
        scale_um_per_pixel = scale_x * 1_000_000 
        
        metadata = {
            'scale_um_per_pixel': scale_um_per_pixel,
            'dimensions': czi.dims,
            'size_bytes': czi.size
        }

        # --- 2. PNG Önizlemesi Oluşturma ---
        img_data, _ = czi.read_image(S=0, T=0, Z=czi.dims_shape[0]['Z']//2, C=0)
        img_data = img_data[0, 0] # Boyutları sıkıştır (Y, X)
        
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
        raise e
    finally:
        # Hata olsun veya olmasın, CZI dosyasını kapat
        if 'czi' in locals() and hasattr(czi, 'close'):
            czi.close()

    # --- 3. PNG Kaydetme (CZI dosyası artık kapalı) ---
    preview_filename = f"{image_id}.png"
    preview_full_path = os.path.join(preview_folder, preview_filename)
    pil_img.save(preview_full_path)
    
    preview_path_relative = os.path.join(os.path.basename(preview_folder), preview_filename)

    # --- 4. YOLOv8 Tespiti (CZI dosyası artık kapalı) ---
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