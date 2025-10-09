# backend/ocr/pdf_brasil_atacarejo_to_csv.py
from pathlib import Path
from datetime import datetime
import argparse
import re
from typing import List, Optional

import pandas as pd
from PyPDF2 import PdfReader

# preço BR com/sem R$, milhares com ponto e centavos com vírgula
PRICE_RE = re.compile(r"(?:R\$?\s*)?\d{1,3}(?:\.\d{3})*,\d{2}")

# ruídos comuns que NÃO são nome de produto
EXCLUDE_PAT = re.compile(
    r"(OFERTAS VÁLIDAS|MINISTÉRIO DA SAÚDE|APRECIE COM MODERAÇÃO|"
    r"SÃO PROIBIDAS|VENDA A MENORES|ESTOQUES|IMAGENS ILUSTRATIVAS|"
    r"BRUMADO|ATACAREJO|VALIDA|VÁLIDA|DIAS|SEMANA|"
    r"^kg$|^cada$|^un$|^l$|^litro$|^\d+\s*(un|kg|l)$)",
    flags=re.IGNORECASE
)

# pistas de "complemento" de produto (unidade/volume/pack)
UNIT_HINT = re.compile(
    r"(\b\d+\s?(kg|g|l|ml|un|pct|und|sach(e|ê)|cx|caixa)\b|\b\d+x\d+\b|kg\b|l\b|ml\b|g\b)",
    flags=re.IGNORECASE
)

def brl_to_float(texto: str) -> float:
    cleaned = re.sub(r"[^\d,]", "", texto).replace(".", "").replace(",", ".")
    return float(cleaned)

def limpar_linha(l: str) -> str:
    l = l.strip()
    # "0,99Molho" -> "0,99 Molho"
    l = re.sub(r"(?<=\d),(?=\d{2})(?=[A-Za-zÁ-ú])", ", ", l)
    l = re.sub(r"(?<=[\d,])(?=[A-Za-zÁ-ú])", " ", l)
    l = re.sub(r"\s+", " ", l)
    return l.strip(" :-–—•|.,\t")

def is_name_candidate(txt: str) -> bool:
    if not txt or len(txt) < 3:
        return False
    if PRICE_RE.fullmatch(txt):
        return False
    if EXCLUDE_PAT.search(txt):
        return False
    # precisa ter pelo menos uma letra
    return bool(re.search(r"[A-Za-zÁ-ú]", txt))

def montar_nome_completo(lines: List[str], idx: int, atual: str, match) -> Optional[str]:
    """
    Nome completo = [linhas de cima que parecem título/marca] + [texto à esquerda do preço na mesma linha] + [linhas de baixo com unidade/complemento]
    """
    partes: List[str] = []

    # 1) à esquerda do preço na mesma linha
    left = limpar_linha(atual[: match.start()])
    if is_name_candidate(left):
        partes.append(left)

    # 2) olhar 1–3 linhas ACIMA (marca / parte 1 do nome)
    acima: List[str] = []
    for j in range(1, 4):
        k = idx - j
        if k < 0:
            break
        cand = limpar_linha(lines[k])
        if not is_name_candidate(cand):
            # se topar com linha vazia/ruído, para de subir
            if cand == "" or EXCLUDE_PAT.search(cand):
                break
            continue
        # se a linha acima também parecer parte do nome, empilha (vamos inverter depois)
        acima.append(cand)
        # heurística: se a linha tem muita "cara" de título (tudo maiúsculo/curto), podemos olhar mais uma acima
        if len(cand) > 80:
            break
    if acima:
        # as de cima ficam antes; invertidas para manter ordem natural
        partes = list(reversed(acima)) + partes

    # 3) olhar 0–2 linhas ABAIXO (unidade/volume/complemento)
    abaixo: List[str] = []
    for j in range(1, 3):
        k = idx + j
        if k >= len(lines):
            break
        cand = limpar_linha(lines[k])
        if not cand:
            break
        if PRICE_RE.search(cand):
            break
        # aceita se parecer complemento (unidade/volume) OU nome legítimo
        if UNIT_HINT.search(cand) or is_name_candidate(cand):
            # evita grudar textos longos demais
            if len(cand) <= 80 and not EXCLUDE_PAT.search(cand):
                abaixo.append(cand)
        else:
            # encontrou algo que não ajuda → para
            break
    if abaixo:
        partes = partes + abaixo

    # montar final
    nome = " ".join(p for p in partes if p).strip()
    # pós-limpeza simples
    nome = re.sub(r"\s+", " ", nome)
    # evitar nomes minúsculos demais
    if not is_name_candidate(nome):
        return None
    return nome

def extrair_itens(pdf_path: Path) -> pd.DataFrame:
    reader = PdfReader(str(pdf_path))
    rows = []
    for pnum, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        raw_lines = [l for l in text.splitlines() if l and l.strip()]
        lines = [limpar_linha(l) for l in raw_lines if limpar_linha(l)]

        for i, line in enumerate(lines):
            for m in PRICE_RE.finditer(line):
                price_txt = m.group(0)
                name = montar_nome_completo(lines, i, line, m)
                if not name:
                    # fallback: tenta só a linha de cima imediata
                    if i - 1 >= 0 and is_name_candidate(lines[i - 1]):
                        name = lines[i - 1]
                    else:
                        continue
                try:
                    price_val = brl_to_float(price_txt)
                except Exception:
                    continue

                rows.append({
                    "page": pnum,
                    "product_name_raw": name,
                    "price_text": price_txt,
                    "price_value": price_val,
                    "line_raw": line,
                })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["product_name_norm"] = (
            df["product_name_raw"]
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .str.upper()
        )
    return df

def main():
    ap = argparse.ArgumentParser(description="Extrai produto+preço do PDF e salva em CSV (nome completo).")
    ap.add_argument("--pdf", type=str, default="", help="Caminho do PDF. Se vazio, pega o mais recente na pasta padrão.")
    ap.add_argument("--base-dir", type=str, default="backend/data/folhetos/brasil_atacarejo",
                    help="Pasta padrão onde ficam os PDFs (caso --pdf não seja passado).")
    args = ap.parse_args()

    if args.pdf:
        pdf_path = Path(args.pdf)
    else:
        base = Path(args.base_dir)
        pdfs = sorted(base.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not pdfs:
            raise SystemExit(f"Nenhum PDF encontrado em {base.resolve()}")
        pdf_path = pdfs[0]

    if not pdf_path.exists():
        raise SystemExit(f"PDF não encontrado: {pdf_path}")

    print(f"[INFO] Lendo: {pdf_path.resolve()}")
    df = extrair_itens(pdf_path)
    if df.empty:
        print("Nenhum item encontrado no TEXTO do PDF. Se o folheto for imagem (sem texto embutido), vamos para OCR.")
        return

    out_dir = pdf_path.parent
    out_csv = out_dir / f"extracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[OK] {len(df)} itens extraídos. CSV salvo em:\n{out_csv.resolve()}")
    print("\nAmostra:")
    cols = ["page", "product_name_norm", "price_text", "price_value"]
    print(df[cols].head(12).to_string(index=False))

if __name__ == "__main__":
    main()
