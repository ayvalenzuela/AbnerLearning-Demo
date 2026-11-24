# Build 10 · B2B sales — Account research to proposal

**Pattern:** Skill + MCP · **Claude features:** Agent Skill (`SKILL.md`), MCP server, web search server tool, structured output (JSON schema)

## 1 · Situation
An enterprise UCaaS sales team. Reps spend most of a day researching each account and building a proposal from scratch. No two proposals look alike, so nobody can tell which parts actually win deals.

## 2 · Constraints
- CRM access is read-only and goes through one MCP server, so IT can audit what the model can see.
- Every pain in the proposal cites a source the rep can check: a CRM note or a dated web page.
- ROI numbers come from a calculator in code, never from the model, and each line shows its formula.
- The rep edits and sends. Nothing goes to a buyer automatically, and pricing stays a placeholder for the deal desk.

## 3 · Architecture
```
CRM --(MCP server: crm_mcp_server.py)--> account, contacts, open deals
Web search (news, hiring, tech stack) --> findings with URLs, look-alike companies dropped
Proposal Skill (skill/proposal-writer/SKILL.md) + playbook --> top 3 pains -> offers
ROI calculator (code) --> Word proposal + first-call agenda, filed per territory
Rep edits and sends --> win/loss log --> which sections win --> Skill update
```

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # fictional CRM, search index, playbook, rep's answer key, win/loss log
python pipeline.py       # runs all 6 steps, writes outputs/
```
Proposals land in `outputs/territories/<territory>/<account>/proposal.docx`, next to `first_call_agenda.md`.

With no API key it runs in **OFFLINE mode**: research reads a local synthetic search index, and the pain mapping scores playbook trigger phrases with the source weights the Skill describes. Set `ANTHROPIC_API_KEY` to use the web search tool (`common/web_research.py`) and let Claude follow the Skill.

To give Claude Desktop or Claude Code the same CRM, register the server (stdio): `python crm_mcp_server.py`. Its tools are `list_accounts`, `get_account`, `list_contacts` and `list_open_deals`.

| Step | What happens | Code |
|---|---|---|
| 1 | Pull account, contacts and open deals through the CRM MCP server | `crm_mcp_server.py` |
| 2 | Three searches per account (news, hiring, tech stack); drop results about other companies | `common/web_research.py` |
| 3 | The Skill maps evidence to playbook pains and offers; top three per account | `skill/proposal-writer/SKILL.md`, `data/playbook.json` |
| 4 | Code computes ROI; Claude drafts the words; python-docx renders the branded proposal and the agenda | `render_proposal()`, `render_agenda()` |
| 5 | Rep edits and sends (simulated); the win/loss log gives each section's win-rate lift | `outputs/section_win_rates.json` |
| 6 | Pain picks scored against the rep's own read of each account | `data/answer_key.json` |

## 5 · Results (offline run on synthetic data)
- Proposals: **3 accounts, 3 territories, the same 7 sections in the same order**, each pain cited
- Pain match with the rep's own read: **8 of 9 (89%)**. The miss: Meridian's hold-time article ranked fifth for a broad "news" search and was cut, so the Skill picked new clinics instead.
- Hours per proposal: **6.3 → 1.0** in the log; this run needed **24 minutes** of rep edits per proposal on average
- Meetings booked: **50% → 70%**; win rate: **30% → 60%** (Skill vs freeform proposals in a **simulated** 80-proposal win/loss log, so these show the method, not a real result)
- Section with the biggest win-rate lift: the pains-and-solutions table (+42 points). The company overview section costs 24 points, and case studies help, so the next Skill version adds a case study and drops the overview.

## 6 · Replay
Reuse: "the Skill holds the playbook, MCP holds the data, code holds the numbers" fits any repeatable document: QBRs, renewal briefs, RFP answers.
Next time I'd run one search per playbook pain instead of one broad news search, block pains backed by only a tech-stack page, and weight pain scores with the win/loss log.
