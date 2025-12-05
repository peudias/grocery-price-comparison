from __future__ import annotations
from pathlib import Path
import csv
import unicodedata
import re
from collections import defaultdict

def normalize_basic(text: str) -> str:
    """
    Normaliza levemente o nome do produto:
    - remove acentos
    - caixa alta
    - normaliza espaços em torno de barras (/)
    - colapsa espaços internos
    """
    if text is None:
        return ""
    # remove acentos
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    # caixa alta
    text = text.upper()
    # normaliza espaços em torno de barras: "ACEM/ PÁ", "ACEM /PÁ", "ACEM / PÁ" -> "ACEM/PÁ"
    text = re.sub(r"\s*/\s*", "/", text)
    # colapsa espaços
    return " ".join(text.strip().split())



def load_target_products(target_file: Path):
    """
    Lê um arquivo de texto com 1 produto por linha.
    Cada linha é interpretada como um PREFIXO do nome do produto.

    Regras:
    - Se o arquivo não existir, ele é criado vazio e NENHUM prefixo é carregado.
    - Se o arquivo existir mas estiver vazio -> usa TODOS os produtos.
    - Se tiver linhas -> só mantém produtos cujo nome normalizado começa
      com pelo menos um desses prefixos.
    """
    target_file.parent.mkdir(parents=True, exist_ok=True)

    if not target_file.exists():
        print(f"[AVISO] {target_file} não existe! Criando arquivo vazio… (TODOS os produtos serão usados)")
        target_file.touch()
        return []

    prefixes: list[str] = []
    with target_file.open("r", encoding="utf-8") as f:
        for line in f:
            name = normalize_basic(line)
            if name:
                prefixes.append(name)

    if not prefixes:
        print(f"[INFO] {target_file} está vazio → usando TODOS os produtos.")
    else:
        print(f"[INFO] Prefixos de produtos alvo carregados ({len(prefixes)}):")
        for p in prefixes:
            print(f" - {p}")

    return prefixes


