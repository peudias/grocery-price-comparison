from pathlib import Path
import csv
import cv2

def main():
    # 1. Configuração de Caminhos
    backend_dir = Path(__file__).resolve().parents[1]
    SUPERMERCADO = "assai"
    
    # Pasta onde estão as imagens originais que o YOLO processou
    input_dir = backend_dir / "data" / "processed" / SUPERMERCADO
    
    # O CSV que o Script 01 gerou
    detections_csv = backend_dir / "data" / "results" / SUPERMERCADO / "test_yolo11" / "detections_price_text.csv"
    
    # Onde salva os recortes
    crops_root = backend_dir / "data" / "results" / SUPERMERCADO / "test_yolo11" / "crops_teste"
    crops_root.mkdir(parents=True, exist_ok=True)

    if not detections_csv.exists():
        print(f"[ERRO] O arquivo {detections_csv} não existe. Rode a inferência (Script 01) primeiro!")
        return

    print(f"[INFO] Gerando crops para: {SUPERMERCADO}")

    with detections_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        count = 0
        for row in reader:
            img_name = row["image"]
            class_name = row["class_name"]
            
            # Coordenadas
            x1, y1, x2, y2 = float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])
            
            # Carregar imagem original
            img_path = input_dir / img_name
            img = cv2.imread(str(img_path))
            
            if img is None:
                continue

            # Realizar o recorte (Slicing da matriz NumPy)
            # y1:y2 (linhas), x1:x2 (colunas)
            crop = img[int(y1):int(y2), int(x1):int(x2)]

            if crop.size == 0:
                continue

            # Organizar em subpastas por classe
            target_dir = crops_root / class_name
            target_dir.mkdir(exist_ok=True)

            # Nome único para o crop
            crop_filename = f"{count}_{class_name}_{img_name}"
            cv2.imwrite(str(target_dir / crop_filename), crop)
            
            count += 1

    print(f"[SUCESSO] {count} crops gerados em: {crops_root}")

if __name__ == "__main__":
    main()