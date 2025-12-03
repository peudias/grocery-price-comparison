from __future__ import annotations
from pathlib import Path
import csv
import re
from collections import defaultdict
from itertools import cycle

import numpy as np
import matplotlib
matplotlib.use("Agg")  # backend sem GUI, só para salvar PNG
import matplotlib.pyplot as plt


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def slugify(text: str) -> str:
    """
    Transforma o nome do produto/categoria em algo seguro para nome de arquivo.
    Ex.: 'ACEM/PA/PEITO BOVINO...' -> 'ACEM_PA_PEITO_BOVINO'
    """
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "ITEM"


def parse_period_key(period_start: str, period_end: str):
    """
    Converte 'dd.mm' em uma chave ordenável (mês, dia).
    Não temos ano aqui, então serve só para ordenar.
    """
    try:
        d1, m1 = period_start.split(".")
        d1 = int(d1)
        m1 = int(m1)
    except Exception:
        # fallback: ordena por string mesmo
        return (999, 999, period_start, period_end)

    return (m1, d1, period_start, period_end)


def get_category(prod: str) -> str:
    """
    Define uma 'categoria' genérica do produto.
    Usa a primeira palavra (antes de espaço ou '/'):
    - 'ACEM/PA/PEITO ...' -> 'ACEM'
    - 'ARROZ PARBOILIZADO ...' -> 'ARROZ'
    - 'BATATA CONGELADA ...' -> 'BATATA'
    """
    return prod.split()[0].split("/")[0].strip()