def main():
    backend_dir = Path(__file__).resolve().parents[2]
    base_results = backend_dir / "data" / "results" / "yolo11"
    base_configs = backend_dir / "data" / "configs"

    # Entrada 1: CSV enriquecido (linhas brutas)
    input_csv = base_results / "products_prices_enriched.csv"

    # Entrada 2: CSV de análise já agregado (contém TODOS os períodos)
    analysis_product_branch_period_csv = base_results / "analysis_product_branch_period.csv"

    # Saídas: CSVs filtrados (em uma subpasta própria)
    out_dir = base_results / "filter_products_for_report"
    out_dir.mkdir(parents=True, exist_ok=True)

    filtered_products_csv = out_dir / "report_products_filtered.csv"
    filtered_product_branch_period_csv = out_dir / "report_product_branch_period.csv"
    filtered_product_week_comparison_csv = out_dir / "report_product_week_branch_comparison.csv"

    if not input_csv.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_csv}")

    if not analysis_product_branch_period_csv.exists():
        raise FileNotFoundError(
            f"Arquivo de análise por produto+filial+período não encontrado: "
            f"{analysis_product_branch_period_csv}"
        )

    # Arquivo com produtos (ou famílias de produtos) de interesse
    target_file = base_configs / "target_products.txt"
    target_prefixes = load_target_products(target_file)

    # -------------------------------------------------------------------------
    # 1) FILTRO NAS LINHAS BRUTAS (products_prices_enriched.csv)
    # -------------------------------------------------------------------------
    print(f"[INFO] Lendo dados brutos de: {input_csv}")

    rows = []
    with input_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # preço numérico
            price_str = row.get("price_brl", "")
            try:
                price = float(price_str)
            except Exception:
                continue  # ignora linhas sem preço numérico

            raw_product = row.get("product_ocr", "")
            product_norm = normalize_basic(raw_product)
            row["product_norm"] = product_norm
            row["price_brl_float"] = price

            # Se houver prefixos definidos em target_products.txt, filtra por prefixo
            if target_prefixes:
                if not any(product_norm.startswith(prefix) for prefix in target_prefixes):
                    continue

            rows.append(row)

    print(f"[INFO] Linhas mantidas após filtro (preço OK e produto alvo): {len(rows)}")

    # 1a) Salvar um CSV simples com essas linhas filtradas
    if rows:
        with filtered_products_csv.open("w", newline="", encoding="utf-8") as f_out:
            fieldnames = list(rows[0].keys())
            # remove coluna auxiliar float se quiser
            if "price_brl_float" in fieldnames:
                fieldnames.remove("price_brl_float")
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                r_out = dict(r)
                r_out.pop("price_brl_float", None)
                writer.writerow(r_out)

        print(f"[OK] Linhas filtradas salvas em: {filtered_products_csv}")
    else:
        print("[AVISO] Nenhuma linha após o filtro. Verifique os prefixos em target_products.txt.")
        return

    # -------------------------------------------------------------------------
    # 2) USAR analysis_product_branch_period.csv COMO BASE DO RELATÓRIO
    #        NÃO filtra períodos, apenas produtos.
    # -------------------------------------------------------------------------
    print(f"[INFO] Lendo estatísticas agregadas de: {analysis_product_branch_period_csv}")

    # Acumular linhas filtradas (por produto) para depois comparar filiais
    filtered_agg_rows = []

    with analysis_product_branch_period_csv.open("r", encoding="utf-8") as f_in, \
            filtered_product_branch_period_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)

        fieldnames = [
            "product_norm",
            "branch",
            "period_start",
            "period_end",
            "num_occurrences",
            "price_mean",
            "price_min",
            "price_max",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total_in_analysis = 0
        total_after_product_filter = 0

        for row in reader:
            total_in_analysis += 1

            # Pega o nome do produto do CSV de análise
            prod_raw = row.get("product_norm") or row.get("product") or row.get("product_name") or ""
            prod_norm = normalize_basic(prod_raw)

            # Aplica filtro de produto, se houver prefixos
            if target_prefixes:
                if not any(prod_norm.startswith(prefix) for prefix in target_prefixes):
                    continue

            branch = (row.get("branch") or "").strip()
            ps = (row.get("period_start") or "").strip()
            pe = (row.get("period_end") or "").strip()
            num_occ = row.get("num_occurrences") or row.get("n") or row.get("count") or "1"
            price_mean = row.get("price_mean") or row.get("mean_price") or ""
            price_min = row.get("price_min") or row.get("min_price") or ""
            price_max = row.get("price_max") or row.get("max_price") or ""

            if not branch or not prod_norm or not ps or not pe or not price_mean:
                # Linha incompleta, pula
                continue

            total_after_product_filter += 1

            writer.writerow(
                {
                    "product_norm": prod_norm,
                    "branch": branch,
                    "period_start": ps,
                    "period_end": pe,
                    "num_occurrences": num_occ,
                    "price_mean": price_mean,
                    "price_min": price_min,
                    "price_max": price_max,
                }
            )

            # Guarda para comparação entre filiais
            try:
                mean_val = float(price_mean)
            except Exception:
                continue

            filtered_agg_rows.append(
                (prod_norm, ps, pe, branch, mean_val)
            )

    print(f"[INFO] Linhas no analysis_product_branch_period.csv: {total_in_analysis}")
    print(f"[INFO] Linhas após filtro por produto (SEM filtrar períodos): {total_after_product_filter}")
    print(f"[OK] Estatísticas por produto+filial+período salvas em: {filtered_product_branch_period_csv}")

    # -------------------------------------------------------------------------
    # 3) Comparação entre filiais na mesma semana, apenas para esses produtos
    # -------------------------------------------------------------------------
    product_period_branch_prices: dict[tuple[str, str, str], list[tuple[str, float]]] = defaultdict(list)

    for prod_norm, ps, pe, branch, mean_val in filtered_agg_rows:
        product_period_branch_prices[(prod_norm, ps, pe)].append((branch, mean_val))

    with filtered_product_week_comparison_csv.open("w", newline="", encoding="utf-8") as f_out:
        fieldnames = [
            "product_norm",
            "period_start",
            "period_end",
            "cheapest_branch",
            "cheapest_price",
            "num_branches_compared",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for (prod, ps, pe), lst in sorted(product_period_branch_prices.items()):
            if len(lst) < 2:
                continue  # só compara se tiver pelo menos 2 filiais

            cheapest_branch, cheapest_price = min(lst, key=lambda x: x[1])
            writer.writerow(
                {
                    "product_norm": prod,
                    "period_start": ps,
                    "period_end": pe,
                    "cheapest_branch": cheapest_branch,
                    "cheapest_price": f"{cheapest_price:.2f}",
                    "num_branches_compared": len(lst),
                }
            )

    print(f"[OK] Comparação entre filiais por produto+período salva em: {filtered_product_week_comparison_csv}")
    print("[FINALIZADO] Filtro e análises para produtos selecionados concluídos.")


if __name__ == "__main__":
    main()
