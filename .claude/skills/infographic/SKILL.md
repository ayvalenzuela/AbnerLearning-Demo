---
name: infographic
description: Turn any topic into a visual lesson drawn as a clean visual summary. Best for quick overviews. Use when the user types /infographic <topic> or asks for a visual lesson in the infographic format.
argument-hint: <topic>
---

# /infographic: a clean visual summary

Make a visual lesson about **$ARGUMENTS** as a clean visual summary. This format is best for quick overviews.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a modern editorial poster on a light background, with one bold accent color and a strong headline at the top.
- Sections, top to bottom: 3–4 big-number stat tiles (number, short label and an icon built from simple SVG shapes), a "How it works in 3 steps" strip, a simple bar or proportion graphic for one comparison, and a "Did you know?" fact.
- Every number shown must be real and approximately right. If you can't stand behind a number, use a qualitative fact instead.
- Keep a clear grid, generous whitespace and consistent icon style.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-infographic.html`.
