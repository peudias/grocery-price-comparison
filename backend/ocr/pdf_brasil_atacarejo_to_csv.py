# backend/ocr/pdf_brasil_atacarejo_to_csv.py
from pathlib import Path
from datetime import datetime
import argparse
import re
from typing import List, Optional

import pandas as pd
from PyPDF2 import PdfReader

# ---------------- REGEX / CONSTANTES ----------------

# Preço BR com/sem R$, milhares com ponto e centavos com vírgula
PRICE_RE = re.compile(r"(?:R\$?\s*)?\d{1,3}(?:\.\d{3})*,\d{2}")

# Textos de vitrine/rodapé que NÃO são nome de produto
EXCLUDE_PAT = re.compile(
    r"(OFERTAS?|VÁLID[AO]S?|VALIDAS?|PROMO(Ç|C)Ã?O|LEVE\s*\d+\s*PAGUE\s*\d+|"
    r"MINISTÉRIO DA SAÚDE|APRECIE COM MODERAÇÃO|SÃO PROIBIDAS|VENDA A MENORES|"
    r"ESTOQUES?|IMAGENS ILUSTRATIVAS?|LOJA|BRASIL\s+ATACAREJO|BRUMADO|VIT[ÓO]RIA DA CONQUISTA|"
    r"SEMANA|DIAS?)",
    flags=re.IGNORECASE
)

# Palavrinhas de unidade quando aparecem como "prefixo sujo" de linha
UNIT_WORD = re.compile(r"^(?:kg|cada|un|und|unid|l|ml|g)\b", re.IGNORECASE)

# “Animais”/grupos para corte de carnes — mantém até aqui (inclusive)
MEAT_ANIMALS = ["BOVINO", "FRANGO", "SUÍNO", "SUINO", "PEIXE", "CAMARÃO", "CAMARAO", "BACALHAU", "PERU"]
ANIMALS_RE = re.compile(r"\b(" + "|".join(MEAT_ANIMALS) + r")\b", re.IGNORECASE)


# ---------------- HELPERS ----------------

def brl_to_float(txt: str) -> float:
    cleaned = re.sub(r"[^\d,]", "", txt).replace(".", "").replace(",", ".")
    return float(cleaned)

def limpar_linha(l: str) -> str:
    """Normaliza espaços e separa casos grudados tipo '0,99Molho' / '5,80kg'."""
    l = (l or "").strip()
    # 0,99Molho -> 0,99 Molho
    l = re.sub(r"(?<=\d),(?=\d{2})(?=[A-Za-zÁ-ú])", ", ", l)
    # 5,80kg / 5,80cada -> 5,80 kg / 5,80 cada
    l = re.sub(r"(?<=\d),(?=\d{2})(?=(?:kg|l|ml|g|cada)\b)", ", ", l, flags=re.IGNORECASE)
    # dígito/centavos grudados em letras
    l = re.sub(r"(?<=[\d,])(?=[A-Za-zÁ-ú])", " ", l)
    # espaços extras
    l = re.sub(r"\s+", " ", l)
    # pontuação nas bordas
    return l.strip(" :-–—•|.,\t")

def is_name_candidate(txt: str) -> bool:
    if not txt or len(txt) < 3:
        return False
    if PRICE_RE.fullmatch(txt):
        return False
    if EXCLUDE_PAT.search(txt):
        return False
    return bool(re.search(r"[A-Za-zÁ-ú]", txt))


# ---------------- LIMPEZA DIRECIONADA (CARNES) ----------------

def clean_meat_name(name: str) -> str:
    """Remove prefixos de unidade, corta 'pacotes' grudados e trunca até o animal (Bovino/Frango/...)."""
    if not name:
        return ""
    s = name

    # remove prefixos de unidade no INÍCIO
    s = re.sub(r"^(kg|cada|un|und|unid|l|ml|g)\s*", "", s, flags=re.IGNORECASE)

    # remove pacote 'Resfriado/ Congelado ... Friboi ... (kg|cada)' se vier logo no começo
    s = re.sub(r"^(resfriado|congelad[oa])\b.*?\b(friboi)\b.*?(kg|cada)\b", "", s, flags=re.IGNORECASE).strip()
    # opcional extra: remover “peça / pedaço ...” grudado no início (marca/forma de venda)
    s = re.sub(r"^(resfriado|congelad[oa])\b.*?\b(peça|pedaço|peca|pedaco)\b", "", s, flags=re.IGNORECASE).strip()

    # se por acaso houver outro preço colado depois do nome, corta antes
    s = re.split(PRICE_RE, s)[0]

    # regra principal para carnes: truncar até o animal, se existir
    m = ANIMALS_RE.search(s)
    if m:
        end = m.end()
        s = s[:end]

    # remove tokens soltos no fim
    s = re.sub(r"\b(kg|cada|un|und|unid|l|ml|g)\b$", "", s, flags=re.IGNORECASE).strip()

    # normalizações finais
    s = re.sub(r"\s*[/]\s*", "/", s)           # "Peça / Pedaço" -> "Peça/Pedaço"
    s = re.sub(r"\s+", " ", s).strip(" -–—•|.,\t")

    return s


