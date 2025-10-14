# backend/ocr/pdf_brasil_atacarejo_to_csv.py
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple
import argparse
import re
import sys
import pandas as pd
from PyPDF2 import PdfReader

# --- Config locais ---
FOLDER_PDFS = Path("backend/data/folhetos/brasil_atacarejo")
FOLDER_CSV  = Path("backend/data/csv/brasil_atacarejo")

# Regex preço em PT-BR (com/sem R$; milhar com ponto; centavos com vírgula)
PRICE_RE = re.compile(r"(?:R\$?\s*)?\d{1,3}(?:\.\d{3})*,\d{2}")

# nova: unidades comuns como linhas isoladas
UNIT_SOLO_PAT = re.compile(r"^\s*(kg|cada|un|l|lt|ml|g|unid\.?)\s*$", re.IGNORECASE)

# palavras/tokens típicos de atributo/corte/unidade
ATTR_TOKENS = set("""
kg cada un l lt ml g peça pedaço vacuo vácuo a de do da dos das c/ s/ sem com
ponta interior exterior dianteiro traseiro osso osso. osso, s/ c/ s/ osso
vácuo a vácuo pacote pct pct. tp tp. unid unidade unidades litro litros
""".split())


# melhore o EXCLUDE_PAT (evita grudar aviso do Ministério e banners)
EXCLUDE_PAT = re.compile(
    r"(OFERTAS V[ÁA]LIDAS|MINIST[ÉE]RIO DA SA[ÚU]DE|APRECIE COM MODERA[ÇC][ÃA]O|"
    r"S[ÃA]O PROIBIDAS|VENDA A MENORES|ESTOQUES|IMAGENS ILUSTRATIVAS|"
    r"TV SMART|PNEU|V[OÓ]LV|XXG|XG|^M\s*\d+|^G\s*\d+|^P\s*\d+|"
    r"^\s*(kg|cada|un|lt|l|ml|g)\s*$)",
    flags=re.IGNORECASE
)

# # Linhas que não são nome de produto (avisos, unidades isoladas etc.)
# EXCLUDE_PAT = re.compile(
#     r"(OFERTAS V[ÁA]LIDAS|MINIST[ÉE]RIO DA SA[ÚU]DE|APRECIE COM MODERA[ÇC][ÃA]O|"
#     r"S[ÃA]O PROIBIDAS|VENDA A MENORES|ESTOQUES|IMAGENS ILUSTRATIVAS|"
#     r"^\s*(kg|un|lt|l|ml|g|cada)\s*$|^\s*\d+\s*(un|kg|l|ml|g)\s*$)",
#     flags=re.IGNORECASE
# )

CIDADES_OK = re.compile(r"(BRUMADO|VIT[ÓO]RIA\s+DA\s+CONQUISTA)", re.IGNORECASE)

try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False


def brl_to_float(s: str) -> float:
    s = s.upper().replace("R$", "").strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def read_pdf_text_pages(pdf_path: Path) -> List[str]:
    pages: List[str] = []
    reader = PdfReader(str(pdf_path))
    for pg in reader.pages:
        try:
            txt = pg.extract_text() or ""
        except Exception:
            txt = ""
        pages.append(txt)
    return pages


def ocr_pdf_text_pages(pdf_path: Path, dpi: int = 300) -> List[str]:
    if not OCR_AVAILABLE:
        return []
    images = convert_from_path(str(pdf_path), dpi=dpi)
    texts: List[str] = []
    for im in images:
        txt = pytesseract.image_to_string(im, lang="por")
        texts.append(txt or "")
    return texts


