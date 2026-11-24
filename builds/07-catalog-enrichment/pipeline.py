"""Build 07 - Catalog enrichment pipeline (E-commerce). Pattern: batch + structured output + vision."""
import json, random, re, statistics, sys
from pathlib import Path
from typing import Literal

import pandas as pd
from PIL import Image
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace  # noqa: E402
from common.vision import batch_vision_structured  # noqa: E402

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "outputs"
SKILL = (HERE / "skill/brand-voice/SKILL.md").read_text()


def skill_section(name: str) -> list[str]:
    body = SKILL.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]
    return [l[2:].strip() for l in body.splitlines() if l.startswith("- ")]


LIMITS = {k.strip(): int(v) for k, v in (l.split(":") for l in skill_section("Limits"))}
BANNED = skill_section("Banned claims")


# ---------- Step 2: the attribute schema ----------
Fit = Literal["relaxed", "slim", "regular", "oversized", "tapered", "one size", "unknown"]

class Enrichment(BaseModel):
    sku: str
    title: str = Field(description=f"brand-voice title, max {LIMITS['title_max_chars']} chars")
    description: str = Field(description=f"{LIMITS['description_min_words']}-{LIMITS['description_max_words']} words")
    material: str = Field(description="main fabric, or 'unknown' if not in the specs")
    fit: Fit
    color: str = Field(description="one name from the store's color list, read from the photo")
    use_case: list[str] = Field(description="1-3 short use cases")
    search_keywords: list[str]

# The store's color facet: swatch name -> reference RGB
COLORS = {"black": (25, 25, 28), "charcoal": (64, 64, 70), "heather grey": (150, 150, 155), "cream": (238, 230, 208),
          "navy": (30, 40, 80), "sky blue": (120, 170, 215), "forest green": (34, 85, 50), "olive": (110, 115, 55),
          "burgundy": (115, 25, 45), "red": (200, 40, 40), "rust": (175, 80, 40), "mustard": (210, 165, 40),
          "sand": (200, 180, 140), "pink": (230, 150, 170)}
SYSTEM = ("You are a catalog editor. From the product photo and the supplier specs, fill every attribute and write the "
          f"title and description. Color must be one of: {', '.join(COLORS)}. Material only from the specs; if it is "
          "not there, return 'unknown'. Follow this skill exactly:\n\n" + SKILL)

MATERIALS = [(r"org ctn|organic cotton", "organic cotton"), (r"ctn/poly|cotton/poly", "cotton-polyester blend"),
             (r"merino", "merino wool"), (r"wool blend|wool/", "wool blend"),
             (r"rec poly|recycled poly", "recycled polyester"), (r"nylon", "nylon"), (r"linen", "linen"),
             (r"canvas", "cotton canvas"), (r"twill", "cotton twill"), (r"acrylic", "acrylic"),
             (r"\bctn\b|cotton", "cotton")]
USES = [(r"dwr", ["rain", "commuting"]), (r"merino", ["hiking", "travel"]), (r"linen", ["warm days", "travel"]),
        (r"fleece", ["lounging", "weekends"]), (r"5in", ["running"]), (r"tote", ["shopping", "everyday carry"]),
        (r"beanie", ["cold mornings"]), (r"cap", ["sunny days"]), (r"vest", ["layering"])]
FIT_LINES = {"relaxed": "The relaxed fit gives you room to move.", "slim": "The slim fit sits close without clinging.",
             "regular": "The regular fit is true to size.", "oversized": "The oversized fit is cut roomy on purpose; size down for a closer fit.",
             "tapered": "The tapered leg narrows toward the ankle.", "one size": "One size fits most."}


def photo_color(path: Path) -> tuple[str, tuple]:
    """Offline vision stand-in: median color of the non-background pixels, snapped to the store's swatches."""
    img = Image.open(path).convert("RGB").resize((100, 100))
    px, (w, h) = img.load(), img.size
    fg = []
    for y in range(h):
        edge = [px[x, y] for x in (*range(4), *range(w - 4, w))]       # row background (lighting varies by row)
        bg = tuple(statistics.median(c[i] for c in edge) for i in range(3))
        fg += [px[x, y] for x in range(4, w - 4) if sum((a - b) ** 2 for a, b in zip(px[x, y], bg)) > 28 ** 2]
    med = tuple(int(statistics.median(p[i] for p in fg)) for i in range(3))
    name = min(COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(COLORS[n], med)))
    return name, med


