from pathlib import Path
from ultralytics import YOLO
import os

def main():
    # Script está em src/train, sobe dois níveis para chegar na raiz da backend
    backend_dir = Path(__file__).resolve().parents[2]
    
    # Aponta para a pasta do Assaí
    dataset_dir = backend_dir / "data" / "dataset" / "assai"
    data_yaml = dataset_dir / "data.yaml"

    os.chdir(dataset_dir)

    # Carrega o modelo base que está na pasta models
    model_base = backend_dir / "models" / "yolo11s.pt"
    model = YOLO(str(model_base))

    # Onde os resultados (best.pt) serão salvos
    runs_dir = dataset_dir / "runs"

    print(f"--- Treino Portável: ASSAÍ ---")
    print(f"Diretório de Trabalho: {os.getcwd()}")

    # 2. Treinamento
    results = model.train(
        data="data.yaml",
        epochs=80,          # Mesmo padrão usado no Brasil Atacarejo
        imgsz=1024,
        batch=4,
        project=str(runs_dir),
        name="weights",      # Criar a pasta 'weights' dentro de 'runs'
        device="cpu",        # Rodando no processador
    )

    print("\nTreino do Assaí finalizado!")

if __name__ == "__main__":
    main()