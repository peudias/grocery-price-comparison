from pathlib import Path
from typing import List
import sys
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

    alvo = pdfs[0].resolve()
    print(alvo)

if __name__ == "__main__":
    main()
