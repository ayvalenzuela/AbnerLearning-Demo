---
name: flowchart
description: Turn any topic into a visual lesson drawn as steps with decisions and branches. Best for processes with options. Use when the user types /flowchart <topic> or asks for a visual lesson in the flowchart format.
argument-hint: <topic>
---

# /flowchart: steps with decisions and branches

Make a visual lesson about **$ARGUMENTS** as steps with decisions and branches. This format is best for processes with options.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a standard flowchart on a light background. Rounded pills for start and end, rectangles for actions, diamonds for yes/no decisions, and arrows with arrowheads.
- Flow top-to-bottom, with branches going left or right. Label every arrow out of a diamond "Yes" or "No" (or the option name).
- Use 8–14 nodes and 2–4 decisions. Every path must reach an end. Avoid crossing lines, and reroute with elbow connectors if needed.
- Use one accent color for the "happy path" and neutral for alternate branches.

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-flowchart.html`.
