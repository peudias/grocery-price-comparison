from __future__ import annotations
from pathlib import Path
import re
import csv

DEFAULT_YEAR = 2025

PATTERN = re.compile(
    r"BRASIL ATACAREJO - (.+) (\d{2}\.\d{2}) A (\d{2}\.\d{2})"
)

def parse_image_metadata(image_name: str):
    """
    Recebe algo como:
      'BRASIL ATACAREJO - BRUMADO 03.11 A 06.11_p1.png'
    Retorna:
      filial (cidade), data_inicio_str, data_fim_str

    Exemplo:
      ('BRUMADO', '03.11', '06.11')
    """
    base = image_name.rsplit("_p", 1)[0]
    m = PATTERN.match(base)
    if not m:
        return None, None, None
    city, start, end = m.groups()
    return city, start, end


def main():
    backend_dir = Path(__file__).resolve().parents[2]
    base_results = backend_dir / "data" / "results" / "yolo11"

    input_csv = base_results / "products_prices_fixed.csv"
    output_csv = base_results / "products_prices_enriched.csv"

    if not input_csv.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_csv}")

    print(f"Lendo dados de: {input_csv}")
    print(f"Gerando CSV enriquecido em: {output_csv}")

    with input_csv.open("r", encoding="utf-8") as f_in, \
         output_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames + ["branch", "period_start", "period_end"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total = 0
        sem_meta = 0

        for row in reader:
            total += 1
            image_name = row.get("image", "")

            branch, start, end = parse_image_metadata(image_name)

            if branch is None:
                sem_meta += 1
                row["branch"] = ""
                row["period_start"] = ""
                row["period_end"] = ""
            else:
                row["branch"] = branch
                row["period_start"] = start
                row["period_end"] = end

            writer.writerow(row)

    print(f"Linhas processadas: {total}")
    print(f"Linhas sem metadata de branch/período: {sem_meta}")
    print(f"Arquivo gerado: {output_csv}")


if __name__ == "__main__":
    main()
