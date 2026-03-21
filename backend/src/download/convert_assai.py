from pathlib import Path
from pdf2image import convert_from_path

backend_dir   = Path(__file__).resolve().parents[2]  # aponta para backend/
raw_dir       = backend_dir / "data" / "raw" / "assai"
processed_dir = backend_dir / "data" / "processed" / "assai"
processed_dir.mkdir(parents=True, exist_ok=True)

if not raw_dir.exists():
    print(f"[ERRO] Pasta não encontrada: {raw_dir}")
    exit(1)

pdfs = sorted(raw_dir.glob("*.pdf"))
if not pdfs:
    print(f"[ERRO] Nenhum PDF encontrado em: {raw_dir}")
    exit(1)

for pdf in pdfs:
    print(f"[INFO] Convertendo: {pdf.name}")
    imagens = convert_from_path(pdf, dpi=200)
    for i, img in enumerate(imagens, start=1):
        destino = processed_dir / f"{pdf.stem}_p{i}.png"
        if destino.exists():
            print(f"[SKIP] {destino.name}")
            continue
        img.save(destino, "PNG")
        print(f"[OK] {destino.name}")

print("\n[FINALIZADO] PNGs em:", processed_dir)