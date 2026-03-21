from pathlib import Path
import csv
import re


# regex para formatos diferentes
PRICE_FULL_RE = re.compile(r"(\d{1,4}[.,]\d{2})")   # 12,34  /  1234.56
PRICE_ONE_DEC_RE = re.compile(r"(\d{1,4}[.,]\d)")   # 8,0   /  3.5
PRICE_INT_RE = re.compile(r"(\d{1,4})")             # 58    / 298


def parse_price(text: str):
    """
    Recebe o texto bruto do OCR (price_ocr)
    Retorna (price_brl: float | None, price_raw_normalizado: str)

    Regras:
    - 12,34  -> 12,34
    - 8,0    -> 8,00
    - 298,   -> 298,00
    - 58     -> 58,00
    - 9,0.   -> 9,00
    - 0,     -> 0,00
    """
    if text is None:
        return None, ""

    original = text.strip()
    if not original:
        return None, ""

    s = re.sub(r"[^\d,\.]", "", original)

    s = s.replace(".", ",")

    m = PRICE_FULL_RE.search(s)
    if m:
        val = m.group(1)
        norm = val.replace(".", ",")
    else:
        m = PRICE_ONE_DEC_RE.search(s)
        if m:
            val = m.group(1)
            int_part, dec_part = val.replace(".", ",").split(",")
            dec_part = (dec_part + "0")[:2]
            norm = f"{int_part},{dec_part}"
        else:
            m = PRICE_INT_RE.search(s)
            if m:
                int_part = m.group(1)
                norm = f"{int_part},00"
            else:
                return None, original

    try:
        price_brl = float(norm.replace(",", "."))
    except ValueError:
        return None, original

    return price_brl, norm


def main():
    backend_dir = Path(__file__).resolve().parents[2]
    SUPERMERCADO = "assai"

    base_results = backend_dir / "data" / "results" / SUPERMERCADO / "yolo11"
    input_csv = base_results / "products_prices.csv"
    output_csv = base_results / "products_prices_fixed.csv"

    if not input_csv.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {input_csv}")

    print(f"Supermercado: {SUPERMERCADO}")
    print(f"Lendo preços de: {input_csv}")
    print(f"Salvando CSV corrigido em: {output_csv}")

    with input_csv.open("r", encoding="utf-8") as f_in, \
         output_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total = 0
        com_preco = 0

        for row in reader:
            total += 1

            price_ocr = row.get("price_ocr", "")
            price_brl, price_raw_norm = parse_price(price_ocr)

            if price_raw_norm:
                row["price_raw"] = price_raw_norm
            else:
                row["price_raw"] = price_ocr or ""

            if price_brl is not None:
                row["price_brl"] = f"{price_brl:.2f}"
                com_preco += 1
            else:
                row["price_brl"] = row.get("price_brl", "")

            writer.writerow(row)

    print(f"Linhas processadas: {total}")
    print(f"Linhas com preço numérico: {com_preco}")
    print(f"Arquivo gerado: {output_csv}")


if __name__ == "__main__":
    main()
