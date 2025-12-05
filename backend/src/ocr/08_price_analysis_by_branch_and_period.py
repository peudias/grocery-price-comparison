from __future__ import annotations
from pathlib import Path
import csv
from collections import defaultdict


def to_float_safe(s: str):
    try:
        return float(s)
    except Exception:
        return None


def clean_product_name(text: str) -> str:
    """
    Versão simples de normalização de nome de produto.
    Você pode melhorar isso depois (tirar acentos, padronizar kg/L, etc.).
    """
    if text is None:
        return ""
    return " ".join(text.strip().upper().split())


def main():
    backend_dir = Path(__file__).resolve().parents[2]
    base_results = backend_dir / "data" / "results" / "yolo11"

    input_csv = base_results / "products_prices_enriched.csv"
    if not input_csv.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {input_csv}")

    print(f"Lendo dados enriquecidos de: {input_csv}")

    branch_period_stats_csv = base_results / "analysis_branch_period_stats.csv"
    product_branch_period_csv = base_results / "analysis_product_branch_period.csv"
    product_week_comparison_csv = base_results / "analysis_product_week_branch_comparison.csv"

    rows = []
    with input_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            price = to_float_safe(row.get("price_brl", ""))
            if price is None:
                continue

            row["price_brl_float"] = price
            row["branch"] = row.get("branch", "").strip()
            row["period_start"] = row.get("period_start", "").strip()
            row["period_end"] = row.get("period_end", "").strip()
            row["product_norm"] = clean_product_name(row.get("product_ocr", ""))

            rows.append(row)

    print(f"Linhas com preço numérico: {len(rows)}")

    # ------------------------------------------------------------------
    # 1) Estatísticas gerais por filial + período (histórico por cidade)
    # ------------------------------------------------------------------
    branch_period_stats = defaultdict(list)

    for r in rows:
        key = (r["branch"], r["period_start"], r["period_end"])
        branch_period_stats[key].append(r["price_brl_float"])

    with branch_period_stats_csv.open("w", newline="", encoding="utf-8") as f_out:
        fieldnames = [
            "branch",
            "period_start",
            "period_end",
            "num_items",
            "price_mean",
            "price_min",
            "price_max",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for (branch, ps, pe), prices in sorted(branch_period_stats.items()):
            if not branch:
                continue
            n = len(prices)
            mean_p = sum(prices) / n
            min_p = min(prices)
            max_p = max(prices)
            writer.writerow(
                {
                    "branch": branch,
                    "period_start": ps,
                    "period_end": pe,
                    "num_items": n,
                    "price_mean": f"{mean_p:.2f}",
                    "price_min": f"{min_p:.2f}",
                    "price_max": f"{max_p:.2f}",
                }
            )

    print(f"Estatísticas por filial+período salvas em: {branch_period_stats_csv}")

    # ------------------------------------------------------------------
    # 2) Estatísticas por produto + filial + período
    #    -> histórico de um produto em uma filial ao longo do tempo
    # ------------------------------------------------------------------
    product_branch_period = defaultdict(list)

    for r in rows:
        key = (r["product_norm"], r["branch"], r["period_start"], r["period_end"])
        product_branch_period[key].append(r["price_brl_float"])

    with product_branch_period_csv.open("w", newline="", encoding="utf-8") as f_out:
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

        for (prod, branch, ps, pe), prices in sorted(product_branch_period.items()):
            if not branch or not prod:
                continue
            n = len(prices)
            mean_p = sum(prices) / n
            min_p = min(prices)
            max_p = max(prices)
            writer.writerow(
                {
                    "product_norm": prod,
                    "branch": branch,
                    "period_start": ps,
                    "period_end": pe,
                    "num_occurrences": n,
                    "price_mean": f"{mean_p:.2f}",
                    "price_min": f"{min_p:.2f}",
                    "price_max": f"{max_p:.2f}",
                }
            )

    print(f"Estatísticas por produto+filial+período salvas em: {product_branch_period_csv}")

    # ------------------------------------------------------------------
    # 3) Comparação entre filiais na mesma semana:
    #    para cada produto + período, descobrir qual filial está mais barata
    # ------------------------------------------------------------------
    # chave: (product_norm, period_start, period_end) -> lista de (branch, price_mean)
    product_period_branch_prices = defaultdict(list)

    for (prod, branch, ps, pe), prices in product_branch_period.items():
        if not branch or not prod:
            continue
        mean_p = sum(prices) / len(prices)
        product_period_branch_prices[(prod, ps, pe)].append((branch, mean_p))

    with product_week_comparison_csv.open("w", newline="", encoding="utf-8") as f_out:
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
                continue  # só faz sentido comparar se houver pelo menos 2 filiais

            # encontra a filial com menor preço médio
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

    print(f"Comparação entre filiais por produto+período salva em: {product_week_comparison_csv}")
    print("Análises concluídas.")


if __name__ == "__main__":
    main()
