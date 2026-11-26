---
name: decision-matrix
description: Turn any topic into a visual lesson drawn as options scored side by side. Best for comparing choices. Use when the user types /decision-matrix <topic> or asks for a visual lesson in the decision matrix format.
argument-hint: <topic>
---

# /decision-matrix: options scored side by side

Make a visual lesson about **$ARGUMENTS** as options scored side by side. This format is best for comparing choices.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a clean scoring table drawn in SVG (not an HTML table), with options as columns (3–5) and criteria as rows (4–7).
- Each cell holds a score from 1 to 5 shown as a number plus filled dots, with a cell tint that strengthens with the score (one sequential color ramp).
- Show a weight (×1, ×2, ×3) beside each criterion, and a bold weighted total row at the bottom. Highlight the top option with a "Best for most people" badge.
- Under the SVG, add a "When to pick something else" note, one line per runner-up option.
- Scores must be justified by facts. Where a score is a judgement call, say so in the notes.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-decision-matrix.html`.
