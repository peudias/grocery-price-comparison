from __future__ import annotations
from pathlib import Path
from typing import List
import sys
import re

import gdown
from pdf2image import convert_from_path

# ========= DRIVE DOS FOLHETOS DO BRASIL ATACAREJO =========
FOLDER_URL = "https://drive.google.com/drive/folders/1mzp4QQj7Ep1GRvjy4tRHbLfqu-_Ts7Ns"

# Pastas de dados
DATA_RAW = Path("backend/data/raw/brasil_atacarejo");
DATA_PROCESSED = Path("backend/data/processed/brasil_atacarejo");

# ========= CIDADES DE INTERESSE =========
PADRAO_CIDADE = re.compile(
    r"(BRUMADO|VIT[ÓO]RIA\s+DA\s+CONQUISTA)",
    flags=re.IGNORECASE,
)

def converter_pdf_para_png(pdf_path: Path, pasta_destino: Path) -> List[Path]:
    """
    Converte um PDF em imagens PNG (uma por página).
    """
    pasta_destino.mkdir(parents=True, exist_ok=True)
    imagens = convert_from_path(pdf_path, dpi=200)

    caminhos_png: List[Path] = []
    for i, img in enumerate(imagens, start=1):
        nome_png = pdf_path.stem + f"_p{i}.png"
        caminho_png = pasta_destino / nome_png
        img.save(caminho_png, "PNG")
        caminhos_png.append(caminho_png)
        print(f"[OK] Gerado: {caminho_png.name}")

    return caminhos_png
    
def baixar_pdfs_brasil_atacarejo() -> List[Path]:
    """
    Baixa todos os PDFs da pasta do Drive,
    filtra apenas BRUMADO e VITÓRIA DA CONQUISTA,
    e remove o restante.
    Retorna a lista de PDFs mantidos.
    """
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    print("[INFO] Baixando PDFs do Brasil Atacarejo...")
    files = gdown.download_folder(
        url=FOLDER_URL,
        output=str(DATA_RAW),
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
    ) or []

    pdfs = [Path(p) for p in files if str(p).lower().endswith(".pdf")]
    if not pdfs:
        print("[ERRO] Nenhum arquivo PDF foi encontrado no Drive do Brasil Atacarejo.", file=sys.stderr)
        return []
    
    manter = [p for p in pdfs if PADRAO_CIDADE.search(p.name)]
    remover = [p for p in pdfs if p not in manter]

    for p in remover:
        try:
            p.unlink(missing_ok=True)
            print(f"[REMOVIDO] {p.name}")
        except Exception as e:
            print(f"[AVISO] Não foi possível remover {p.name}: {e}", file=sys.stderr)
    
    if not manter:
        print("[ERRO] Nenhum PDF de BRUMADO ou VITÓRIA DA CONQUISTA foi encontrado.", file=sys.stderr)
        return []

    return manter

def run_download_and_convert() -> List[Path]:
    """
    Função principal do pipeline:
    - baixa PDFs
    - converte para PNG
    - retorna lista de PNGs gerados
    """
    pdfs = baixar_pdfs_brasil_atacarejo()
    if not pdfs:
        return []
    
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    todos_pngs: List[Path] = []
    for pdf in pdfs:
        print(f"[INFO] Convertendo {p.name} para PNG...")
        pngs = converter_pdf_para_png(pdf, DATA_PROCESSED)
        todos_pngs.extend(pngs)
    
    print("\n[FINALIZADO] Todos os folhetos foram baixados e convertidos.")
    return todos_pngs

def main() -> None:
    pngs = run_download_and_convert()
    if not pngs:
        sys.exit(1)

if __name__ == "__main__":
    main()