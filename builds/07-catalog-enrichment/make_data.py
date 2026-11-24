"""Generate a synthetic 20-product apparel catalog: thin supplier data plus a product photo for each."""
import json, random
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

random.seed(5)
D = Path("data")
(D / "images").mkdir(parents=True, exist_ok=True)

RGB = {"black": (25, 25, 28), "charcoal": (64, 64, 70), "heather grey": (150, 150, 155), "cream": (238, 230, 208),
       "navy": (30, 40, 80), "sky blue": (120, 170, 215), "forest green": (34, 85, 50), "olive": (110, 115, 55),
       "burgundy": (115, 25, 45), "red": (200, 40, 40), "rust": (175, 80, 40), "mustard": (210, 165, 40),
       "sand": (200, 180, 140), "pink": (230, 150, 170)}

# sku, type, style name, TRUE color, supplier color field, specs, supplier notes, TRUE material (answer key)
PRODUCTS = [
    ("P01", "tee", "Everyday Tee", "navy", "NVY", "100% org ctn 180gsm jersey, relaxed", "Super soft, eco friendly fabric.", "organic cotton"),
    ("P02", "tee", "Crew Tee", "heather grey", "HTR GRY", "ctn/poly 60/40 jersey, slim", "", "cotton-polyester blend"),
    ("P03", "hoodie", "Pullover Hoodie", "forest green", "GRN", "80/20 ctn/poly fleece 320gsm, regular", "Best hoodie ever!!", "cotton-polyester blend"),
    ("P04", "hoodie", "Zip Hoodie", "black", "NVY", "80/20 ctn/poly fleece, oversized", "", "cotton-polyester blend"),
    ("P05", "joggers", "Fleece Jogger", "charcoal", "GRY", "ctn/poly fleece, tapered", "", "cotton-polyester blend"),
    ("P06", "dress", "Midi Dress", "rust", "RST", "100% linen, relaxed", "Breathable linen for hot days.", "linen"),
    ("P07", "dress", "Wrap Dress", "sky blue", "", "100% linen, regular", "", "linen"),
    ("P08", "jacket", "Rain Shell", "olive", "OLV", "nylon ripstop, DWR finish, regular", "100% water-proof in any storm.", "nylon"),
    ("P09", "jacket", "Coach Jacket", "mustard", "MSTD", "rec poly shell, DWR, relaxed", "Made from recycled bottles.", "recycled polyester"),
    ("P10", "vest", "Women's Lightweight Packable Quilted Insulated Puffer Vest", "sand", "SND", "rec poly, regular", "", "recycled polyester"),
    ("P11", "sweater", "Merino Crew", "burgundy", "BRG", "merino 18.5 micron, slim", "Naturally anti-bacterial merino.", "merino wool"),
    ("P12", "sweater", "Cable Knit", "cream", "CRM", "wool blend 70/30 wool/nylon, relaxed", "", "wool blend"),
    ("P13", "beanie", "Rib Beanie", "red", "", "acrylic rib knit, one size", "", "acrylic"),
    ("P14", "beanie", "Merino Beanie", "charcoal", "CHR", "merino rib knit, one size", "", "merino wool"),
    ("P15", "tote", "Market Tote", "cream", "NAT", "12oz ctn canvas, one size", "Eco-Friendly everyday tote.", "cotton canvas"),
    ("P16", "tote", "Packable Tote", "black", "BLK", "rec poly ripstop, one size", "", "recycled polyester"),
    ("P17", "cap", "Dad Cap", "navy", "NVY", "adjustable strap, embroidered logo", "", "cotton twill"),
    ("P18", "shorts", "Chino Short", "olive", "OLV", "ctn twill 7in inseam, regular", "", "cotton twill"),
    ("P19", "shorts", "Run Short", "pink", "PNK", "rec poly, 5in, relaxed", "Guaranteed to last.", "recycled polyester"),
    ("P20", "tee", "Boxy Tee", "mustard", "", "100% org ctn, oversized", "", "organic cotton"),
]

