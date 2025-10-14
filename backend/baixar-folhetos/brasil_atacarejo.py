from pathlib import Path
from typing import List
import sys
import re
import gdown

# Drive dos folhetos do Brasil Atacarejo
FOLDER_URL = "https://drive.google.com/drive/folders/1mzp4QQj7Ep1GRvjy4tRHbLfqu-_Ts7Ns"
DESTINO = Path("backend/data/folhetos/brasil_atacarejo");

def main():
    DESTINO.mkdir(parents=True, exist_ok=True)

    files: List[str] = gdown.download_folder(
        url=FOLDER_URL,
        output=str(DESTINO),
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
    ) or []

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
        except Exception as e:
            print(f"Aviso: não foi possível remover {p.name}: {e}", file=sys.stderr)

    if not manter:
        print("Nenhum PDF de BRUMADO ou VITÓRIA DA CONQUISTA encontrado.", file=sys.stderr)
        sys.exit(1)

    alvo = manter[0].resolve()
    print(alvo)

if __name__ == "__main__":
    main()
