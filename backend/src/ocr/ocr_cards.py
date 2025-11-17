from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any
import io
import re
import argparse
import base64
import json

import pandas as pd
from PIL import Image
from openai import OpenAI
from google.cloud import vision

from dotenv import load_dotenv
load_dotenv()

# ========= CONFIG =========
FOLDER_PNG  = Path("backend/data/processed/brasil_atacarejo")
OUT_DIR     = Path("backend/data/csv/brasil_atacarejo")
client_oa   = OpenAI()
client_gv   = vision.ImageAnnotatorClient()
PRICE_RE    = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

ROW_Y_TOLERANCE     = 80
CARD_TOP_PAD        = 450
CARD_BOTTOM_PAD     = 40
CARD_X_PAD          = 40

# ========= GOOGLE VISION: DETECTAR PREÇOS =========
def detect_prices_google(img_path: Path) -> List[Dict[str, Any]]:
    """
    Detecta todos os preços e suas coordenadas com o Google Vision.
    
    Retorna uma lista de dicionários com:
    - t: texto cru detectado
    - x, y, w, h, cx, cy: coordenadas do bounding box
    - preco: texto do preco (igual a t) se for um preço válido
    """
    with open(img_path, "rb") as f:
        image = vision.Image(content=f.read())

    resp = client_gv.text_detection(image=image)
    toks: List[Dict[str, Any]] = []

    # text_annotations[0] é o texto completo; [1:] são os tokens
    for ann in resp.text_annotations[1:]:
        text = ann.description.strip()
        if not text:
            continue

        vertices = ann.bounding_poly.vertices
        xs = [v.x for v in vertices]
        ys = [v.y for v in vertices]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)

        toks.append({
            "t": text,
            "x": float(x0),
            "y": float(y0),
            "w": float(x1 - x0),
            "h": float(y1 - y0),
            "cx": float((x0 + x1) / 2),
            "cy": float((y0 + y1) / 2),
        })

    # filtrar apenas os tokens que são preços válidos
    prices: List[Dict[str, Any]] = []
    for t in toks:
        if PRICE_RE.fullmatch(t["t"]):
            t["preco"] = t["t"]
            prices.append(t)

    # ordenar por posição na imagem (primeiro por Y, depois por X)
    prices.sort(key=lambda p: (p["cy"], p["cx"]))
    return prices

def group_by_row(prices: List[Dict[str, Any]], y_tol: int = ROW_Y_TOLERANCE) -> List[List[Dict[str, Any]]]:
    """
    Agrupa preços em "fileiras" com base na coordenada Y, usando uma tolerância y_tol.
    """
    rows: List[List[Dict[str, Any]]] = []
    for p in prices:
        if not rows or abs(p["cy"] - rows[-1][-1]["cy"]) > y_tol:
            rows.append([p])
        else:
            rows[-1].append(p)

    # ordena cada fileira da esquerda para a direita
    for r in rows:
        r.sort(key=lambda x: x["cx"])
    return rows

# ========= GPT-4 VISION: EXTRAIR PRODUTO DE CADA CARD =========
# def encode_image(image: Image.Image) -> str:
#     buffer = io.BytesIO()
#     image.save(buffer, format="PNG")
#     return base64.b64encode(buffer.getvalue()).decode("utf-8")

def ask_gpt4_vision(card_img: Image.Image, preco_str: str) -> Dict[str, str]:
    """
    Envia o recorte do card para o GPT-4o-mini via Vision e extrai:
    - produto
    - unidade
    - preco

    Sempre retorna um dicionário com as chaves:
    {"produto": str, "unidade": str, "preco": str}
    """
    # Converte o card para base64
    buf = io.BytesIO()
    card_img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = f"""
Você está vendo um card de oferta de supermercado.

Extraia APENAS:

- "produto": nome completo do produto (sem preço, sem texto de promoção, sem datas)
- "unidade": unidade de venda (por exemplo: "kg", "un", "pct", "peça", "bandeja" ou "" se não aparecer)
- "preco": o preço do produto, que deve ser exatamente "{preco_str}"

Responda SOMENTE com um JSON VÁLIDO, sem texto antes ou depois, no formato exato:

{{
  "produto": "...",
  "unidade": "...",
  "preco": "{preco_str}"
}}
"""

    response = client_oa.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=200,
        temperature=0
    )

    raw = response.choices[0].message.content.strip()
    # DEBUG opcional: ver o que o modelo está mandando
    # print("GPT RAW:", raw)

    # 1) Se vier dentro de ```json ... ``` ou ```...```, remove cercas
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9]*\s*", "", raw)  # tira ```json
        raw = re.sub(r"```$", "", raw).strip()         # tira ``` final

    # 2) Tenta extrair só o trecho entre a primeira { e a última }
    if "{" in raw and "}" in raw:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        raw_json = raw[start:end]
    else:
        raw_json = raw

    try:
        data = json.loads(raw_json)
    except Exception:
        return {"produto": "", "unidade": "", "preco": preco_str}

    # garantias básicas
    produto = (data.get("produto") or "").strip()
    unidade = (data.get("unidade") or "").strip()
    preco   = (data.get("preco") or preco_str).strip()

    return {
        "produto": produto,
        "unidade": unidade,
        "preco": preco,
    }

