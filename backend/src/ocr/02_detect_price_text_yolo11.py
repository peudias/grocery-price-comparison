from pathlib import Path
from ultralytics import YOLO
import csv

try:
    import cv2
except ImportError:
    cv2 = None
    print("AVISO: opencv-python não está instalado. As imagens anotadas não serão geradas.")


def main():
    backend_dir = Path(__file__).resolve().parents[2]

    model_path = (
        backend_dir
        / "data"
        / "yolo11"
        / "runs"
        / "yolo11s_price_text"
        / "weights"
        / "best.pt"
    )

    input_dir = backend_dir / "data" / "processed" / "brasil_atacarejo"

    output_vis_dir = backend_dir / "data" / "results" / "yolo11" / "predictions_vis"
    output_vis_dir.mkdir(parents=True, exist_ok=True)

    output_csv = backend_dir / "data" / "results" / "yolo11" / "detections_price_text.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    print(f"Carregando modelo de: {model_path}")
    model = YOLO(str(model_path))
    class_names = model.names

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "image",
                "class_id",
                "class_name",
                "conf",
                "x1",
                "y1",
                "x2",
                "y2",
            ]
        )

        image_extensions = ("*.png", "*.jpg", "*.jpeg")
        image_paths = []
        for ext in image_extensions:
            image_paths.extend(sorted(input_dir.glob(ext)))

        if not image_paths:
            print(f"Nenhuma imagem encontrada em {input_dir}")
            return

        for img_path in image_paths:
            print(f"Rodando YOLO em: {img_path.name}")
            results = model.predict(
                source=str(img_path),
                imgsz=1024,
                conf=0.25,
                iou=0.7,
                verbose=False,
            )

            r = results[0]

            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                cls_name = class_names[cls_id]

                writer.writerow(
                    [
                        img_path.name,
                        cls_id,
                        cls_name,
                        f"{conf:.4f}",
                        f"{x1:.1f}",
                        f"{y1:.1f}",
                        f"{x2:.1f}",
                        f"{y2:.1f}",
                    ]
                )

            if cv2 is not None:
                import numpy as np

                img = cv2.imread(str(img_path))
                if img is None:
                    print(f"Não consegui ler {img_path}, pulando visualização.")
                else:
                    for box in r.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        label = f"{class_names[cls_id]} {conf:.2f}"

                        p1 = (int(x1), int(y1))
                        p2 = (int(x2), int(y2))

                        cv2.rectangle(img, p1, p2, (0, 255, 0), 2)
                        cv2.putText(
                            img,
                            label,
                            (p1[0], max(p1[1] - 5, 0)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            1,
                            cv2.LINE_AA,
                        )

                    out_path = output_vis_dir / img_path.name
                    cv2.imwrite(str(out_path), img)
            else:
                pass

    print()
    print("Detecções salvas em:", output_csv)
    print("Imagens com boxes (se cv2 instalado) em:", output_vis_dir)


if __name__ == "__main__":
    main()
