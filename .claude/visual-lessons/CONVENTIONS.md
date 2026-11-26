# Visual lesson conventions

Shared rules for the 15 visual-lesson skills (`/blueprint`, `/roadmap`, `/handwritten`, `/decision-matrix`, `/flowchart`, `/infographic`, `/canvas`, `/layers`, `/cycle`, `/diagram`, `/sketchnotes`, `/iceberg`, `/exploded-view`, `/tree`, `/timeline`). Each skill sets the format. This file sets everything they have in common.

## Input
The argument is the topic, for example `coffee`, `how DNS works` or `our new refund process`. It can also add an audience ("for new hires") or a size ("keep it to 5 steps").
- If there is no topic, ask for one in a single short question and stop.
- If the topic is about the user's own team or process and you lack the facts, ask for them, or say in the page footer which parts are general assumptions. Never invent internal details and present them as fact.

## Content
1. **Research before drawing.** Decide the 5–12 facts that matter most for this format, and no more. A lesson that teaches one idea clearly beats one that crams in twenty.
2. **Be accurate.** Use only figures, dates and names you are confident of. Round numbers honestly ("about 70%"), and leave out anything you're unsure of rather than guessing.
3. **Write tight labels.** Aim for 2–6 words per label and 1–2 short sentences per note. Use the reader's words, not jargon.
4. **Include one takeaway.** Every lesson ends with one line that starts "Key takeaway:".

## Output
- Write one self-contained file to `lessons/<topic-slug>-<format>.html`, for example `lessons/coffee-iceberg.html`. Create `lessons/` if it does not exist. If the file already exists, add `-2`, `-3` and so on rather than overwriting it.
- **Draw the visual as hand-written inline SVG** in a `viewBox` (about 1200×800, or taller when needed) with `width:100%; height:auto` (see Legibility for small screens). Use no external images and no chart libraries. Google Fonts `<link>` tags are the only allowed external requests, and the page must still read well without them.
- **Page structure:** a `<title>` (2–4 words), an `h1` with the topic, a one-line subtitle naming the format and what it is best for, the SVG, an optional short "Notes" list under it when the format needs more text than fits in the picture, the key takeaway, and a small footer saying "Generated with /<format>".
- **Theming:** define every color as a CSS custom property on `:root` and use the variables inside the SVG (`fill="var(--ink)"` or classes). Give `body` an explicit background. Add a dark-mode override under `@media (prefers-color-scheme: dark)`. Pick a palette that suits the format (each skill suggests one) and limit it to 1 accent plus at most 3 supporting colors.
- **Legibility:** SVG text at least 14px in viewBox units (labels 16–20, titles 28+). No overlapping text, and every label sits clearly next to or connected to what it names, using leader lines where needed. Keep a 16px side gutter, and make sure the page has no horizontal scroll on a phone. Wrap the SVG in `<div class="figure">` with `overflow-x:auto`, give the SVG `min-width: 760px` so the text stays readable, and show a "Swipe sideways to see the whole picture" hint under 760px. The figure scrolls but the page does not.
- **Accessibility:** set `role="img"` and an `aria-label` on the SVG that summarizes the whole visual in one sentence. Add `<title>` elements on the main shapes.

## Check before finishing
Open the file with Playwright (`require('playwright')`, `chromium.launch()`) and take a 1x screenshot to your scratchpad at 1280px wide and at 390px wide. Look at both. Fix overlapping or clipped text, labels pointing at the wrong thing, and empty or lopsided areas. Then reply with:
- the file path
- a two-line summary of what the lesson shows
- one suggestion for which other format would show a different side of the topic
