---
name: sketchnotes
description: Turn any topic into a visual lesson drawn as doodles and notes on one page. Best for visual learners. Use when the user types /sketchnotes <topic> or asks for a visual lesson in the sketchnotes format.
argument-hint: <topic>
---

# /sketchnotes: doodles and notes on one page

Make a visual lesson about **$ARGUMENTS** as doodles and notes on one page. This format is best for visual learners.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a lively single-page sketchnote on off-white. Hand-lettered title in a banner, a marker-style font (`Kalam`, `Gaegu` or `Patrick Hand`), 2 accent colors plus black ink, and slightly wobbly strokes (wobbly paths, not perfect rectangles).
- Arrange 5–8 idea clusters across the page, each with a simple doodle icon built from basic SVG shapes, a short heading and 1–2 lines of text.
- Connect clusters with hand-drawn arrows and dotted paths, and use containers: speech bubbles, banners, boxes and clouds.
- Include one "big idea" in a starburst, and add small visual rhythm (stars, dashes, underlines) without clutter.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-sketchnotes.html`.
