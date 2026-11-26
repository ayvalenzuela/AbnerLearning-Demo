---
name: roadmap
description: Turn any topic into a visual lesson drawn as a winding path with numbered stops. Best for step-by-step journeys. Use when the user types /roadmap <topic> or asks for a visual lesson in the roadmap format.
argument-hint: <topic>
---

# /roadmap: a winding path with numbered stops

Make a visual lesson about **$ARGUMENTS** as a winding path with numbered stops. This format is best for step-by-step journeys.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a friendly illustrated map on a warm light background, with one thick winding road (an S-curve path) from START (bottom-left) to FINISH (top-right).
- Place 5–8 numbered circular stops along the road. Next to each, add a short stop name and a 1-sentence "what happens here".
- Mark 1–2 stops as milestones (a flag icon) and, where it helps, one "watch out" hazard sign beside the road for a common mistake.
- Steps must be in true order and each stop must be one distinct action or stage.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-roadmap.html`.
