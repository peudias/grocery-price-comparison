from pathlib import Path
import csv

def clean_text(text: str) -> str:
    if text is None:
        return ""
    return " ".join(text.strip().split())

def main():
    backend_dir = Path(__file__).resolve().parents[2]
    SUPERMERCADO = "assai"

    base_results = backend_dir / "data" / "results" / SUPERMERCADO / "yolo11"
    input_csv = base_results / "products_prices_fixed.csv"
    output_csv = base_results / "products_simple.csv"

    if not input_csv.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_csv}")

    print(f"Supermercado: {SUPERMERCADO}")
    print(f"Lendo dados de: {input_csv}")
    print(f"Gerando CSV simplificado em: {output_csv}")

    with input_csv.open("r", encoding="utf-8") as f_in, \
         output_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)

        fieldnames = ["product_ocr", "price_raw"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total = 0
        escritos = 0

        for row in reader:
            total += 1

            product = clean_text(row.get("product_ocr", ""))
            price = clean_text(row.get("price_raw", ""))

            writer.writerow(
                {
                    "product_ocr": product,
                    "price_raw": price,
                }
            )
            escritos += 1

    print(f"Linhas lidas: {total}")
    print(f"Linhas escritas no CSV simples: {escritos}")
    print(f"Arquivo gerado: {output_csv}")


if __name__ == "__main__":
    main()
