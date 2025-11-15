# processing.py
import numpy as np
from PIL import Image as PILImage
from ultralytics import YOLO
import os
from aicsimageio import AICSImage

def process_czi_image(czi_path, image_id, preview_folder, yolo_model_path):
    """
    Bir .czi dosyasını aicsimageio kullanarak işler.
    Eğer görüntü 'uint8' ise, verilere HİÇ DOKUNMAZ ("olduğu gibi" alır).
    Eğer 'uint16' vb. ise, kontrastı ayarlar (p2-p98).
    """
    
    try:
        img = AICSImage(czi_path)
    except Exception as e:
        raise ValueError(f"CZI dosyası AICSImageIO ile açılamadı: {e}")

    # === DEBUG: Sunucu konsoluna görüntünün bilgilerini yaz ===
    print(f"DEBUG: Görüntü ID: {image_id}")
    print(f"DEBUG: Görüntü Boyutları (dims): {img.dims}")
    print(f"DEBUG: Kanal Sayısı (img.dims.C): {img.dims.C}")
    print(f"DEBUG: Sahne Sayısı (img.dims.S): {img.dims.S}")
    print(f"DEBUG: Piksel Tipi (dtype): {img.dtype}")
    # ========================================================

    try:
        # --- 1. Metadata ve Ölçek Çıkarımı ---
        if img.physical_pixel_sizes.X is None:
            raise ValueError("Metadata içinde fiziksel piksel boyutu (X) bulunamadı.")
        
        scale_x_meters = img.physical_pixel_sizes.X
        scale_um_per_pixel = scale_x_meters * 1_000_000 
        
        metadata = {
            'scale_um_per_pixel': scale_um_per_pixel,
            'dimensions': img.dims.order,
            'size_bytes': os.path.getsize(czi_path)
        }

        # --- 2. PNG Önizlemesi Oluşturma ---
        
        z_slice = img.dims.Z // 2
        num_channels = img.dims.C
        num_scenes = img.dims.S
        pixel_type = img.dtype  # Görüntünün veri tipini (uint8, uint16 vb.) al
        
        def normalize_channel(channel_data):
            """SADECE uint8 OLMAYAN veriler için kontrastı ayarlar"""
            data = channel_data.astype(np.float32)
            p2 = np.percentile(data, 2)
            p98 = np.percentile(data, 98)
            data = np.clip(data, p2, p98)
            
            min_val = np.min(data)
            max_val = np.max(data)
            
            if max_val == min_val:
                return np.zeros_like(data, dtype=np.uint8)
            
            data = (data - min_val) / (max_val - min_val)
            return (data * 255).astype(np.uint8)

        
        # === RENK ALGISI (Önce Sahne, sonra Kanal) ===
        
        if num_scenes >= 3 and num_channels == 1:
            # === RENK (Sahne'den) ===
            print("DEBUG: Renk modu 'Scene' (S:3, C:1) olarak algılandı.")
            img_data_rgb = np.zeros((img.dims.Y, img.dims.X, 3), dtype=np.uint8)

            # R (S=0), G (S=1), B (S=2) kanallarını al
            channel_r = img.get_image_data("YX", Z=z_slice, T=0, C=0, S=0)
            channel_g = img.get_image_data("YX", Z=z_slice, T=0, C=0, S=1)
            channel_b = img.get_image_data("YX", Z=z_slice, T=0, C=0, S=2)

            # === DOKUNMA KONTROLÜ ===
            if pixel_type != np.uint8:
                print("DEBUG: Veri tipi uint8 değil, normalize ediliyor...")
                img_data_rgb[:, :, 0] = normalize_channel(channel_r)
                img_data_rgb[:, :, 1] = normalize_channel(channel_g)
                img_data_rgb[:, :, 2] = normalize_channel(channel_b)
            else:
                print("DEBUG: Veri tipi uint8, normalize edilmiyor (olduğu gibi alınıyor).")
                img_data_rgb[:, :, 0] = channel_r
                img_data_rgb[:, :, 1] = channel_g
                img_data_rgb[:, :, 2] = channel_b
            # ========================
            
            pil_img = PILImage.fromarray(img_data_rgb, 'RGB')
            
        elif num_channels >= 3:
            # === RENK (Kanal'dan) ===
            print("DEBUG: Renk modu 'Channel' (C:3) olarak algılandı.")
            img_data_rgb = np.zeros((img.dims.Y, img.dims.X, 3), dtype=np.uint8)

            channel_r = img.get_image_data("YX", Z=z_slice, T=0, C=0)
            channel_g = img.get_image_data("YX", Z=z_slice, T=0, C=1)
            channel_b = img.get_image_data("YX", Z=z_slice, T=0, C=2)
            
            if pixel_type != np.uint8:
                print("DEBUG: Veri tipi uint8 değil, normalize ediliyor...")
                img_data_rgb[:, :, 0] = normalize_channel(channel_r)
                img_data_rgb[:, :, 1] = normalize_channel(channel_g)
                img_data_rgb[:, :, 2] = normalize_channel(channel_b)
            else:
                print("DEBUG: Veri tipi uint8, normalize edilmiyor (olduğu gibi alınıyor).")
                img_data_rgb[:, :, 0] = channel_r
                img_data_rgb[:, :, 1] = channel_g
                img_data_rgb[:, :, 2] = channel_b
            
            pil_img = PILImage.fromarray(img_data_rgb, 'RGB')
            
        else:
            # === SİYAH BEYAZ (Grayscale) ===
            print("DEBUG: Mod 'Grayscale' (C:1, S:1) olarak algılandı.")
            img_data = img.get_image_data("YX", Z=z_slice, C=0, T=0, S=0)
            
            if pixel_type != np.uint8:
                print("DEBUG: Veri tipi uint8 değil, normalize ediliyor...")
                img_data_normalized = normalize_channel(img_data)
            else:
                print("DEBUG: Veri tipi uint8, normalize edilmiyor (olduğu gibi alınıyor).")
                img_data_normalized = img_data
                
            pil_img = PILImage.fromarray(img_data_normalized, 'L')

    except Exception as e:
        raise e

    # --- 3. PNG Kaydetme ---
    preview_filename = f"{image_id}.png"
    preview_full_path = os.path.join(preview_folder, preview_filename)
    pil_img.save(preview_full_path)
    
    # Veritabanına kaydedilecek web-uyumlu yol
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