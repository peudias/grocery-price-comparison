from __future__ import annotations
from pathlib import Path
from typing import List
import csv
import cv2

def main() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    SUPERMERCADO = "assai"
    input_dir = backend_dir / "data" / "processed" / SUPERMERCADO

    detections_csv = (
        backend_dir
        / "data"
        / "results"
        / SUPERMERCADO
        / "yolo11"
        / "detections_price_text.csv"
    )

    crops_root = backend_dir / "data" / "results" / SUPERMERCADO / "yolo11" / "crops"
    price_dir = crops_root / "price"
    product_text_dir = crops_root / "product_text"

    price_dir.mkdir(parents=True, exist_ok=True)
    product_text_dir.mkdir(parents=True, exist_ok=True)

    metadata_csv = crops_root / "crops_metadata.csv"

    if not detections_csv.exists():
        raise FileNotFoundError(f"Arquivo de detecções não encontrado: {detections_csv}")

    print(f"[INFO] Supermercado: {SUPERMERCADO}")
    print(f"[INFO] Lendo detecções de: {detections_csv}")
    print(f"[INFO] Salvando crops em: {crops_root}")
    print(f"[INFO] Salvando metadata em: {metadata_csv}")

    with detections_csv.open("r", encoding="utf-8", newline="") as f_in, \
         metadata_csv.open("w", encoding="utf-8", newline="") as f_out:

        reader = csv.DictReader(f_in)

        fieldnames = [
            "crop_filename",
            "orig_image",
            "class_id",
            "class_name",
            "conf",
            "x1",
            "y1",
            "x2",
            "y2",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        counters = {
            "price": 0,
            "product_text": 0,
            "other": 0,
        }
        total_crops = 0

        for row in reader:
            image_name = row["image"]
            class_id = row["class_id"]
            class_name = row["class_name"]
            conf = row["conf"]

            x1 = float(row["x1"])
            y1 = float(row["y1"])
            x2 = float(row["x2"])
            y2 = float(row["y2"])

            img_path = input_dir / image_name
            if not img_path.exists():
                print(f"[AVISO] Imagem não encontrada, pulando: {img_path}")
                continue

            img = cv2.imread(str(img_path))
            if img is None:
                print(f"[AVISO] Não consegui carregar a imagem, pulando: {img_path}")
                continue

            h, w = img.shape[:2]

            x1_i = max(0, min(int(x1), w - 1))
            y1_i = max(0, min(int(y1), h - 1))
            x2_i = max(0, min(int(x2), w))
            y2_i = max(0, min(int(y2), h))

            if x2_i <= x1_i or y2_i <= y1_i:
                print(f"[AVISO] Bounding box inválido para {image_name}, pulando.")
                continue

            crop = img[y1_i:y2_i, x1_i:x2_i]

            if class_name == "price":
                target_dir = price_dir
                counters["price"] += 1
                idx = counters["price"]
            elif class_name == "product_text":
                target_dir = product_text_dir
                counters["product_text"] += 1
                idx = counters["product_text"]
            else:
                other_dir = crops_root / class_name
                other_dir.mkdir(parents=True, exist_ok=True)
                target_dir = other_dir
                counters["other"] += 1
                idx = counters["other"]

            crop_name = f"{Path(image_name).stem}_{class_name}_crop{idx}.png"
            crop_path = target_dir / crop_name

            cv2.imwrite(str(crop_path), crop)
            total_crops += 1
            print(f"[OK] Crop salvo: {crop_path.relative_to(crops_root)}")

            writer.writerow(
                {
                    "crop_filename": crop_name,
                    "orig_image": image_name,
                    "class_id": class_id,
                    "class_name": class_name,
                    "conf": conf,
                    "x1": f"{x1:.1f}",
                    "y1": f"{y1:.1f}",
                    "x2": f"{x2:.1f}",
                    "y2": f"{y2:.1f}",
                }
            )

    print()
    print(f"[FINALIZADO] {total_crops} crops gerados.")
    print(f"  - price:        {counters['price']}")
    print(f"  - product_text: {counters['product_text']}")
    print(f"  - outras:       {counters['other']}")
    print(f"Metadata salvo em: {metadata_csv}")


if __name__ == "__main__":
    main()
