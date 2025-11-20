from pathlib import Path
import subprocess
import sys

def run_script(label: str, relative_path: str) -> None:
    src_dir = Path(__file__).resolve().parent
    script_path = src_dir / relative_path

    print(f"\n[PIPELINE] {label}")
    print(f"[PIPELINE] Executando: {script_path}")

    subprocess.run([sys.executable, str(script_path)], check=True)


def run_ocr_pipeline() -> None:
    steps = [
        ("01 - YOLO: detectar price_text",              "ocr/01_price_text_inference.py"),
        ("02 - Gerar crops das detecções",              "ocr/02_crops_from_detections.py"),
        ("03 - OCR dos crops",                          "ocr/03_ocr_crops.py"),
        ("04 - Associar produtos e preços",             "ocr/04_link_products_and_prices.py"),
        ("05 - Normalizar preços vindos do OCR",        "ocr/05_normalize_prices_from_ocr.py"),
        ("06 - Exportar lista simples produto/preço",   "ocr/06_export_flat_product_price_list.py"),
    ]

    for label, rel in steps:
        run_script(label, rel)

    print("\n[PIPELINE] OCR concluído!")


def pipeline_brasil_atacarejo() -> None:
    run_script(
        "Download e conversão dos folhetos do Brasil Atacarejo",
        "download/download_brasil_atacarejo.py",
    )
    run_ocr_pipeline()


if __name__ == "__main__":
    pipeline_brasil_atacarejo()