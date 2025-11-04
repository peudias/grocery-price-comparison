from pathlib import Path
from typing import List
import sys
import re
import gdown
from pdf2image import convert_from_path

# Drive dos folhetos do Brasil Atacarejo
FOLDER_URL = "https://drive.google.com/drive/folders/1mzp4QQj7Ep1GRvjy4tRHbLfqu-_Ts7Ns"
DESTINO_PDF = Path("backend/data/folhetos/brasil_atacarejo_pdf");
DESTINO_PNG = Path("backend/data/folhetos/brasil_atacarejo_png");

def converter_pdf_para_png(pdf_path: Path, pasta_destino: Path) -> List[Path]:
    """Converte um PDF em imagens PNG (uma por página)."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    imagens = convert_from_path(pdf_path, dpi=200)
    caminhos_png = []

    for i, img in enumerate(imagens, start=1):
        nome_png = pdf_path.stem + f"_p{i}.png"
        caminho_png = pasta_destino / nome_png
        img.save(caminho_png, "PNG")
        caminhos_png.append(caminho_png)
        print(f"[OK] Gerado: {caminho_png.name}")

    return caminhos_png
    

def main():
    # Criar pastas
    DESTINO_PDF.mkdir(parents=True, exist_ok=True)
    DESTINO_PNG.mkdir(parents=True, exist_ok=True)

    print("[INFO] Baixando PDFs do Brasil Atacarejo...")
    files: List[str] = gdown.download_folder(
        url=FOLDER_URL,
        output=str(DESTINO_PDF),
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
    ) or []

    # Filtrar PDFs
    pdfs = [Path(p) for p in files if str(p).lower().endswith(".pdf")]
    if not pdfs:
        print("Nenhum arquivo PDF foi encontrado no Drive do Brasil Atacarejo.", file=sys.stderr)
        sys.exit(1)

    # Manter só BRUMADO e VITÓRIA DA CONQUISTA
    padrao_cidade = re.compile(r"(BRUMADO|VIT[ÓO]RIA\s+DA\s+CONQUISTA)", flags=re.IGNORECASE)
    manter = [p for p in pdfs if padrao_cidade.search(p.name)]
    remover = [p for p in pdfs if p not in manter]

    # Apagar demais PDFs
    for p in remover:
        try:
            p.unlink(missing_ok=True)
            print(f"[REMOVIDO] {p.name}")
        except Exception as e:
            print(f"Aviso: não foi possível remover {p.name}: {e}", file=sys.stderr)

    if not manter:
        print("Nenhum PDF de BRUMADO ou VITÓRIA DA CONQUISTA encontrado.", file=sys.stderr)
        sys.exit(1)

    # Converter cada PDF em PNG
    for pdf in manter:
        print(f"[INFO] Convertendo {pdf.name} para PNG...")
        converter_pdf_para_png(pdf, DESTINO_PNG)
    
    print("\n[FINALIZADO] Todos os folhetos foram baixados e convertidos.")

if __name__ == "__main__":
    main()