SHAPES = {
    "tee":     [(120, 60), (160, 50), (240, 50), (280, 60), (350, 120), (310, 160), (280, 140), (280, 340), (120, 340), (120, 140), (90, 160), (50, 120)],
    "hoodie":  [(120, 80), (160, 70), (240, 70), (280, 80), (340, 250), (305, 260), (280, 160), (280, 340), (120, 340), (120, 160), (95, 260), (60, 250)],
    "sweater": [(120, 70), (160, 60), (240, 60), (280, 70), (345, 260), (310, 270), (280, 160), (280, 340), (120, 340), (120, 160), (90, 270), (55, 260)],
    "jacket":  [(115, 70), (160, 55), (240, 55), (285, 70), (350, 270), (312, 280), (285, 170), (285, 345), (115, 345), (115, 170), (88, 280), (50, 270)],
    "vest":    [(130, 60), (170, 50), (230, 50), (270, 60), (285, 130), (285, 340), (115, 340), (115, 130)],
    "dress":   [(160, 50), (180, 50), (190, 90), (210, 90), (220, 50), (240, 50), (250, 150), (320, 350), (80, 350), (150, 150)],
    "joggers": [(130, 50), (270, 50), (290, 345), (225, 345), (200, 140), (175, 345), (110, 345)],
    "shorts":  [(120, 100), (280, 100), (300, 280), (215, 280), (200, 190), (185, 280), (100, 280)],
    "beanie":  [(110, 300), (110, 170), (140, 110), (200, 90), (260, 110), (290, 170), (290, 300)],
    "tote":    [(100, 150), (300, 150), (300, 340), (100, 340)],
    "cap":     [(100, 240), (120, 170), (160, 130), (200, 120), (240, 130), (280, 170), (300, 240), (370, 255), (370, 270), (100, 270)],
}


def draw(sku, kind, color):
    base = RGB[color]
    img = Image.new("RGB", (400, 400), (248, 248, 246))
    d = ImageDraw.Draw(img)
    d.polygon(SHAPES[kind], fill=base, outline=tuple(max(0, c - 40) for c in base))
    trim = tuple(max(0, c - 35) for c in base)
    if kind in ("hoodie",):
        d.ellipse((160, 25, 240, 105), fill=base, outline=trim, width=3)
    if kind == "jacket":
        d.line((200, 60, 200, 345), fill=(180, 180, 180), width=4)  # zipper
    if kind == "tote":
        d.arc((150, 80, 250, 220), 180, 360, fill=trim, width=8)
    if kind in ("tee", "sweater"):
        d.arc((165, 35, 235, 85), 0, 180, fill=trim, width=6)  # collar
    d.text((12, 380), f"{sku} {kind}", fill=(110, 110, 110))
    # make it look like a photo: soft top-to-bottom lighting + sensor noise
    px = img.load()
    for y in range(400):
        light = 1.06 - 0.12 * y / 400
        for x in range(400):
            r, g, b = px[x, y]
            n = random.randint(-9, 9)
            px[x, y] = tuple(max(0, min(255, int(c * light) + n)) for c in (r, g, b))
    path = D / "images" / f"{sku}.png"
    img.save(path)
    return str(path.relative_to(D.parent))


rows, key = [], {}
for sku, kind, style, color, sup_color, specs, notes, material in PRODUCTS:
    abbrev = {"tee": "TEE", "hoodie": "HD", "sweater": "SWTR", "jacket": "JKT", "vest": "VST", "dress": "DRS",
              "joggers": "JGR", "shorts": "SHRT", "beanie": "BNE", "tote": "TOTE", "cap": "CAP"}[kind]
    rows.append({"sku": sku, "product_type": kind, "style_name": style,
                 "supplier_title": f"{abbrev}-{100 + int(sku[1:])} {sup_color}".strip(),
                 "supplier_color": sup_color, "specs": specs, "supplier_notes": notes,
                 "image": draw(sku, kind, color), "price": round(random.choice([24, 38, 48, 64, 88, 120]) - 0.01, 2)})
    key[sku] = {"color": color, "material": material}

pd.DataFrame(rows).to_csv(D / "catalog_export.csv", index=False)
(D / "merchandiser_key.json").write_text(json.dumps(key, indent=2))
(D / "supplier_color_codes.json").write_text(json.dumps(
    {"NVY": "navy", "HTR GRY": "heather grey", "GRN": "green", "GRY": "grey", "RST": "rust", "OLV": "olive",
     "MSTD": "mustard", "SND": "sand", "BRG": "burgundy", "CRM": "cream", "CHR": "charcoal", "NAT": "natural",
     "BLK": "black", "PNK": "pink"}, indent=2))
print(f"wrote {len(rows)} products and {len(rows)} images")
