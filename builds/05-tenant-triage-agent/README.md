# Build 05 · Property management — Tenant request triage agent

**Pattern:** Agent + approvals · **Claude features:** structured output (triage schema), tool use (agent loop), human approval in Slack

## 1 · Situation
A 240-unit apartment portfolio run by a two-person office. Tenant emails and texts pile up in one inbox: simple questions wait days, and an urgent leak sent on a Saturday night can sit unread until Monday.

## 2 · Constraints
- Emergencies must reach a human within minutes. The agent pages on-call staff first and acts second.
- Policy answers must come from the lease or FAQ, with the source quoted, so staff can stand behind them.
- The agent never commits vendor spend over $500. Those work orders wait for a manager's Approve click in Slack. Emergency call-outs skip the queue by written policy and are reviewed afterwards.
- The tools are narrow (search policies, read ledger, draft work order, book slot, page, request approval, reply). The agent can't edit leases or move money.

## 3 · Architecture
```
Email + SMS inbox -> Claude triage (question / repair / emergency / billing)
   -> agent with tools: lease + FAQ search (RAG), tenant ledger, work-order API, vendor calendar
   -> on-call pager (emergencies, within 1 minute)
   -> Slack approval queue (spend over $500) -> reply to tenant on the same channel
```

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 15 synthetic messages, lease, FAQ, vendors, ledger, answer key
python pipeline.py       # runs all 7 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**. Triage is rule-based, and a deterministic planner picks the same tools Claude would, based on the message and earlier tool results. The tools are real Python functions, so retrieval, estimates, slots, pages and Slack messages are all computed from the data.
Set `ANTHROPIC_API_KEY` and the same pipeline runs against Claude. The agent loop is in `common/agent.py`: it calls `client.messages.create(..., tools=TOOLS)`, loops while `stop_reason == "tool_use"`, and returns every tool result in one user message.

| Step | What happens | Code / output |
|---|---|---|
| 1 | Read one week of email + SMS (10 of 15 after hours) | `data/inbox.json` |
| 2 | Classify each message: question, repair, emergency, billing | `ask_structured(schema=Triage)` |
| 3 | Answer questions and billing from the lease, FAQ and ledger, with the source | `search_policies`, `get_tenant_ledger` |
| 4 | For repairs, draft a work order with an estimate and book the vendor's earliest slot | `outputs/work_orders.json` |
| 5 | Page on-call staff at once for any emergency (first tool call) | `outputs/pages.json` |
| 6 | Manager approves spend over $500 in Slack (Block Kit message with buttons) | `outputs/slack_approvals.json` |
| 7 | Score triage against a hand-labelled answer key, and time every reply | `data/answer_key.json` |

The full log of every tool call and reply is in `outputs/triage_log.json`.

## 5 · Results (offline run on synthetic data)
- Median first response: **13.0 hours → 1 minute** (before = office staff working the inbox 9–5 on weekdays, about 3 working hours behind)
- After-hours coverage: **0 of 10 → 10 of 10** after-hours messages answered before the office opens
- Emergencies routed: **2 of 2** paged within 1 minute (the old process left the Saturday-night leak waiting up to 37 hours)
- Triage accuracy against the answer key: **15 of 15**. All 8 question and billing answers cite the lease or FAQ.
- 7 work orders drafted; **2** over the limit went to Slack, and none were booked without approval

## 6 · Replay
Classify, then an agent with narrow tools, then a human approval over a threshold: the same shape works for any service inbox (IT helpdesk, facilities, field service).
Next time I'd connect the real work-order API and pager first, measure how often staff edit the agent's replies, and add a "not sure" category so borderline messages go to a human.
