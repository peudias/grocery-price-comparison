# backend/src/ocr/encarte_vision_extrator.py
from pathlib import Path
import re
import argparse
import pandas as pd
from google.cloud import vision

# === Config ===
FOLDER_PNG = Path("backend/data/folhetos/brasil_atacarejo_png")
OUT_DIR    = Path("backend/data/csv/brasil_atacarejo")

# Preços: 23,80 | 1.299,90 | R$ 19,80
PRICE_FULL_RE   = re.compile(r"^(?:R\$?\s*)?\d{1,3}(?:\.\d{3})*,\d{2}$")
PRICE_FRAG_RE   = re.compile(r"^\d{1,3},\d$")  # "34,8" (falta o "0")
UNIT_WORDS      = {"kg","cada","un","unid","lt","l","ml","g","peça","pct","pc","cx","bandeja"}
TRASH_WORDS     = {"brasil","atacarejo","economia","fazemos","entrega","domicílio","american","amercan","friara","uaj"}  # ruídos comuns do flyer
LINE_Y_TOL      = 10  # tolerância para juntar tokens na mesma linha

# ROI em torno do preço (ajuste fino aqui se precisar)
ROI_EXPAND_X = 160  # expande para esquerda/direita
ROI_UP       = 220  # captura texto acima do preço (produto)
ROI_DOWN     = 70   # evita pegar coisas abaixo (outra oferta)

# ---------- util ----------
def _poly_to_xywh(vertices):
    xs = [v.x for v in vertices]; ys = [v.y for v in vertices]
    x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
    return float(x0), float(y0), float(x1-x0), float(y1-y0)

def _all_tokens(resp):
    toks = []
    for ann in resp.text_annotations[1:]:
        x, y, w, h = _poly_to_xywh(ann.bounding_poly.vertices)
        t = ann.description.strip()
        if not t:
            continue
        toks.append({"t": t, "x": x, "y": y, "w": w, "h": h, "cx": x + w/2, "cy": y + h/2})
    toks.sort(key=lambda z: (z["y"], z["x"]))
    return toks

def _join_price_fragments(toks):
    """Conserta '34,8' + '0' -> '34,80' (ou ... + '00')."""
    out = []
    i = 0
    while i < len(toks):
        cur = toks[i]
        if PRICE_FRAG_RE.match(cur["t"]) and i + 1 < len(toks) and toks[i+1]["t"] in {"0", "00"}:
            nxt = toks[i+1]
            cur["t"] = cur["t"] + nxt["t"]
            cur["w"] = (nxt["x"] + nxt["w"]) - cur["x"]
            cur["cx"] = cur["x"] + cur["w"]/2
            i += 2
            out.append(cur)
        else:
            out.append(cur)
            i += 1
    return out

def _normalize_price_token(txt: str) -> str | None:
    raw = txt.replace(" ", "")
    # 11.80 -> 11,80 (se parecer preço com ponto)
    if re.fullmatch(r"(?:R\$?\s*)?\d{1,3}(?:\.\d{3})*\.\d{2}", raw):
        # troca o último ponto por vírgula
        parts = raw.rsplit(".", 1)
        raw = parts[0].replace(".", ".") + "," + parts[1]
    if PRICE_FULL_RE.match(raw):
        return raw.replace("R$", "")
    return None

def _find_prices(toks):
    """Acha tokens que são preço + deduplica por proximidade (evita pegar sombra/duplicado)."""
    found = []
    for tk in toks:
        norm = _normalize_price_token(tk["t"])
        if norm:
            item = dict(tk)
            item["price"] = norm
            found.append(item)
    dedup = []
    for p in found:
        keep = True
        for q in dedup:
            if abs(p["cx"] - q["cx"]) < 40 and abs(p["cy"] - q["cy"]) < 40:
                # mantém o de maior área
                if p["w"]*p["h"] > q["w"]*q["h"]:
                    q.update(p)
                keep = False
                break
        if keep:
            dedup.append(p)
    return dedup

def _roi_for_price(p):
    x0 = p["x"] - ROI_EXPAND_X
    x1 = p["x"] + p["w"] + ROI_EXPAND_X
    y0 = max(0, p["y"] - ROI_UP)
    y1 = p["y"] + ROI_DOWN
    return x0, y0, x1, y1


