# Build 01 · Telecom / UCaaS — Call QA and coaching engine

**Pattern:** Workflow + Batch API · **Claude features:** structured output (JSON schema), Message Batches API

## 1 · Situation
A 40-rep UCaaS sales floor. Managers hear about 2% of calls, so coaching is random and compliance misses slip through.

## 2 · Constraints
- Recordings contain customer PII, so the data stays in the company's tenant.
- Reps must be able to see *why* they got a score, so every criterion quotes evidence from the call.
- The work can wait overnight, so the Batch API (50% cheaper) beats real-time calls.

## 3 · Architecture
```
VoIP recordings -> Speech-to-text -> Claude Batch API (rubric as JSON schema)
   -> schema validation -> n8n -> CRM note (score + 3 tips) -> manager spot-check (eval + tuning)
```

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 12 synthetic calls + a manager's hand scores
python pipeline.py       # runs all 6 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**: a rule-based stand-in with the same schema, clearly labelled.
Set `ANTHROPIC_API_KEY` to run the identical pipeline against Claude.

| Step | What happens | Code |
|---|---|---|
| 1 | Load yesterday's transcribed calls | `pipeline.py` |
| 2 | Sales leaders' rubric becomes a Pydantic schema (`CallScore`) | `pipeline.py` |
| 3 | Every call scored in one batch (`client.messages.batches.create`) | `common/claude.py` |
| 4 | Score + three coaching tips posted to the CRM record | `outputs/crm_notes.json` |
| 5 | Manager's hand scores used as the answer key | `data/manager_scores.json` |
| 6 | Prompt tuned with 3 anchor calls, then re-scored | `pipeline.py` |

## 5 · Results (offline run on synthetic data)
- Calls scored: **12 of 12 (100%)**, versus about 2% reviewed by hand
- Agreement with the manager: **33% → 92%** after one tuning pass
- Compliance issues caught: **5** (misleading recording and discount statements)

## 6 · Replay
Reuse the rubric-as-schema plus batch pattern for any "review every X" job: tickets, emails, chats.
Next time I'd calibrate with anchor calls from day one, and track whether reps act on the tips.
