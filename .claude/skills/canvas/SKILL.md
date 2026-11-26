---
name: canvas
description: Turn any topic into a visual lesson drawn as a whiteboard full of sticky notes. Best for business ideas and planning. Use when the user types /canvas <topic> or asks for a visual lesson in the canvas format.
argument-hint: <topic>
---

# /canvas: a whiteboard full of sticky notes

Make a visual lesson about **$ARGUMENTS** as a whiteboard full of sticky notes. This format is best for business ideas and planning.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a whiteboard (off-white with a soft shadow frame) divided into labelled zones, with square sticky notes (yellow, pink, blue, green) at slight random tilts.
- Default zones follow a business-model canvas: Customers, Problem, Value proposition, Channels, Revenue, Costs, Key partners, Key activities, and Metrics. For a non-business topic, choose 6–9 zones that fit (for example Goals, Risks, Ideas, Next steps).
- Put 2–4 stickies per zone, each 3–8 words in a marker-style font (`Permanent Marker` or `Kalam`).
- Add a few hand-drawn arrows connecting related stickies across zones, and a "Next 3 actions" column on the right.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-canvas.html`.
