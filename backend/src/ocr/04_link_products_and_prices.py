from pathlib import Path
import csv
import re


PRICE_RE = re.compile(
    r"(?:R\$)\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})|([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})"
)

UNIT_WORDS = [
    "kg",
    "quilo",
    "un",
    "unid",
    "unidade",
    "pct",
    "pacote",
    "cx",
    "caixa",
    "l",
    "lt",
    "litro",
    "g",
    "gramas",
    "ml",
]


def parse_price_brl(text: str):
    """
    Tenta extrair um preço em BRL de uma string OCR.
    Retorna (preco_float, preco_str) ou (None, None).
    """
    if not text:
        return None, None

    match = PRICE_RE.search(text)
    if not match:
        return None, None

    raw = match.group(1) or match.group(2)
    if not raw:
        return None, None

    clean = raw.replace(".", "").replace(",", ".")
    try:
        value = float(clean)
    except ValueError:
        return None, None

    return value, raw


def extract_unit(text: str):
    if not text:
        return None
    t = text.lower()
    for u in UNIT_WORDS:
        if u in t:
            return u
    return None


def to_float(s: str):
    try:
        return float(s)
    except Exception:
        return None


def build_price_columns(prices, max_gap_x=200.0):
    """
    Agrupa preços em colunas com base em cx (centro em X).
    max_gap_x: distância máxima entre centros em X para considerar mesma coluna.
    Retorna lista de dicts: {"center_x": float, "items": [price_items]}.
    """
    if not prices:
        return []

    prices_sorted = sorted(prices, key=lambda p: p["cx"])

    columns = []
    current_col = [prices_sorted[0]]

    for p in prices_sorted[1:]:
        prev = current_col[-1]
        if abs(p["cx"] - prev["cx"]) <= max_gap_x:
            current_col.append(p)
        else:
            columns.append(current_col)
            current_col = [p]

    columns.append(current_col)

    col_defs = []
    for col_items in columns:
        center_x = sum(p["cx"] for p in col_items) / len(col_items)
        col_defs.append({"center_x": center_x, "items": col_items})

    return col_defs


def main():
    backend_dir = Path(__file__).resolve().parents[2]
    SUPERMERCADO = "assai"

    crops_root = backend_dir / "data" / "results" / SUPERMERCADO / "yolo11" / "crops"
    ocr_csv = crops_root / "crops_ocr.csv"
    if not ocr_csv.exists():
        raise FileNotFoundError(f"Arquivo de OCR não encontrado: {ocr_csv}")

    output_csv = backend_dir / "data" / "results" / SUPERMERCADO / "yolo11" / "products_prices.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    print(f"Supermercado: {SUPERMERCADO}")
    print(f"Lendo OCR de: {ocr_csv}")
    print(f"Salvando associações em: {output_csv}")

    by_image = {}

    with ocr_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            image_name = row["orig_image"]
            by_image.setdefault(image_name, []).append(row)

    num_products = 0
    num_matched = 0

    with output_csv.open("w", newline="", encoding="utf-8") as f_out:
        fieldnames = [
            "image",
            "product_crop",
            "product_ocr",
            "product_conf",
            "product_x1",
            "product_y1",
            "product_x2",
            "product_y2",
            "price_crop",
            "price_ocr",
            "price_conf",
            "price_x1",
            "price_y1",
            "price_x2",
            "price_y2",
            "price_brl",
            "price_raw",
            "unit",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for image_name, rows in by_image.items():
            products = []
            prices = []

            for r in rows:
                cls = r["class_name"]
                x1 = to_float(r["x1"])
                y1 = to_float(r["y1"])
                x2 = to_float(r["x2"])
                y2 = to_float(r["y2"])
                if x1 is None or y1 is None or x2 is None or y2 is None:
                    continue

                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

                item = {
                    "row": r,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "cx": cx,
                    "cy": cy,
                }

                if cls == "product_text":
                    products.append(item)
                elif cls == "price":
                    prices.append(item)

            if not products or not prices:
                continue

            price_columns = build_price_columns(prices, max_gap_x=200.0)

            for p in products:
                num_products += 1
                p_row = p["row"]

                if price_columns:
                    best_col = min(
                        price_columns,
                        key=lambda col: abs(col["center_x"] - p["cx"]),
                    )
                    col_prices = best_col["items"]
                else:
                    col_prices = prices

                tol_up = 20.0
                cand = [pr for pr in col_prices if pr["cy"] >= p["cy"] - tol_up]

                if cand:
                    best = min(cand, key=lambda pr: abs(pr["cy"] - p["cy"]))
                else:
                    best = min(col_prices, key=lambda pr: abs(pr["cy"] - p["cy"]))

                price_row = best["row"]

                price_text = price_row.get("ocr_text", "") or ""
                product_text = p_row.get("ocr_text", "") or ""

                price_value, price_raw = parse_price_brl(price_text)
                unit = extract_unit(product_text + " " + price_text)

                writer.writerow(
                    {
                        "image": image_name,
                            "product_crop": p_row["crop_filename"],
                            "product_ocr": product_text,
                            "product_conf": p_row.get("conf", ""),
                            "product_x1": p["x1"],
                            "product_y1": p["y1"],
                            "product_x2": p["x2"],
                            "product_y2": p["y2"],
                            "price_crop": price_row["crop_filename"],
                            "price_ocr": price_text,
                            "price_conf": price_row.get("conf", ""),
                            "price_x1": best["x1"],
                            "price_y1": best["y1"],
                            "price_x2": best["x2"],
                            "price_y2": best["y2"],
                            "price_brl": f"{price_value:.2f}" if price_value is not None else "",
                            "price_raw": price_raw or "",
                            "unit": unit or "",
                    }
                )
                num_matched += 1

    print()
    print(f"Total de produtos encontrados: {num_products}")
    print(f"Produtos associados a algum preço: {num_matched}")
    print(f"CSV final: {output_csv}")


if __name__ == "__main__":
    main()
