---
name: contract-review
description: Review NDAs and MSAs against the firm's negotiation playbook. Marks each clause OK, negotiate or escalate with a reason, proposes fallback language from the clause library, and produces a redlined Word document plus a one-page issues memo. Use when asked to review, redline or mark up an NDA or MSA.
---

# Contract review

Apply the firm's playbook the same way every time. You are reviewing for the **service provider**.

## Files in this Skill
- `playbook.json`: for each clause type, our **position**, the **fallback** we will accept, and the **walk-away** condition, plus a machine-readable `check` block.
- `clause_library.json`: the approved fallback wording for each clause type. Use it verbatim; do not draft new language.
- `scripts/redline.py`: builds the redlined `.docx` (original struck through, fallback inserted, a comment with the reason) and the issues memo.

## Steps
1. Split the contract into clauses by heading. Map each heading to a playbook clause type. If a clause does not map, leave it out of the review and list it in the memo as "not covered by playbook".
2. For each mapped clause, extract the deciding value (years, months, days, jurisdiction, mutual or one-sided) and quote the sentence it came from.
3. Decide:
   - **OK** if it meets the position.
   - **escalate** if it meets the walk-away condition, or if you cannot read the value with confidence.
   - **negotiate** otherwise, and propose the clause library fallback.
4. Give a one-sentence reason that names the playbook rule, for example "Term of 5 years exceeds the 3-year position; below the 7-year walk-away."
5. Run `scripts/redline.py` to write `<contract_id>_redline.docx` and `<contract_id>_memo.md`.

## Rules
- Never accept a walk-away term on your own. Escalate it.
- Never invent fallback wording. If the library has none, escalate.
- Output must match the `ContractReview` schema: one entry per clause with `clause_id`, `clause_type`, `extracted_value`, `decision`, `reason`.
