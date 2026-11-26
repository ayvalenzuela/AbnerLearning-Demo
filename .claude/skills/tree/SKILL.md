---
name: tree
description: Turn any topic into a visual lesson drawn as a family tree of categories and branches. Best for types and groups. Use when the user types /tree <topic> or asks for a visual lesson in the tree format.
argument-hint: <topic>
---

# /tree: a family tree of categories and branches

Make a visual lesson about **$ARGUMENTS** as a family tree of categories and branches. This format is best for types and groups.

## First
Read `.claude/visual-lessons/CONVENTIONS.md` in the repository root and follow it for input handling, content rules, file output, theming and the final screenshot check. This file only sets the format.

## Format
- Look: a top-down hierarchy tree on a light background. A root node at the top, then 2–4 levels of child nodes connected with elbow lines.
- The root is the topic. Level 1 holds the main categories (2–5), and lower levels hold types or examples. Keep at most about 25 nodes.
- Color each level-1 branch distinctly and let its descendants carry a lighter tint of the same color.
- Leaf nodes can carry a one-line distinguishing trait. Siblings must be split by one consistent criterion, which should be stated in a small caption ("Grouped by: …").

## Fit check
If the topic does not suit this format (for example a /timeline for something with no history), say so in one line and suggest the format that fits better, then make the best version you can unless the user says otherwise.

Save as `lessons/<topic-slug>-tree.html`.
