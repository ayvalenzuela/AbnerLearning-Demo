---
name: blueprint
description: Turn any topic into a visual lesson drawn as a technical blueprint with labelled parts. Best for how a machine or system works. Use when the user types /blueprint <topic> or asks for a visual lesson in the blueprint format.
argument-hint: <topic>
---

# /blueprint: a technical blueprint with labelled parts

Make a visual lesson about **$ARGUMENTS** as a technical blueprint with labelled parts. This format is best for how a machine or system works.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: an engineering drawing. Deep blue background (`--paper` about #0f3a6b), white or pale-cyan line work, a faint 40px grid, and monospace or condensed labels.
- Draw the main system as clean outlines: a front or side elevation, with an optional small inset detail view.
- Label 6–10 parts with leader lines ending in small dots. Number them (1, 2, 3…), and add a parts legend box in the bottom-right listing number, name and a one-line function.
- Add 1–3 dimension or spec callouts such as pressure, temperature or flow, with arrows showing direction of flow or motion.
- Add a title block in the corner (drawing title, "Sheet 1 of 1", scale "NTS").

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-blueprint.html`.