# Cores fixas por filial (fallback se aparecer filial nova)
FIXED_BRANCH_COLORS = {
    "CAMPINA GRANDE": "#1f77b4",        # azul
    "JOÃO PESSOA": "#2ca02c",           # verde
    "JUAZEIRO DO NORTE": "#d62728",     # vermelho
    "BRUMADO": "#7f7f7f",               # cinza
    "VITÓRIA DA CONQUISTA": "#9467bd",  # roxo
}


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------
def main():
    backend_dir = Path(__file__).resolve().parents[2]
    base_results = backend_dir / "data" / "results" / "yolo11"

    # Entrada: arquivo gerado pelo 09_filter_products_for_report.py
    in_dir = base_results / "filter_products_for_report"
    input_csv = in_dir / "report_product_branch_period.csv"

    if not input_csv.exists():
        raise FileNotFoundError(f"Não encontrei o CSV de entrada: {input_csv}")

    # Saídas:
    summary_csv = in_dir / "report_product_branch_summary.csv"
    plots_root = in_dir / "plots"
    plots_root.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------------
    # 1) LER DADOS E ORGANIZAR POR PRODUTO
    # ---------------------------------------------------------------------
    product_rows: dict[str, list[dict]] = defaultdict(list)

    with input_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prod = (row.get("product_norm") or "").strip()
            branch = (row.get("branch") or "").strip()
            ps = (row.get("period_start") or "").strip()
            pe = (row.get("period_end") or "").strip()
            price_str = (row.get("price_mean") or "").strip()

            if not prod or not branch or not ps or not pe or not price_str:
                continue

            try:
                price = float(price_str.replace(",", "."))
            except Exception:
                continue

            product_rows[prod].append(
                {
                    "branch": branch,
                    "period_start": ps,
                    "period_end": pe,
                    "price_mean": price,
                }
            )

    print(f"[INFO] Produtos encontrados no report: {len(product_rows)}")

    # ---------------------------------------------------------------------
    # 2) RESUMO POR PRODUTO+FILIAL (como antes)
    # ---------------------------------------------------------------------
    stats: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"num_periods": 0, "num_vezes_mais_barata": 0, "soma_precos": 0.0}
    )
    product_period_branch_prices: dict[
        tuple[str, str, str], list[tuple[str, float]]
    ] = defaultdict(list)

    for prod, rows in product_rows.items():
        for r in rows:
            branch = r["branch"]
            ps = r["period_start"]
            pe = r["period_end"]
            price = r["price_mean"]

            key_pb = (prod, branch)
            stats[key_pb]["num_periods"] += 1
            stats[key_pb]["soma_precos"] += price

            key_pp = (prod, ps, pe)
            product_period_branch_prices[key_pp].append((branch, price))

    # para cada (produto, período), descobrir a filial mais barata
    for (prod, ps, pe), lst in product_period_branch_prices.items():
        if not lst:
            continue
        min_price = min(p for _, p in lst)
        for branch, price in lst:
            if abs(price - min_price) < 1e-9:  # trata empates
                stats[(prod, branch)]["num_vezes_mais_barata"] += 1

    # calcular média de preço
    for (prod, branch), d in stats.items():
        if d["num_periods"] > 0:
            d["media_preco"] = d["soma_precos"] / d["num_periods"]
        else:
            d["media_preco"] = 0.0

    # salvar resumo
    with summary_csv.open("w", newline="", encoding="utf-8") as f_out:
        fieldnames = [
            "product_norm",
            "branch",
            "num_periods",
            "num_vezes_mais_barata",
            "media_preco",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for (prod, branch), d in sorted(
            stats.items(), key=lambda x: (x[0][0], x[1]["media_preco"])
        ):
            writer.writerow(
                {
                    "product_norm": prod,
                    "branch": branch,
                    "num_periods": d["num_periods"],
                    "num_vezes_mais_barata": d["num_vezes_mais_barata"],
                    "media_preco": f"{d['media_preco']:.2f}",
                }
            )

    print(f"[OK] Resumo de comparação entre filiais salvo em: {summary_csv}")

    # ---------------------------------------------------------------------
    # 3) AGRUPAR POR CATEGORIA (ACEM, ALCATRA, ARROZ, BATATA, etc.)
    #    E AGREGAR POR CATEGORIA+FILIAL+PERÍODO
    # ---------------------------------------------------------------------
    categories: dict[str, list[str]] = defaultdict(list)
    for prod in product_rows.keys():
        cat = get_category(prod)
        categories[cat].append(prod)

    category_branch_period: dict[
        tuple[str, str, str, str], list[float]
    ] = defaultdict(list)

    for prod, rows in product_rows.items():
        cat = get_category(prod)
        for r in rows:
            key = (cat, r["branch"], r["period_start"], r["period_end"])
            category_branch_period[key].append(r["price_mean"])

    # ---------------------------------------------------------------------
    # 4) GERAR GRÁFICOS POR CATEGORIA (FOCO EM DIFERENÇA ENTRE FILIAIS)
    # ---------------------------------------------------------------------
    for category, prods in sorted(categories.items()):
        print(f"\n[INFO] Plotando categoria: {category}")

        # períodos e filiais presentes nesta categoria
        all_periods = set()
        all_branches = set()
        for (cat, branch, ps, pe), prices in category_branch_period.items():
            if cat != category:
                continue
            all_periods.add((ps, pe))
            all_branches.add(branch)

        if not all_periods or not all_branches:
            continue

        periods = sorted(all_periods, key=lambda x: parse_period_key(x[0], x[1]))
        period_labels = [f"{ps}-{pe}" for ps, pe in periods]
        n_periods = len(periods)
        all_branches = sorted(all_branches)

        # cores fixas por filial
        default_cycle = cycle(plt.rcParams["axes.prop_cycle"].by_key()["color"])
        branch_colors = {}
        for b in all_branches:
            if b in FIXED_BRANCH_COLORS:
                branch_colors[b] = FIXED_BRANCH_COLORS[b]
            else:
                branch_colors[b] = next(default_cycle)

        plt.figure(figsize=(14, 6))

        # -----------------------------------------------------------------
        # 4.1 SÉRIE MÉDIA POR CATEGORIA+FILIAL (UMA LINHA POR FILIAL)
        # -----------------------------------------------------------------
        branch_series: dict[str, list[float]] = {
            b: [np.nan] * n_periods for b in all_branches
        }

        for branch in all_branches:
            for idx, (ps, pe) in enumerate(periods):
                prices_here = category_branch_period.get(
                    (category, branch, ps, pe), []
                )
                if prices_here:
                    mean_p = float(sum(prices_here) / len(prices_here))
                    branch_series[branch][idx] = mean_p
                else:
                    branch_series[branch][idx] = np.nan

            serie = branch_series[branch]
            if all(np.isnan(v) for v in serie):
                continue

            plt.plot(
                period_labels,
                serie,
                marker="o",
                linestyle="-",
                color=branch_colors[branch],
                label=branch,  # legenda simples: só o nome da filial
                alpha=0.9,
            )

        # -----------------------------------------------------------------
        # 4.2 DESTACAR O MENOR PREÇO EM CADA PERÍODO (CÍRCULO DOURADO)
        # -----------------------------------------------------------------
        for idx, (ps, pe) in enumerate(periods):
            best_price = None
            for branch in all_branches:
                val = branch_series[branch][idx]
                if np.isnan(val):
                    continue
                if best_price is None or val < best_price - 1e-9:
                    best_price = val

            if best_price is None:
                continue

            # marcar todas as filiais empatadas no menor preço
            for branch in all_branches:
                val = branch_series[branch][idx]
                if np.isnan(val):
                    continue
                if abs(val - best_price) < 1e-9:
                    plt.scatter(
                        period_labels[idx],
                        val,
                        s=140,
                        facecolors="none",
                        edgecolors="gold",
                        linewidths=2,
                        zorder=5,
                    )

        # -----------------------------------------------------------------
        # 4.3 INDICADOR DE TENDÊNCIA POR FILIAL (↗ ↘ →)
        # -----------------------------------------------------------------
        trend_lines = []
        for branch in all_branches:
            serie = branch_series[branch]
            vals = [(i, v) for i, v in enumerate(serie) if not np.isnan(v)]
            if len(vals) < 2:
                continue
            i0, v0 = vals[0]
            i1, v1 = vals[-1]
            delta = v1 - v0
            if delta > 0.05:
                arrow = "↗"
            elif delta < -0.05:
                arrow = "↘"
            else:
                arrow = "→"
            trend_lines.append(f"{branch}: {arrow} {delta:+.2f} R$")

        if trend_lines:
            text = "Tendência (1º → último período):\n" + "\n".join(trend_lines)
            plt.gcf().text(
                0.01,
                0.97,
                text,
                fontsize=8,
                va="top",
                ha="left",
            )

        # -----------------------------------------------------------------
        # 4.4 LABELS: HISTÓRICO, ÚLTIMO PERÍODO, COMPRA, ETC.
        # -----------------------------------------------------------------
        # todos os valores da categoria (qualquer filial/período)
        all_values = [
            v
            for branch in all_branches
            for v in branch_series[branch]
            if not np.isnan(v)
        ]
        hist_min_label = "Mínimo histórico: sem dados"
        hist_max_label = "Máximo histórico: sem dados"
        hist_mean_label = "Média histórica: sem dados"
        last_label = "Mínimo atual: sem dados"
        compra_label = "Momento de compra: sem avaliação"
        hist_comp_label = "Comparação atual x mínimo histórico: sem avaliação"
        economia_label = "Economia máxima atual: sem dados"

        hist_min = None
        hist_mean = None

        if all_values:
            # mínimo histórico
            hist_min = min(all_values)
            hist_min_branches = sorted(
                {
                    branch
                    for branch in all_branches
                    for v in branch_series[branch]
                    if not np.isnan(v) and abs(v - hist_min) < 1e-9
                }
            )
            hist_min_label = (
                f"Mínimo histórico: R$ {hist_min:.2f} "
                f"({', '.join(hist_min_branches)})"
            )

            # máximo histórico
            hist_max = max(all_values)
            hist_max_branches = sorted(
                {
                    branch
                    for branch in all_branches
                    for v in branch_series[branch]
                    if not np.isnan(v) and abs(v - hist_max) < 1e-9
                }
            )
            hist_max_label = (
                f"Máximo histórico: R$ {hist_max:.2f} "
                f"({', '.join(hist_max_branches)})"
            )

            # média histórica (todas as filiais / períodos)
            hist_mean = float(sum(all_values) / len(all_values))
            hist_mean_label = f"Média histórica (todas as filiais): R$ {hist_mean:.2f}"

        # mínimo no último período (entre as filiais)
        last_idx = n_periods - 1
        last_vals = [
            (branch, branch_series[branch][last_idx])
            for branch in all_branches
            if not np.isnan(branch_series[branch][last_idx])
        ]

        last_min_val = None
        if last_vals:
            last_min_val = min(v for _, v in last_vals)
            last_max_val = max(v for _, v in last_vals)
            last_min_branches = sorted(
                [b for b, v in last_vals if abs(v - last_min_val) < 1e-9]
            )
            last_max_branches = sorted(
                [b for b, v in last_vals if abs(v - last_max_val) < 1e-9]
            )
            last_label = (
                f"Mínimo atual: R$ {last_min_val:.2f} "
                f"({', '.join(last_min_branches)})"
            )

            # economia máxima atual entre filiais
            economia = last_max_val - last_min_val
            economia_label = (
                "Economia máxima atual: "
                f"R$ {economia:.2f} (de {', '.join(last_min_branches)} "
                f"vs {', '.join(last_max_branches)})"
            )

        # avaliação se "compensa comprar agora" (média x preço atual mínimo)
        if hist_mean is not None and last_min_val is not None and hist_mean > 0:
            diff = last_min_val - hist_mean
            diff_pct = diff / hist_mean  # diferença relativa

            if diff_pct <= -0.03:
                compra_label = (
                    f"Comparação atual x média: {diff:+.2f} R$ "
                    f"({diff_pct*100:+.1f}%) → PREÇO ABAIXO da média "
                    f"(bom momento para comprar)."
                )
            elif diff_pct >= 0.03:
                compra_label = (
                    f"Comparação atual x média: {diff:+.2f} R$ "
                    f"({diff_pct*100:+.1f}%) → PREÇO ACIMA da média "
                    f"(menos vantajoso)."
                )
            else:
                compra_label = (
                    f"Comparação atual x média: {diff:+.2f} R$ "
                    f"({diff_pct*100:+.1f}%) → PREÇO PRÓXIMO da média."
                )

        # comparação preço atual mínimo x mínimo histórico
        if hist_min is not None and last_min_val is not None and hist_min > 0:
            diff_hist = last_min_val - hist_min
            diff_hist_pct = diff_hist / hist_min

            if abs(diff_hist_pct) < 0.01:
                hist_comp_label = (
                    "Comparação atual x mínimo histórico: "
                    "preço praticamente igual ao melhor histórico."
                )
            elif diff_hist_pct < 0:
                hist_comp_label = (
                    "Comparação atual x mínimo histórico: "
                    f"{diff_hist:+.2f} R$ ({diff_hist_pct*100:+.1f}%) "
                    "→ NOVO melhor preço histórico!"
                )
            else:
                hist_comp_label = (
                    "Comparação atual x mínimo histórico: "
                    f"{diff_hist:+.2f} R$ ({diff_hist_pct*100:+.1f}%) "
                    "acima do melhor histórico."
                )

        # -----------------------------------------------------------------
        # 4.6 POSICIONAR TEXTOS EXTRAS NO TOPO DIREITO
        # -----------------------------------------------------------------
        extra_text = (
            hist_min_label
            + "\n"
            + hist_max_label
            + "\n"
            + hist_mean_label
            + "\n"
            + last_label
            + "\n"
            + economia_label
            + "\n"
            + compra_label
            + "\n"
            + hist_comp_label
        )
        plt.gcf().text(
            0.35,
            0.93,
            extra_text,
            fontsize=8,
            va="top",
            ha="left",
        )

        # -----------------------------------------------------------------
        # 4.7 AJUSTES VISUAIS FINAIS
        # -----------------------------------------------------------------
        plt.title(f"{category} — Preço médio por filial (categoria agregada)")
        plt.xlabel("Período (início–fim)")
        plt.ylabel("Preço médio (R$)")
        plt.xticks(rotation=45, ha="right")

        plt.legend(
            fontsize=8,
            ncol=1 if len(all_branches) <= 4 else 2,
            loc="upper right",
        )

        # deixa espaço em cima para os textos
        plt.tight_layout(rect=[0, 0, 1, 0.72])

        # -----------------------------------------------------------------
        # 4.8 SALVAR EM SUBPASTA POR CATEGORIA
        # -----------------------------------------------------------------
        cat_slug = slugify(category)
        category_dir = plots_root / cat_slug
        category_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{cat_slug}.png"
        out_path = category_dir / filename
        plt.savefig(out_path, dpi=160)
        plt.close()

        print(f"[OK] Gráfico salvo para categoria '{category}': {out_path}")

    print("\n[FINALIZADO] Comparações e gráficos gerados com sucesso.")


if __name__ == "__main__":
    main()
