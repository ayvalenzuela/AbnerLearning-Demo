---
name: layers
description: Turn any topic into a visual lesson drawn as a cross-section showing each layer. Best for what something is made of. Use when the user types /layers <topic> or asks for a visual lesson in the layers format.
argument-hint: <topic>
---

# /layers: a cross-section showing each layer

Make a visual lesson about **$ARGUMENTS** as a cross-section showing each layer. This format is best for what something is made of.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a cutaway cross-section of the subject (for example a cup, the earth or a tech stack) as stacked layers, each with its own fill color or texture, on a light background.
- Draw 4–8 layers in true order. Make thickness roughly proportional where proportion is meaningful, and say so in a note if not.
- Label each layer on the right with a leader line: name, what it is or does, and one fact (such as share, temperature or thickness).
- Add a small "outside → inside" or "top → bottom" arrow and a scale note.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-layers.html`.
