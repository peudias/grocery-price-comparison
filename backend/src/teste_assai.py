from pathlib import Path
from ultralytics import YOLO
import csv
import cv2
import os

def test_assai_inference():
    # Caminhos baseados nos logs de treino
    backend_dir = Path(__file__).resolve().parents[1]
    
    # ONDE O MODELO ESTÁ
    model_path = backend_dir / "models" / "assai_v1.pt"
    
    # ONDE ESTÃO AS IMAGENS DO ASSAÍ (Processed)
    input_dir = backend_dir / "data" / "processed" / "assai"
    
    # ONDE SALVA OS RESULTADOS
    output_dir = backend_dir / "data" / "results" / "assai" / "test_yolo11"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not model_path.exists():
        print(f"ERRO: Modelo não encontrado em {model_path}")
        return

    print(f"--- TESTE DE INFERÊNCIA: ASSAÍ ---")
    model = YOLO(str(model_path))
    
    # Pega todas as imagens
    images = list(input_dir.glob("*.jpg")) + list(input_dir.glob("*.png"))
    
    if not images:
        print(f"Nenhuma imagem encontrada em {input_dir}")
        return

    for img_path in images:
        print(f"Detectando: {img_path.name}...")
        
        # Roda a predição
        results = model.predict(source=str(img_path), imgsz=1024, conf=0.3)
        
        # Salva a imagem com as caixinhas desenhadas pelo próprio YOLO
        results[0].save(filename=str(output_dir / f"result_{img_path.name}"))

    print(f"\n[OK] Teste finalizado! Veja os resultados em: {output_dir}")

if __name__ == "__main__":
    test_assai_inference()