def normalize_line(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def clean_product_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" -:•|")
    # remove unidade no começo
    s = re.sub(r"^(kg|cada|un|l|lt|ml|g)\b[\s\-:|]*", "", s, flags=re.IGNORECASE)
    # colagens "kgProduto" -> "Produto"
    s = re.sub(r"^(kg|cada)\s*", "", s, flags=re.IGNORECASE)

    # se o início for formado só por tokens curtos de atributo/unidade, remova-os
    def drop_leading_attrs(text: str) -> str:
        parts = text.split()
        k = 0
        for w in parts:
            w_norm = re.sub(r"[^\wáéíóúãõç]", "", w.lower())
            if (w_norm in ATTR_TOKENS) or re.fullmatch(r"\d+[xX/.,-]?\d*\w*", w_norm):
                k += 1
                continue
            # heurística: tokens com ≥4 letras geralmente já são "nome"
            if len(w_norm) >= 4:
                break
            # tokens curtíssimos (1–2) também são ruído na abertura
            k += 1
        return " ".join(parts[k:]).strip()

    s = drop_leading_attrs(s)

    # limpa aspas/lixo
    s = s.replace("“", "").replace("”", "").strip()
    # elimina duplicação de 'kg' no meio tipo "kg kgProduto"
    s = re.sub(r"\bkg\b\s*(?=\bkg\b)", "", s, flags=re.IGNORECASE).strip()
    return s



def looks_like_attr(line: str) -> bool:
    """True se a linha for curtinha e composta (quase) só por tokens de atributo/unidade."""
    txt = normalize_line(line)
    if not txt: 
        return True
    # linhas muito curtas tendem a ser ruído técnico
    if len(txt) <= 6:
        return True
    # unidade solo?
    if UNIT_SOLO_PAT.search(txt):
        return True
    tokens = txt.split()
    # se a maioria dos tokens forem ATTR_TOKENS ou números/medidas, considere atributo
    score_attr = 0
    for w in tokens:
        w_norm = re.sub(r"[^\wáéíóúãõç]", "", w.lower())
        if (w_norm in ATTR_TOKENS) or re.fullmatch(r"\d+[xX/.,-]?\d*\w*", w_norm):
            score_attr += 1
    return score_attr >= max(1, int(0.6 * len(tokens)))  # ≥60% de tokens "técnicos" → atributo


def parse_items_from_pages(pages: List[str]) -> List[dict]:
    """
    Estratégia por blocos:
    - cada ocorrência de preço marca o início de um novo item;
    - todas as linhas entre um preço e o próximo pertencem ao mesmo bloco;
    - dentro do bloco, ignoramos linhas claramente inúteis (unidades isoladas, avisos);
    - resultado: mais itens preservados, menos vazamento entre produtos.
    """
    items: List[dict] = []

    for page_idx, page in enumerate(pages, start=1):
        raw_lines = page.splitlines()
        lines = [normalize_line(l) for l in raw_lines if normalize_line(l)]

        # índices das linhas que contêm preço
        price_indices = []
        for i, ln in enumerate(lines):
            m = PRICE_RE.search(ln)
            if m:
                price_indices.append((i, m.group(0)))

        for k, (i_price, price_txt) in enumerate(price_indices):
            # define o bloco do item (do preço atual até o próximo preço)
            i_next = price_indices[k + 1][0] if k + 1 < len(price_indices) else len(lines)
            bloco = lines[i_price:i_next]

            # preço → float
            preco = brl_to_float(price_txt)

            # nome pode estar junto do preço
            inline_name = PRICE_RE.sub("", bloco[0]).strip()
            nome_partes: List[str] = []

            if inline_name and not EXCLUDE_PAT.search(inline_name) and not UNIT_SOLO_PAT.search(inline_name):
                nome_partes.append(inline_name)

            # linhas seguintes no mesmo bloco
            for ln in bloco[1:]:
                if not ln:
                    continue
                # se aparecer outro preço (por segurança), encerra
                if PRICE_RE.search(ln):
                    break
                # ignora banners e unidades soltas
                if EXCLUDE_PAT.search(ln) or UNIT_SOLO_PAT.search(ln):
                    continue
                nome_partes.append(ln)

            # junta e limpa
            nome = clean_product_name(" ".join(nome_partes))
            # corta textos absurdamente longos (OCR com colagem)
            if len(nome) > 180:
                nome = nome[:180].rsplit(" ", 1)[0].strip()

            if nome:
                items.append({
                    "pagina": page_idx,
                    "linha": i_price + 1,
                    "produto": nome,
                    "preco_brl": price_txt,
                    "preco": preco,
                })

    # remove duplicatas simples
    uniq = {}
    for it in items:
        key = (it["pagina"], it["produto"].lower(), it["preco_brl"])
        if key not in uniq:
            uniq[key] = it
    return list(uniq.values())






