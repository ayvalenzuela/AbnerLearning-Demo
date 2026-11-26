---
name: handwritten
description: Turn any topic into a visual lesson drawn as notebook-style notes with highlights. Best for revision. Use when the user types /handwritten <topic> or asks for a visual lesson in the handwritten format.
argument-hint: <topic>
---

# /handwritten: notebook-style notes with highlights

Make a visual lesson about **$ARGUMENTS** as notebook-style notes with highlights. This format is best for revision.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a ruled notebook page (pale cream paper, light blue rules, a red margin line) with a handwriting font such as `Caveat` or `Patrick Hand` from Google Fonts, and a cursive fallback.
- Content: a page heading underlined by hand, then 3–5 short sections using bullets, arrows (→), boxed definitions and a mini doodle or two.
- Use highlighter strokes (semi-transparent yellow, green or pink rectangles behind words) only on the facts that must be memorised.
- End with a "Quick quiz" box of 3 questions, and put the answers upside down or in small text at the bottom of the page.
- Slightly vary the rotation of elements (±1–2°) so the page feels hand-made, but keep everything legible.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-handwritten.html`.
