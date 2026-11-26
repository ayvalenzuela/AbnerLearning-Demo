---
name: iceberg
description: Turn any topic into a visual lesson drawn as what you see vs. what's hidden below. Best for hidden factors and depth. Use when the user types /iceberg <topic> or asks for a visual lesson in the iceberg format.
argument-hint: <topic>
---

# /iceberg: what you see vs. what's hidden below

Make a visual lesson about **$ARGUMENTS** as what you see vs. what's hidden below. This format is best for hidden factors and depth.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: an iceberg on water. A small white tip above a waterline, and a much larger pale-blue mass below in a gradient that darkens with depth.
- Above the water, put 3–4 visible or obvious items (what most people notice).
- Below the water, put 6–10 hidden items arranged in 2–3 depth bands (for example "Under the surface", "Deep", "Deepest"), with the less obvious, more fundamental factors placed deeper.
- Label the bands on the left edge and items as short labels inside or beside the berg.
- Add a waterline caption, such as "What you see" above it and "What actually drives it" below.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-iceberg.html`.
