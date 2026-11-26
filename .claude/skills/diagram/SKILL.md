---
name: diagram
description: Turn any topic into a visual lesson drawn as the labelled anatomy of one object. Best for the parts of a single thing. Use when the user types /diagram <topic> or asks for a visual lesson in the diagram format.
argument-hint: <topic>
---

# /diagram: the labelled anatomy of one object

Make a visual lesson about **$ARGUMENTS** as the labelled anatomy of one object. This format is best for the parts of a single thing.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a clean scientific-illustration style. One large, centred drawing of the single object (outline plus soft fills) on a white or light background.
- Label 6–12 parts with straight leader lines fanning out to labels on both sides, aligned in neat columns. Lines must not cross.
- Each label has the part name in bold plus one short line on its function.
- Optionally add one magnified circular inset of a small but important part.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-diagram.html`.