# ---------------- MONTAGEM DE NOME (CONSERVADORA) ----------------

def montar_nome(lines: List[str], idx: int, atual: str, match) -> Optional[str]:
    """
    Estratégia:
      1) Preferir o texto à ESQUERDA do preço; se começar com unidade (kg/cada) ou for curto, usar DIREITA.
      2) Opcionalmente pegar 1 linha acima (se for complemento imediato e não começar com unidade).
      3) Opcionalmente pegar 1 linha abaixo (idem).
      4) Cortar se aparecer outro preço no meio.
      5) Limpezas de carnes.
    """
    partes: List[str] = []

    left = limpar_linha(atual[: match.start()])
    right = limpar_linha(atual[match.end():])

    prefer_right = (len(left) < 4) or bool(UNIT_WORD.match(left))
    cand_line = right if (prefer_right and is_name_candidate(right)) else left

    if is_name_candidate(cand_line) and not UNIT_WORD.match(cand_line):
        partes.append(cand_line)

    # no máximo 1 linha acima
    if idx - 1 >= 0:
        up = limpar_linha(lines[idx - 1])
        if is_name_candidate(up) and not PRICE_RE.search(up) and not UNIT_WORD.match(up):
            partes.insert(0, up)

    # no máximo 1 linha abaixo
    if idx + 1 < len(lines):
        down = limpar_linha(lines[idx + 1])
        if is_name_candidate(down) and not PRICE_RE.search(down) and not UNIT_WORD.match(down):
            partes.append(down)

    nome = " ".join(partes).strip()
    # corta qualquer sobra quando há outro preço misturado
    nome = re.split(PRICE_RE, nome)[0]
    nome = re.sub(r"\s+", " ", nome).strip(" -–—•|.,\t")

    if not is_name_candidate(nome):
        return None

    # limpeza específica de carnes
    nome2 = clean_meat_name(nome)
    if is_name_candidate(nome2):
        nome = nome2

    # Evita nome começar com 'kg'
    nome = re.sub(r"^kg\s*", "", nome, flags=re.IGNORECASE).strip()

    return nome if is_name_candidate(nome) else None


# ---------------- EXTRAÇÃO ----------------

def extrair_itens(pdf_path: Path) -> pd.DataFrame:
    reader = PdfReader(str(pdf_path))
    items = []
    for pnum, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = [limpar_linha(l) for l in text.splitlines() if l and l.strip()]
        for i, line in enumerate(lines):
            for m in PRICE_RE.finditer(line):
                price_text = m.group(0)
                nome = montar_nome(lines, i, line, m)
                if not nome:
                    continue
                try:
                    price_val = brl_to_float(price_text)
                except Exception:
                    continue
                items.append({
                    "page": pnum,
                    "product_name": nome,
                    "price_value": price_val,
                    "pdf_name": pdf_path.name
                })
    return pd.DataFrame(items)


# ---------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser(description="Extrai produtos+preços (CSV limpo) do folheto.")
    ap.add_argument("--pdf", type=str, default="", help="Caminho do PDF.")
    ap.add_argument("--base-dir", type=str, default="backend/data/folhetos/brasil_atacarejo",
                    help="Pasta padrão onde ficam os PDFs.")
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

    print(f"[INFO] Extraindo de: {pdf_path.name}")
    df = extrair_itens(pdf_path)
    if df.empty:
        print("Nenhum item encontrado.")
        return

    out_csv = pdf_path.parent / f"extracao_brasil_atacarejo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")

    print(f"[OK] {len(df)} itens salvos em {out_csv}")
    print(df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
