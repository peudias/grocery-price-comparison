from pathlib import Path
import csv
import pytesseract
from PIL import Image


def clean_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def upscale(img: Image.Image, factor: float) -> Image.Image:
    w, h = img.size
    return img.resize((int(w * factor), int(h * factor)), Image.LANCZOS)


def ocr_price(image_path: Path) -> str:
    """
    OCR específico para preços:
    - converte para tons de cinza
    - aumenta a imagem
    - restringe caracteres (dígitos, vírgula, ponto, R$)
    - usa psm 7 (linha única)
    """
    img = Image.open(image_path).convert("L")

    img = upscale(img, 2.0)

    config = (
        "--psm 7 "
        "-c tessedit_char_whitelist=0123456789.,R$"
    )

    try:
        text = pytesseract.image_to_string(img, lang="por", config=config)
    except pytesseract.TesseractError as e:
        print(f"[ERRO OCR PRICE] {image_path}: {e}")
        return ""

    return clean_text(text)


def ocr_product_text(image_path: Path) -> str:
    """
    OCR específico para nomes de produtos:
    - converte para tons de cinza
    - aumenta mais (texto pequeno)
    - usa psm 6 (bloco de texto), sem whitelist agressiva
    """
    img = Image.open(image_path).convert("L")

    img = upscale(img, 3.0)

    config = "--psm 6"

    try:
        text = pytesseract.image_to_string(img, lang="por", config=config)
    except pytesseract.TesseractError as e:
        print(f"[ERRO OCR PROD] {image_path}: {e}")
        return ""

    return clean_text(text)


def main():
    backend_dir = Path(__file__).resolve().parents[2]
    SUPERMERCADO = "assai"

    crops_root = backend_dir / "data" / "results" / SUPERMERCADO / "yolo11" / "crops"
    metadata_csv = crops_root / "crops_metadata.csv"

    if not metadata_csv.exists():
        raise FileNotFoundError(f"Metadata de crops não encontrado: {metadata_csv}")

    price_dir = crops_root / "price"
    product_text_dir = crops_root / "product_text"

    if not price_dir.exists() or not product_text_dir.exists():
        raise FileNotFoundError(
            f"Pastas de crops não encontradas:\n  {price_dir}\n  {product_text_dir}"
        )

    ocr_csv = crops_root / "crops_ocr.csv"

    print(f"Supermercado: {SUPERMERCADO}")
    print(f"Lendo metadata: {metadata_csv}")
    print(f"Salvando OCR em: {ocr_csv}")

    with metadata_csv.open("r", encoding="utf-8") as f_in, \
            ocr_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames + ["ocr_text"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        num_in = 0
        num_ok = 0

        for row in reader:
            num_in += 1

            crop_filename = row["crop_filename"]
            class_name = row["class_name"]

            if class_name == "price":
                crop_path = price_dir / crop_filename
            elif class_name == "product_text":
                crop_path = product_text_dir / crop_filename
            else:
                crop_path = crops_root / class_name / crop_filename

            if not crop_path.exists():
                print(f"[AVISO] Crop não encontrado: {crop_path}, pulando.")
                continue

            if class_name == "price":
                text = ocr_price(crop_path)
            elif class_name == "product_text":
                text = ocr_product_text(crop_path)
            else:
                text = ocr_product_text(crop_path)

            row["ocr_text"] = text
            writer.writerow(row)
            num_ok += 1

    print()
    print(f"Linhas lidas (crops): {num_in}")
    print(f"Crops com OCR gerado: {num_ok}")
    print(f"Arquivo final de OCR: {ocr_csv}")


if __name__ == "__main__":
    main()
