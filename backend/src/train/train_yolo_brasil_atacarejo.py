from pathlib import Path
from ultralytics import YOLO

def main():
    backend_dir = Path(__file__).resolve().parents[2]
    dataset_dir = backend_dir / "data" / "yolo11"
    data_yaml = dataset_dir / "data.yaml"

    model = YOLO("yolo11s.pt")

    runs_dir = dataset_dir / "runs"

    results = model.train(
        data=str(data_yaml),
        epochs=80,
        imgsz=1024,
        batch=4,
        project=str(runs_dir),
        name="yolo11s_price_text",
        device="cpu",
    )

    print("Treino finalizado. Resultados em:", results.save_dir)

if __name__ == "__main__":
    main()