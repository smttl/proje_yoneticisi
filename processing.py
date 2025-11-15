# processing.py
import numpy as np
from PIL import Image as PILImage
from aicspylibczi import CziFile
from ultralytics import YOLO
import os
import xml.etree.ElementTree as ET # XML'i ayrıştırmak için eklendi

def get_scale_from_xml(xml_string):
    """
    CZI dosyasının ham XML metadata'sını ayrıştırır ve X ekseni için
    ölçek bilgisini (metre cinsinden) döndürür.
    """
    try:
        # XML string'ini ayrıştır
        root = ET.fromstring(xml_string)
        
        # Zeiss XML'inde ölçek bilgisinin standart yolu (namespace'leri görmezden gelerek)
        # Yol: .../Metadata/Scaling/Items/Distance[@Id='X']/Value
        # '*//' ile namespace'leri atlayarak arama yapıyoruz.
        
        # Doğru etiketi bulmak için 'Scaling' etiketini arayalım
        scaling_node = root.find('.//{*}Scaling')
        if scaling_node is None:
            raise ValueError("XML içinde 'Scaling' düğümü bulunamadı.")

        # 'Scaling' içindeki 'Items' içindeki 'Distance' etiketlerini ara
        for distance in scaling_node.findall('.//{*}Distance'):
            if distance.get('Id') == 'X':
                value_node = distance.find('.//{*}Value')
                if value_node is not None:
                    scale_meters = float(value_node.text)
                    if scale_meters == 0:
                        raise ValueError("XML'de X ölçeği '0' olarak bulundu.")
                    return scale_meters
        
        # Eğer yukarıdaki yol başarısız olursa, alternatif bir yaygın yolu dene
        # Yol: .../Metadata/Information/Image/Scaling/Distance[@Id='X']/Value
        alt_scaling_node = root.find('.//{*}Information/{*}Image/{*}Scaling')
        if alt_scaling_node is not None:
            for distance in alt_scaling_node.findall('.//{*}Distance'):
                if distance.get('Id') == 'X':
                    value_node = distance.find('.//{*}Value')
                    if value_node is not None:
                        scale_meters = float(value_node.text)
                        if scale_meters == 0:
                            raise ValueError("XML'de (alternatif yol) X ölçeği '0' olarak bulundu.")
                        return scale_meters

        raise ValueError("XML içinde X ekseni için 'Distance' ölçek bilgisi bulunamadı.")
        
    except Exception as e:
        # XML ayrıştırma hatası
        raise ValueError(f"XML metadata ayrıştırılamadı: {e}")


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
        
        # === DÜZELTME: XML'den Oku ===
        # Doğrudan öznitelik erişimi başarısız olduğu için ham XML'i ayrıştırıyoruz.
        raw_xml = czi.raw_metadata
        if not raw_xml:
            raise ValueError("Dosyadan ham XML metadata okunamadı.")
            
        # XML'den X ölçeğini (metre cinsinden) al
        scale_x_meters = get_scale_from_xml(raw_xml)
        
        # Metreyi mikrometreye (µm) çevir
        scale_um_per_pixel = scale_x_meters * 1_000_000 
        
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
        # Hata ne olursa olsun (XML, Görüntü okuma vb.)
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