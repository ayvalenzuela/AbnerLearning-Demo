# Build 03 · Legal — Contract review Skill

**Pattern:** Skill · **Claude features:** Agent Skills (SKILL.md + bundled files and scripts), structured output (JSON schema), Message Batches API

## 1 · Situation
A commercial team reviews dozens of NDAs and MSAs a month. Associates redline the same issues by hand, and each
one applies the playbook a little differently, so partners spend their time re-editing redlines instead of
negotiating the few clauses that matter.

## 2 · Constraints
- Client documents are confidential and stay inside the firm's Claude workspace, with one Project per client for context.
- Fallback wording must come verbatim from the approved clause library. The model never drafts new language.
- Walk-away terms always go to a partner. The Skill escalates; it never accepts them.
- Output has to land where lawyers work: a Word redline and a one-page memo.

## 3 · Architecture
```
Firm playbook -> rules (position / fallback / walk-away)
   -> skill/contract-review/  (SKILL.md, playbook.json, clause_library.json, scripts/redline.py)
   -> Claude loaded with the Skill: OK / negotiate / escalate per clause, with a reason
   -> scripts/redline.py: redlined .docx (struck original, inserted fallback, Word comment) + issues memo
   -> partner review (escalations; answer key for testing)
```
The Skill folder is the product. Copy `skill/contract-review/` into `~/.claude/skills/` (Claude Code) or upload it as a
Skill in Claude, and the same instructions, rules and scripts run there. `pipeline.py` loads the same files into the
system prompt so the demo runs through the plain Messages API.

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 10 fictional past contracts, the partner's final calls, 3 associates' past reviews
python pipeline.py       # runs all 6 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**: a rule-based stand-in reads each clause, extracts the deciding value and
applies `playbook.json`, returning the same `ContractReview` schema. Set `ANTHROPIC_API_KEY` to run the identical
pipeline against Claude.

| Step | What happens | Code / output |
|---|---|---|
| 1 | Turn the playbook into rules: position, fallback, walk-away | `skill/contract-review/playbook.json` |
| 2 | Package rules, clause library and scripts as one Skill | `skill/contract-review/SKILL.md` |
| 3 | Mark each clause OK / negotiate / escalate with a reason (one batch) | `pipeline.py` |
| 4 | Redlined .docx and a one-page issues memo per contract | `outputs/redlines/`, `outputs/memos/` |
| 5 | Test on 10 past contracts against what partners changed | `data/partner_answer_key.json` |
| 6 | Compare with how three associates reviewed the same contracts | `data/associate_history.json` |

## 5 · Results (offline run on synthetic data)
- Review time per contract: **89 min → 21 min** (estimate: 10 min associate check + 3 min per flagged clause)
- Consistency: **50%** of clauses where all three associates made the same call → **100%** same call on a rerun
- Partner edits per contract: **1.5 → 0.7**
- Agreement with the partner: **88%** (51 of 58 clauses); **95%** of partner escalations caught
- Where it missed: indemnities written as two one-way sentences (read as one-sided), a cap written as "two times the annual fees" (escalated as unreadable), and two partner judgment calls that depart from the written playbook.

## 6 · Replay
Reuse the playbook-as-Skill pattern for any team that applies written rules to documents: procurement terms, lease abstracts, policy checks.
Next time I'd have partners label 20 contracts before writing the rules, and log every partner override with a reason, so the playbook itself gets better.