def _text_above_price_in_roi(toks, price_tok):
    x0, y0, x1, y1 = _roi_for_price(price_tok)
    region = [t for t in toks
              if x0 <= t["cx"] <= x1 and y0 <= t["cy"] <= y1 and t["cy"] < price_tok["cy"] - 6]

    clean = []
    for t in region:
        # ignora tokens que já são preços ou números soltos
        if _normalize_price_token(t["t"]): 
            continue
        if re.fullmatch(r"\d+|\d+[xX]|\d{1,2}g|\d{1,2}kg", t["t"]):
            continue

        wnorm = re.sub(r"[^\wáéíóúâêôãõç/]", "", t["t"].lower())
        if wnorm in UNIT_WORDS or wnorm in TRASH_WORDS:
            continue
        clean.append(t)

    clean.sort(key=lambda z: (z["cy"], z["cx"]))
    lines, cur = [], []
    for t in clean:
        if not cur or abs(t["cy"] - cur[-1]["cy"]) <= LINE_Y_TOL:
            cur.append(t)
        else:
            lines.append(cur); cur = [t]
    if cur: lines.append(cur)

    parts = []
    for ln in lines:
        ln.sort(key=lambda z: z["cx"])
        parts.append(" ".join(x["t"] for x in ln))

    txt = re.sub(r"\s{2,}", " ", " ".join(parts).strip())
    # pós-limpeza: tira sobras de vírgulas/barras duplicadas
    txt = re.sub(r"\s*/\s*", " / ", txt)
    txt = re.sub(r"\s{2,}", " ", txt).strip(" -_/")
    return txt


def _unit_near_price(toks, price_tok):
    px1 = price_tok["x"] + price_tok["w"]
    best = ""
    for t in toks:
        same_line = abs(t["cy"] - price_tok["cy"]) <= 8
        right     = px1 - 5 < t["cx"] < px1 + 150
        if not (same_line and right):
            continue
        w = re.sub(r"[^\wáéíóúâêôãõç\.]", "", t["t"].lower())
        if w in UNIT_WORDS or w in {"kg","kg.", "cada"}:
            best = "kg" if "kg" in w else "cada"
            break
    return best


# ---------- principal ----------
def process_image(img_path: Path) -> pd.DataFrame:
    client = vision.ImageAnnotatorClient()
    with open(img_path, "rb") as f:
        image = vision.Image(content=f.read())
    resp = client.text_detection(image=image)
    if resp.error.message:
        raise RuntimeError(resp.error.message)

    toks   = _all_tokens(resp)
    toks   = _join_price_fragments(toks)
    prices = _find_prices(toks)

    # monta linhas a partir dos preços e ordena (top->down, left->right)
    rows = []
    for p in prices:
        produto = _text_above_price_in_roi(toks, p)
        if not produto:
            continue
        unidade = _unit_near_price(toks, p)
        rows.append({"y": p["cy"], "x": p["cx"], "produto": produto, "preco_brl": p["price"], "unidade": unidade})

    rows.sort(key=lambda r: (round(r["y"]/40), r["x"]))  # agrupa em faixas de ~40px

    # numeração
    for i, r in enumerate(rows, start=1):
        r["ordem"] = i
    df = pd.DataFrame(rows, columns=["ordem","produto","preco_brl","unidade"])
    return df

def save_csv_for_image(img_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    df = process_image(img_path)
    out_csv = out_dir / (img_path.stem + ".csv")
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[OK] {img_path.name}: {len(df)} itens -> {out_csv}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", help="Caminho de 1 imagem PNG")
    ap.add_argument("--folder", help="Pasta com PNGs (default: brasil_atacarejo_png)", action="store_true")
    args = ap.parse_args()

    if args.img:
        save_csv_for_image(Path(args.img), OUT_DIR)
        return

    # default: processa todas as imagens da pasta
    base = FOLDER_PNG if args.folder or True else Path(args.folder)
    assert base.exists(), f"Pasta não encontrada: {base}"
    for img in sorted(base.glob("*.png")):
        try:
            save_csv_for_image(img, OUT_DIR)
        except Exception as e:
            print(f"[ERRO] {img.name}: {e}")

if __name__ == "__main__":
    main()
