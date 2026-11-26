---
name: exploded-view
description: Turn any topic into a visual lesson drawn as a product pulled apart into labelled parts. Best for products and assembly. Use when the user types /exploded-view <topic> or asks for a visual lesson in the exploded view format.
argument-hint: <topic>
---

# /exploded-view: a product pulled apart into labelled parts

Make a visual lesson about **$ARGUMENTS** as a product pulled apart into labelled parts. This format is best for products and assembly.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a technical-illustration exploded view. Product components floated apart along one or two assembly axes (vertical or isometric), joined by dashed alignment lines, on a light grey background.
- Show 6–12 components in true assembly order, each numbered with a callout bubble.
- Add a bill-of-materials list on the side: number, part, material or what it does, and how it attaches (screws in, clips on, slides over).
- Add a small "Assembly order: 1 → N" note and, where relevant, one "fragile" or "replaceable" marker.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-exploded-view.html`.
