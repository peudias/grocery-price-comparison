from pathlib import Path
import csv


def main():
    backend_dir = Path(__file__).resolve().parents[2]

    base_results = backend_dir / "data" / "results" / "yolo11"
    full_csv = base_results / "products_prices.csv"
    simple_csv = base_results / "products_prices_simple.csv"

    if not full_csv.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {full_csv}")

    print(f"Lendo: {full_csv}")
    print(f"Gerando versão simplificada em: {simple_csv}")

    with full_csv.open("r", encoding="utf-8") as f_in, \
         simple_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)

        fieldnames = ["image", "product_ocr", "unit", "price_brl", "price_raw"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total = 0
        gravadas = 0

        for row in reader:
            total += 1

            price_brl = row.get("price_brl", "").strip()

            if price_brl == "":
                continue

            writer.writerow(
                {
                    "image": row.get("image", ""),
                    "product_ocr": row.get("product_ocr", ""),
                    "unit": row.get("unit", ""),
                    "price_brl": price_brl,
                    "price_raw": row.get("price_raw", ""),
                }
            )
            gravadas += 1

    print(f"Linhas lidas no original : {total}")
    print(f"Linhas gravadas no simples: {gravadas}")
    print(f"Arquivo final: {simple_csv}")


if __name__ == "__main__":
    main()