# ========= PIPELINE PRINCIPAL =========
def process_image(img_path: Path) -> pd.DataFrame:
    """
    Pipeline completo para processar 1 imagem:

    - carrega a imagem
    - detecta preços com Google Vision
    - agrupa por fileiras
    - recorta cda card
    - extrai produto/unidade com GPT-4 Vision
    - monta DataFrame com colunas: ordem, produto, preco_brl, unidade
    """
    print(f"[INFO] Processando {img_path.name}")

    # 1. Carregar imagem grande
    big_img = Image.open(img_path).convert("RGB")
    W, H = big_img.size

    # 2. Detectar preços com Google Vision
    prices = detect_prices_google(img_path)
    if not prices:
        print("[ERRO] Nenhum preço detectado!")
        return pd.DataFrame()

    print(f"[OK] {len(prices)} preços detectados")

    # 3. Agrupar preços por fileira
    rows = group_by_row(prices)
    out_items = []

    # 4. Para cada card, calcular o bounding box
    for row in rows:
        n = len(row)
        for i, p in enumerate(row):

            # limites laterais (metade da distância até o vizinho)
            if i == 0:
                dx = row[i+1]["cx"] - p["cx"] if n > 1 else 400
                left = p["cx"] - dx/2
            else:
                left = (row[i-1]["cx"] + p["cx"]) / 2

            if i == n - 1:
                dx = p["cx"] - row[i-1]["cx"] if n > 1 else 400
                right = p["cx"] + dx/2
            else:
                right = (p["cx"] + row[i+1]["cx"]) / 2

            # limites verticais (faixa acima e um pouco abaixo do preço)
            y_top = max(0, int(p["cy"] - 450))
            y_bottom = min(H, int(p["cy"] + 40))

            x0 = max(0, int(left - 40))
            x1 = min(W, int(right + 40))

            # 5. Recorta o card
            card = big_img.crop((x0, y_top, x1, y_bottom))

            # 6. Extrai via GPT-4 Vision
            result = ask_gpt4_vision(card, p["preco"])
            result["y"] = p["cy"]
            out_items.append(result)

    # 7. Ordenar por posição
    out_items.sort(key=lambda r: r["y"])

    # 8. Montar DataFrame final
    final_rows = []
    for i, it in enumerate(out_items, start=1):
        final_rows.append({
            "ordem": i,
            "produto": it["produto"],
            "preco_brl": it["preco"],
            "unidade": it["unidade"]
        })

    return pd.DataFrame(final_rows)


def save_csv_for_image(img_path: Path, out_dir: Path) -> Path:
    """
    Roda o OCR para uma imagem e salva o CSV correspondente em out_dir.
    Retorna o caminho do CSV gerado.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    df = process_image(img_path)
    out_csv = out_dir / (img_path.stem + ".csv")
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[OK] Gerado: {out_csv}")
    return out_csv

# ========= FUNÇÃO DE PIPELINE (VÁRIAS IMAGENS) =========
def run_ocr_for_folder(folder: Path | None = None, out_dir: Path | None = None) -> List[Path]:
    """
    Executa o OCR para todas as imagens PNG em 'folder'
    e salva os CSVs em 'out_dir'
    """
    folder = folder or FOLDER_PNG
    out_dir = out_dir or OUT_DIR

    pngs = sorted(folder.glob("*.png"))
    if not pngs:
        print("[ERRO] Nenhuma imagem PNG encontrada em", folder)
        return []

    csv_paths: List[Path] = []
    for img in pngs:
        csv_path = save_csv_for_image(img, out_dir)
        csv_paths.append(csv_path)

    return csv_paths

# ========= MAIN =========
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", help="Caminho de 1 imagem PNG")
    args = ap.parse_args()

    if args.img:
        save_csv_for_image(Path(args.img), OUT_DIR)
    else:
        run_ocr_for_folder(FOLDER_PNG, OUT_DIR)

if __name__ == "__main__":
    main()