def offline_enrich(p: dict, text: str, image: Path) -> Enrichment:
    specs, low = p["specs"], (p["specs"] + " " + p["product_type"]).lower()
    color, _ = photo_color(image)
    material = next((m for pat, m in MATERIALS if re.search(pat, specs.lower())), "unknown")
    fit = next((f for f in FIT_LINES if f in specs.lower()), "unknown")
    uses = []
    for pat, u in USES:
        if re.search(pat, low):
            uses += [x for x in u if x not in uses]
    uses = uses[:3] or ["everyday wear"]
    use_txt = " and ".join(uses) if len(uses) < 3 else f"{uses[0]}, {uses[1]} and {uses[2]}"
    style = p["style_name"]
    problems = text.split("PROBLEMS:\n", 1)[1].splitlines() if "PROBLEMS:" in text else []
    if any(pr.startswith("- title_too_long") for pr in problems):
        style = " ".join(style.split()[-2:])
    noun = p["product_type"] if p["product_type"] not in ("joggers", "shorts") else f"pair of {p['product_type']}"
    detail = re.search(r"\d+gsm|\d+oz|\d+(\.\d+)? micron|\d+in inseam", specs)
    lead = fit if fit not in ("unknown", "one size") else ""
    sents = [f"A {lead} {noun} made for {use_txt}.".replace("  ", " "),
             f"It's made from {material}{f' ({detail.group(0)})' if detail else ''}, so you know what you're getting."
             if material != "unknown" else "Fabric details are being confirmed.",
             FIT_LINES.get(fit, ""), f"Shown in {color}, as photographed in natural light."]
    if "dwr" in low:
        sents.append("A DWR finish makes it water-resistant in light rain.")
    note = p["supplier_notes"].strip().replace("!", "") if isinstance(p["supplier_notes"], str) else ""
    # naive guard: skip a supplier note only if it contains a banned claim spelled exactly as in the skill
    if note and not any(b in note.lower() for b in BANNED):
        sents.append(note if note.endswith(".") else note + ".")
    banned_sents = [pr.split(" in: ", 1)[1] for pr in problems if pr.startswith("- banned") and " in: " in pr]
    sents = [s for s in sents if s and s not in banned_sents]
    title = f"{style} in {color.title()} | {material.title() if material != 'unknown' else p['product_type'].title()}"
    return Enrichment(sku=p["sku"], title=title, description=" ".join(sents), material=material, fit=fit,
                      color=color, use_case=uses,
                      search_keywords=sorted({color, material, p["product_type"], *uses} - {"unknown"}))


# ---------- Step 4: deterministic checks ----------
BANNED_RX = {b: re.compile(r"\b" + r"[\s-]?".join(re.escape(ch) for ch in b.replace("-", "")) + r"\b", re.I)
             for b in BANNED}


def check(e: Enrichment) -> list[str]:
    probs = []
    for f in ["title", "description", "material", "color"]:
        if not getattr(e, f) or getattr(e, f) == "unknown":
            probs.append(f"- missing_required: {f}")
    if e.fit == "unknown":
        probs.append("- missing_required: fit")
    if not e.use_case:
        probs.append("- missing_required: use_case")
    if e.color not in COLORS:
        probs.append(f"- color_not_in_facet: {e.color}")
    if len(e.title) > LIMITS["title_max_chars"]:
        probs.append(f"- title_too_long: {len(e.title)} > {LIMITS['title_max_chars']} chars")
    n = len(e.description.split())
    if not LIMITS["description_min_words"] <= n <= LIMITS["description_max_words"]:
        probs.append(f"- description_length: {n} words")
    if "!" in e.title + e.description:
        probs.append("- exclamation_mark")
    for sent in re.split(r"(?<=\.)\s+", e.description):
        for b, rx in BANNED_RX.items():
            if rx.search(sent):
                probs.append(f"- banned '{b}' in: {sent}")
    return probs


