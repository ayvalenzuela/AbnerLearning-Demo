# Build 07 · E-commerce — Catalog enrichment pipeline

**Pattern:** Batch + structured output · **Claude features:** vision (base64 image blocks), structured output (JSON schema), Message Batches API, a brand-voice Skill

## 1 · Situation
An apparel store has 4,000 SKUs from 30 suppliers. Titles look like `TEE-101 NVY`. The material, fit and color filters are mostly empty or use supplier codes, so search misses products, and shoppers return items that weren't what they expected.

## 2 · Constraints
- Copy must not make claims the brand can't back up (waterproof, eco-friendly, antibacterial). The banned list lives in one place, the brand-voice `SKILL.md`, and both the prompt and the checker read it.
- Colors must come from the store's swatch list, or the filters break. Color is read from the photo, not copied from the supplier's code.
- Material comes only from the spec sheet. If it isn't there, the answer is "unknown" and the product goes to a person; nothing is guessed.
- A merchandiser signs off before anything goes live. The job runs overnight, so the Batch API halves the cost.

## 3 · Architecture
```
Store product feed (specs + photo) -> attribute schema (material, fit, color, use case)
   -> Claude vision via Batch API, with skill/brand-voice/SKILL.md
   -> deterministic checks (required fields, banned claims, length limits) -> one retry with the problems listed
   -> merchandiser spot-check (sample + every flagged item) -> publish + before/after CSV
```

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 20 synthetic products, a Pillow-drawn photo each, merchandiser answer key
python pipeline.py       # runs all 6 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**. Color comes from real pixel analysis with Pillow: it takes the median of the non-background pixels and snaps it to the nearest store swatch. Material, fit and use case come from the spec text, and the copy follows the skill's template.
Set `ANTHROPIC_API_KEY` to send each product's photo as a base64 `image` content block, plus the specs, through the Message Batches API (`common/vision.py`). The SKILL.md text goes into the system prompt.

| Step | What happens | Code / output |
|---|---|---|
| 1 | Export the catalog with each product's photo and specs | `data/catalog_export.csv`, `data/images/` |
| 2 | Define the attribute schema; limits and banned claims are read from the skill | `Enrichment`, `skill/brand-voice/SKILL.md` |
| 3 | Batch-run Claude (vision) to fill attributes and write on-brand copy | `batch_vision_structured()` |
| 4 | Auto-check required fields, banned claims (in any spelling) and length limits; retry failures once | `check()` |
| 5 | Merchandiser spot-checks 5 random products plus every flagged one against her labels, then publishes | `data/merchandiser_key.json` |
| 6 | Write the before/after catalog and the publish feed | `outputs/catalog_before_after.csv`, `publish_feed.json`, `review_queue.json` |

## 5 · Results (offline run on synthetic data)
- Products enriched per merchandiser hour: **6 → 52**. This assumes about 10 minutes per product by hand, versus 2 minutes per spot-check and 10 minutes per held item.
- Filterable fields filled (color, material, fit, use case): **17 of 80 → 78 of 80**
- Color facet correct against the merchandiser's labels: **13 of 20 → 20 of 20**. The supplier data had wrong or missing colors, such as a black hoodie coded navy.
- Material correct: **19 of 20**. The miss has no material in its specs, so it was held for review rather than guessed.
- Banned claims caught before publishing: **3** ("eco friendly", "water-proof", "anti-bacterial", spelled differently from the skill's list). One title over the length limit was fixed on retry.
- Published **19 of 20**; 1 held for the merchandiser
- Search clicks and return reasons need a live A/B test after publishing. As a proxy, 19 of 19 published products now state fit and material in the copy, which addresses the usual "not as described" and "didn't fit" returns.

## 6 · Replay
Photo plus spec sheet, then schema, batch, deterministic checks and a human sample: the same shape works for any listing job, such as real estate, auto parts or marketplace sellers.
Next time I'd have the checker and the skill share the banned list from day one (as here), and A/B test the new copy on search click-through for one category before rolling it out to all SKUs.
