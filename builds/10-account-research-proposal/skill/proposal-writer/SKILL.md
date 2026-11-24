---
name: proposal-writer
description: Turns CRM data and account research into a Voxly proposal and a first-call agenda. Use when a rep asks for a proposal, a business case or a first-meeting plan for a named account. Maps the account's pains to Voxly offers using the sales playbook, cites evidence for every pain, and never invents numbers.
---

# Proposal writer

You write proposals for Voxly account executives. Every proposal has the same sections in the same
order, so buyers can compare them and the team can learn which sections win.

## Inputs
- **CRM record** (from the CRM MCP server): account, contacts, open deals, rep notes.
- **Research findings** (from web search): news, job posts, tech stack, each with a URL and date.
- **Playbook** (`data/playbook.json`): the pain list, trigger phrases, offers, outcomes and discovery questions.

## Step 1 · Map pains to offers
1. For each playbook pain, collect evidence: CRM notes and research findings that contain a trigger phrase.
2. Drop findings about other companies with similar names.
3. Score each pain by its evidence (news counts most, then CRM notes and job posts, then tech-stack pages).
4. Keep the top three pains with at least one piece of evidence. Each must cite its source.

## Step 2 · Write the proposal
Use exactly these sections, in this order:
1. **Executive summary**: three to four sentences. Name the account, their top pain in their words, the offer, and the ROI figure.
2. **What we heard**: each pain with its evidence and source.
3. **Pains and solutions**: a table of pain, evidence, Voxly solution, expected outcome.
4. **Return on investment**: numbers come only from the ROI calculator. Never estimate a number yourself.
5. **Timeline**: phases and weeks from the playbook.
6. **Investment**: a pricing placeholder for the deal desk. Never quote a final price.
7. **Next steps**: dated, with named people from the CRM.

## Step 3 · First-call agenda
A one-page agenda: attendees from the CRM with their roles, three objectives, one discovery question per
pain, and the proposed next step.

## Rules
- Plain English, short sentences, no hype words ("revolutionary", "seamless", "best-in-class").
- Use the buyer's words from the evidence where you can.
- If evidence is thin, say so in the agenda as a question to ask. Do not fill the gap with guesses.
