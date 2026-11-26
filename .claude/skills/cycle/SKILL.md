---
name: cycle
description: Turn any topic into a visual lesson drawn as a loop of stages that repeats. Best for life cycles and routines. Use when the user types /cycle <topic> or asks for a visual lesson in the cycle format.
argument-hint: <topic>
---

# /cycle: a loop of stages that repeats

Make a visual lesson about **$ARGUMENTS** as a loop of stages that repeats. This format is best for life cycles and routines.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a circular loop of 4–8 stages evenly spaced around a ring, with curved arrows between them going clockwise, on a light background.
- Each stage gets a circle node with a simple icon or number, a stage name and a 1-sentence description placed outside the ring.
- In the centre, put the cycle's name and its typical duration or frequency (for example "about 9 months, yearly").
- If the cycle has an entry point or an exit or branch, mark it clearly with a separate arrow.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-cycle.html`.