def main():
    tr = Trace("07", "Catalog enrichment pipeline", OUT)
    tr.arch([
        {"label": "Store product feed", "kind": "data", "note": "specs + photo per SKU"},
        {"label": "Attribute schema", "kind": "code", "note": "material, fit, color, use case"},
        {"label": "Claude vision, Batch API", "kind": "ai", "note": "attributes + copy, brand-voice skill"},
        {"label": "Auto-checks", "kind": "code", "note": "required fields, banned claims, lengths"},
        {"label": "Merchandiser spot-check", "kind": "human", "note": "sample + flagged items"},
        {"label": "Publish to store", "kind": "system", "note": "before/after feed"},
    ])
    tr.story(
        situation="An apparel store with 4,000 SKUs from 30 suppliers. Titles look like 'TEE-101 NVY', and material, fit and color filters are mostly empty, so search misses products and shoppers return items that were not what they expected.",
        constraints="Copy must not make claims the brand can't back (waterproof, eco-friendly, antibacterial). Colors must use the store's swatch list or the filters break. A merchandiser signs off before anything goes live. The job runs overnight, so the Batch API halves the cost.",
        replay="Reuse: photo + spec sheet -> schema -> batch -> deterministic checks -> human sample is the same shape for any listing job (real estate, auto parts, marketplaces). Next time: put the banned-claims list in the checker and the skill from day one, and A/B test the new copy on search click-through before rolling out to all SKUs.",
    )

    cat = pd.read_csv(DATA / "catalog_export.csv").fillna("")
    codes = json.loads((DATA / "supplier_color_codes.json").read_text())
    tr.step("Export the catalog with each product's photo and specs", kind="io",
            what=f"Pulled {len(cat)} products from the store feed (synthetic): a supplier title, a spec line and one photo each.",
            code=('cat = pd.read_csv("data/catalog_export.csv")   # GET /admin/api/products.json\n'
                  'img = Image.open(row["image"])                # data/images/P01.png'),
            output=cat[["sku", "supplier_title", "supplier_color", "specs", "image"]].to_string(index=False)[:2600])

    tr.step("Define the attribute schema", kind="code",
            what=f"Material, fit, color and use case become a Pydantic schema; limits and {len(BANNED)} banned claims are read from the brand-voice SKILL.md.",
            code=("class Enrichment(BaseModel):\n    title: str; description: str\n    material: str\n"
                  "    fit: Literal['relaxed','slim','regular','oversized','tapered','one size','unknown']\n"
                  "    color: str          # one of the store's swatches\n    use_case: list[str]"),
            output="\n".join(f"{k}: {v}" for k, v in {
                "fields": ", ".join(Enrichment.model_fields), "fit_values": ", ".join(Fit.__args__),
                "color_facet": ", ".join(COLORS), "limits_from_skill": LIMITS,
                "banned_from_skill": ", ".join(BANNED)}.items()))

    prods = {r["sku"]: r for r in cat.to_dict("records")}
    def prompt(p):
        return (f"SKU {p['sku']}\nProduct type: {p['product_type']}\nStyle name: {p['style_name']}\n"
                f"Specs: {p['specs']}\nSupplier notes: {p['supplier_notes']}\nSupplier color code: {p['supplier_color']}")
    items = {s: {"text": prompt(p), "image": HERE / p["image"]} for s, p in prods.items()}
    out = batch_vision_structured(system=SYSTEM, items=items, schema=Enrichment,
                                  offline=lambda cid, txt, img: offline_enrich(prods[cid], txt, img))
    _, med = photo_color(HERE / prods["P04"]["image"])
    tr.step("Batch-run Claude to fill attributes and write on-brand copy", kind="ai",
            what=f"{len(out)} products went through one Message Batch, each with its photo as a base64 image block. Offline, color comes from Pillow pixel analysis (P04's median pixel is {med}, closest swatch '{out['P04'].color}'; the supplier said '{codes.get(prods['P04']['supplier_color'])}').",
            code=('items = {sku: {"text": prompt(p), "image": p["image"]} for sku, p in prods.items()}\n'
                  'out = batch_vision_structured(system=SYSTEM + SKILL, items=items, schema=Enrichment)\n'
                  '# content=[{"type":"image","source":{"type":"base64","media_type":"image/png",...}}, text]'),
            output=out["P01"].model_dump_json(indent=1) + "\n\n" + "\n".join(
                f"{s}  {e.color:13} {e.material:23} {e.fit:9} {', '.join(e.use_case)}" for s, e in list(out.items())[:10]) + "\n...")

    # Step 4: auto-check, send failures back once with the problems listed, check again
    first = {s: check(e) for s, e in out.items()}
    failed = {s: pr for s, pr in first.items() if pr}
    retry_items = {s: {"text": items[s]["text"] + "\nPROBLEMS:\n" + "\n".join(pr), "image": items[s]["image"]}
                   for s, pr in failed.items()}
    fixed = batch_vision_structured(system=SYSTEM, items=retry_items, schema=Enrichment,
                                    offline=lambda cid, txt, img: offline_enrich(prods[cid], txt, img))
    out.update(fixed)
    second = {s: check(e) for s, e in out.items()}
    still = {s: pr for s, pr in second.items() if pr}
    tr.step("Auto-check required fields, banned claims and length limits", kind="check",
            what=f"Plain code checks every product. {len(failed)} failed on the first pass; they were re-run once with the problems listed, and {len(still)} still need a person.",
            code=('rx = r"\\b" + r"[\\s-]?".join(term)  + r"\\b"   # catches "eco friendly", "water-proof"\n'
                  'probs = check(e)   # required fields, title <= 70, 25-70 words, banned claims, "!"\n'
                  'retry = {s: prompt + "PROBLEMS:\\n" + "\\n".join(p) for s, p in failed.items()}'),
            output="first pass:\n" + "\n".join(f"  {s} {p}" for s, pr in failed.items() for p in pr)
            + "\n\nafter one retry:\n" + ("\n".join(f"  {s} {p}" for s, pr in still.items() for p in pr) or "  all pass"))

    # Step 5: merchandiser spot-check against the answer key, then publish
    key = json.loads((DATA / "merchandiser_key.json").read_text())
    passed = [s for s in out if s not in still]
    sample = sorted(random.Random(1).sample(passed, 5)) + sorted(still)
    rows = []
    for s in sample:
        e = out[s]
        rows.append(f"{s}  color {e.color:13} {'OK ' if e.color == key[s]['color'] else 'WRONG'}  "
                    f"material {e.material:23} {'OK' if e.material == key[s]['material'] else 'WRONG (key: ' + key[s]['material'] + ')'}"
                    f"{'  -> held for review' if s in still else ''}")
    color_ok = sum(out[s].color == key[s]["color"] for s in key)
    mat_ok = sum(out[s].material == key[s]["material"] for s in key)
    before_color_ok = sum(codes.get(prods[s]["supplier_color"], "") == key[s]["color"] for s in key)
    status = {s: ("held: " + "; ".join(p[2:] for p in still[s])) if s in still else "published" for s in out}
    tr.step("Merchandiser spot-checks a sample, then publish", kind="human",
            what=f"A merchandiser checks 5 random products plus every flagged one against her own labels, then publishes {len(passed)} and holds {len(still)}.",
            code=('sample = random.sample(passed, 5) + still        # plus everything the checks flagged\n'
                  'ok = e.color == key[s]["color"] and e.material == key[s]["material"]'),
            output="\n".join(rows) + f"\n\nfull answer key ({len(key)} products):\n"
            f"  color facet correct: {before_color_ok}/{len(key)} supplier data -> {color_ok}/{len(key)} enriched\n"
            f"  material correct:    {mat_ok}/{len(key)} (the miss has no material in its specs, so it was held)")

    # Before/after catalog
    rows = []
    for s, p in prods.items():
        e = out[s]
        rows.append({"sku": s, "before_title": p["supplier_title"], "after_title": e.title,
                     "before_color": codes.get(p["supplier_color"], ""), "after_color": e.color,
                     "before_material": "", "after_material": e.material, "before_fit": "", "after_fit": e.fit,
                     "before_use_case": "", "after_use_case": "; ".join(e.use_case),
                     "before_description": p["specs"], "after_description": e.description, "status": status[s]})
    ba = pd.DataFrame(rows)
    ba.to_csv(OUT / "catalog_before_after.csv", index=False)
    (OUT / "publish_feed.json").write_text(json.dumps([out[s].model_dump() for s in passed], indent=2))
    (OUT / "review_queue.json").write_text(json.dumps({s: {"enrichment": out[s].model_dump(), "problems": still[s]}
                                                       for s in still}, indent=2))

    facets = ["color", "material", "fit", "use_case"]
    before_filled = sum(bool(r[f"before_{f}"]) for r in rows for f in facets)
    after_filled = sum(bool(r[f"after_{f}"]) and r[f"after_{f}"] != "unknown" for r in rows for f in facets)
    total = len(rows) * len(facets)
    tr.step("Write the before/after catalog", kind="io",
            what=f"Published products go to the store feed; the before/after CSV shows what changed. Filterable fields filled: {before_filled}/{total} -> {after_filled}/{total}.",
            code=('ba.to_csv("outputs/catalog_before_after.csv", index=False)\n'
                  'requests.put(f"{STORE}/products/{sku}.json", json=payload)   # simulated publish'),
            output=ba[["sku", "before_title", "after_title", "status"]].head(12).to_string(index=False, max_colwidth=58)
            + "\n\nP08 after: " + out["P08"].description)

    # Throughput: by hand ~10 min per product; now 2 min per sampled product + 10 min per held product
    manual_per_h = 60 / 10
    review_min = len(sample) * 2 + len(still) * 10
    after_per_h = len(passed) / (review_min / 60)
    fit_mat_copy = sum(out[s].fit != "unknown" and out[s].material != "unknown" for s in passed)
    tr.metrics(products_enriched_per_merchandiser_hour=f"{manual_per_h:.0f} -> {after_per_h:.0f}",
               filterable_fields_filled=f"{before_filled}/{total} -> {after_filled}/{total}",
               color_facet_correct=f"{before_color_ok}/{len(key)} -> {color_ok}/{len(key)}",
               material_correct=f"{mat_ok}/{len(key)}",
               banned_claims_caught_before_publish=sum(1 for pr in first.values() for p in pr if p.startswith("- banned")),
               published=f"{len(passed)}/{len(out)} ({len(still)} held for review)",
               copy_states_fit_and_material=f"0/{len(out)} -> {fit_mat_copy}/{len(passed)} published (proxy for 'not as described' returns)",
               search_clicks="needs a live A/B test; not measurable offline")
    tr.save()


if __name__ == "__main__":
    main()
