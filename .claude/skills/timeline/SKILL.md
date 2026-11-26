---
name: timeline
description: Turn any topic into a visual lesson drawn as key dates and events in order. Best for history and milestones. Use when the user types /timeline <topic> or asks for a visual lesson in the timeline format.
argument-hint: <topic>
---

# /timeline: key dates and events in order

Make a visual lesson about **$ARGUMENTS** as key dates and events in order. This format is best for history and milestones.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a horizontal timeline (or vertical, if more than 10 events) on a light background, with a thick axis, era bands shaded behind it, and event markers alternating above and below the axis to avoid overlap.
- Show 6–12 events, each with a year or date in bold, a short title and a one-sentence "why it mattered".
- Spacing should be roughly proportional to time where feasible. If you compress any gap, show it with a break symbol (≈).
- Only include dates you are confident of. Use "c." for approximate ones.
- End with a "Today" marker if the story continues to the present.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-timeline.html`.