def info_from_filename(pdf_path: Path) -> Tuple[str, str]:
    """Extrai (cidade, periodo) do nome: '... - CIDADE DD.MM A DD.MM.pdf'"""
    name = pdf_path.stem
    m_city = re.search(r"-\s*([^-]+?)\s+\d{2}\.\d{2}\s+A\s+\d{2}\.\d{2}$", name)
    cidade = (m_city.group(1).strip() if m_city else "").upper()
    m_per = re.search(r"(\d{2}\.\d{2}\s+A\s+\d{2}\.\d{2})", name)
    periodo = m_per.group(1) if m_per else ""
    return (cidade, periodo)


def escolher_pdf_default() -> Path:
    pdfs = sorted(FOLDER_PDFS.glob("*.pdf"))
    # mantém apenas as cidades desejadas se possível
    pref = [p for p in pdfs if CIDADES_OK.search(p.name)]
    base = pref if pref else pdfs
    if not base:
        print("Nenhum PDF encontrado em", FOLDER_PDFS, file=sys.stderr)
        sys.exit(2)
    # mais recente por mtime
    return max(base, key=lambda p: p.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(description="Extrai itens e preços dos folhetos do Brasil Atacarejo (PDF → CSV).")
    parser.add_argument("--pdf", help="Caminho do PDF. Se omitido, pega o mais recente em backend/data/folhetos/brasil_atacarejo.")
    parser.add_argument("--outdir", default=str(FOLDER_CSV), help="Pasta de saída dos CSVs.")
    parser.add_argument("--min-itens", type=int, default=10, help="Se extrair menos que isso por texto, tenta OCR (se disponível).")
    args = parser.parse_args()

    pdf_path = Path(args.pdf) if args.pdf else escolher_pdf_default()
    if not pdf_path.exists():
        print(f"PDF não encontrado: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) Tenta por texto
    pages_txt = read_pdf_text_pages(pdf_path)
    items = parse_items_from_pages(pages_txt)

    # 2) OCR fallback
    if len(items) < args.min_itens and OCR_AVAILABLE:
        print(f"[INFO] Extração por texto retornou {len(items)} itens. Tentando OCR…")
        ocr_pages_txt = ocr_pdf_text_pages(pdf_path, dpi=300)
        items = parse_items_from_pages(ocr_pages_txt)

    # Compor DataFrame
    cidade, periodo = info_from_filename(pdf_path)
    df = pd.DataFrame(items)
    if df.empty:
        print("[AVISO] Nenhum item encontrado. Verifique o OCR/regex.", file=sys.stderr)
    df.insert(0, "cidade", cidade)
    df.insert(1, "periodo", periodo)
    df.insert(2, "fonte_pdf", str(pdf_path.resolve()))
    df.insert(3, "loja", "BRASIL ATACAREJO")
    # ordena colunas
    # cols = ["loja", "cidade", "periodo", "produto", "preco_brl", "preco", "pagina", "linha", "fonte_pdf"]
    cols = ["loja", "cidade", "periodo", "produto", "preco_brl"]
    df = df.reindex(columns=cols)

    # Salva
    safe_city = cidade.replace(" ", "_").lower() or "desconhecida"
    out_path = outdir / f"{safe_city}__{pdf_path.stem}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"[OK] {len(df)} linhas salvas em:")
    print(out_path.resolve())


if __name__ == "__main__":
    main()
