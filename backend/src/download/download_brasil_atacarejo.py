from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import sys
import gdown
from pdf2image import convert_from_path

CONFIG_PATH = Path("backend/src/download/config_brasil_atacarejo.txt")

# 1. Leitura do arquivo de configuração (geral + cidades)
def carregar_config(config_path: Path) -> Tuple[str, Path, Path, Dict[str, bool]]:
    """
    Lê o arquivo de configuração e retorna:
    - folder_url (str)
    - data_raw (Path)
    - data_processed (Path)
    - flags_cidades (dict)
    """
    if not config_path.exists():
        print(f"[ERRO] Arquivo de configuração não encontrado: {config_path}")
        sys.exit(1)

    folder_url = None
    data_raw = None
    data_processed = None
    flags_cidades: Dict[str, bool] = {}

    with config_path.open("r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()

            if not linha or linha.startswith("#"):
                continue

            if "=" not in linha:
                print(f"[AVISO] Linha inválida no config: {linha}")
                continue

            chave_raw, valor_raw = linha.split("=", 1)
            chave = chave_raw.strip().upper()
            valor = valor_raw.strip()

            # Configurações gerais
            if chave == "FOLDER_URL":
                folder_url = valor
                continue

            if chave == "DATA_RAW":
                data_raw = Path(valor)
                continue

            if chave == "DATA_PROCESSED":
                data_processed = Path(valor)
                continue

            # Flags de cidades (TRUE/FALSE)
            valor_bool = valor.upper()
            if valor_bool in {"TRUE", "1", "SIM", "YES"}:
                flags_cidades[chave] = True
            elif valor_bool in {"FALSE", "0", "NAO", "NÃO", "NO"}:
                flags_cidades[chave] = False
            else:
                print(f"[AVISO] Valor inválido: {valor_raw} ({chave})")

    if not folder_url or data_raw is None or data_processed is None:
        print("[ERRO] Configurações gerais incompletas no arquivo de configuração.")
        sys.exit(1)

    return folder_url, data_raw, data_processed, flags_cidades

# 2. Decisão de manter/remover PDF
def deve_manter_pdf(nome_pdf: str, flags: Dict[str, bool]) -> bool:
    nome = nome_pdf.upper()

    for cidade, flag in flags.items():
        if cidade in nome:
            return flag

    return False

# 3. Conversão e download
def converter_pdf_para_png(pdf_path: Path, pasta_destino: Path) -> List[Path]:
    pasta_destino.mkdir(parents=True, exist_ok=True)
    imagens = convert_from_path(pdf_path, dpi=200)

    saidas = []
    for i, img in enumerate(imagens, start=1):
        nome_png = pdf_path.stem + f"_p{i}.png"
        destino = pasta_destino / nome_png

        if destino.exists():
            print(f"[SKIP] PNG já existe, pulando: {destino}")
            saidas.append(destino)
            continue

        img.save(destino, "PNG")
        print(f"[OK] Gerado: {destino}")
        saidas.append(destino)

    return saidas
    
def baixar_pdfs(folder_url: str, data_raw: Path) -> List[Path]:
    print("[INFO] Baixando PDFs do Brasil Atacarejo...")

    data_raw.mkdir(parents=True, exist_ok=True)

    arquivos = gdown.download_folder(
        url=folder_url,
        output=str(data_raw),
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
    ) or []

    return [Path(p) for p in arquivos if p.lower().endswith(".pdf")]

# 4. Pipeline completo
def run():
    folder_url, data_raw, data_processed, flags_cidades = carregar_config(CONFIG_PATH)

    # Verifica se existe pelo menos uma cidade TRUE
    cidades_ativas = [c for c, v in flags_cidades.items() if v]
    if not cidades_ativas:
        print("[ERRO] Nenhuma cidade está marcada como TRUE no arquivo de configuração.")
        print("       Edite backend/src/download/brasil_atacarejo_config.txt e marque pelo menos uma cidade =TRUE.")
        return

    print("\n[INFO] CONFIGURAÇÕES CARREGADAS:")
    print(f"   FOLDER_URL      = {folder_url}")
    print(f"   DATA_RAW        = {data_raw}")
    print(f"   DATA_PROCESSED  = {data_processed}")
    print("   CIDADES:")
    for c, v in flags_cidades.items():
        status = "MANTER" if v else "REMOVER"
        print(f"      - {c}: {status}")

    # 1) Baixar NOVOS PDFs (se houver)
    pdfs_novos = baixar_pdfs(folder_url, data_raw)

    if not pdfs_novos:
        print("[AVISO] Nenhum PDF novo foi baixado. Usando apenas os PDFs já existentes na pasta raw.")

    # 2) Agora considerar TODOS os PDFs presentes em data_raw
    todos_pdfs = list(data_raw.glob("*.pdf"))

    if not todos_pdfs:
        print("[ERRO] Não há nenhum PDF na pasta raw (mesmo após o download).")
        return

    # 3) Aplicar as flags de cidades em cima de TODOS os PDFs
    manter = [p for p in todos_pdfs if deve_manter_pdf(p.name, flags_cidades)]
    remover = [p for p in todos_pdfs if p not in manter]

    for p in remover:
        print(f"[REMOVIDO] {p.name}")
        p.unlink(missing_ok=True)

    if not manter:
        print("[ERRO] Não há PDFs correspondentes às cidades marcadas como TRUE:")
        for c in cidades_ativas:
            print(f"   - {c}")
        return

    print("\n[INFO] PDFs mantidos (após filtro por cidade):")
    for p in manter:
        print(f"   - {p.name}")

    print("\n[INFO] Convertendo PDFs para PNG (TODOS os mantidos)...")
    data_processed.mkdir(parents=True, exist_ok=True)

    for pdf in manter:
        converter_pdf_para_png(pdf, data_processed)

    print("\n[FINALIZADO] Processo concluído.")

if __name__ == "__main__":
    run()