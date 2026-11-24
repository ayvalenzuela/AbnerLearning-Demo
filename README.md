# AI Build Portfolio — Abner Yegres Valenzuela

Ten working AI builds across ten industries, each following the same method:
**discover → map → choose the simplest pattern → architect → prototype → evaluate → prove.**

Every build is runnable Python on synthetic data, and each one has a step-by-step trace, a case-study README, and a short screen recording.

| # | Industry | Build | Pattern | Video |
|---|---|---|---|---|
| 01 | Telecom / UCaaS | [Call QA and coaching engine](builds/01-call-qa-coaching) | Workflow + batch | [mp4](site/videos/build-01.mp4) |
| 02 | Healthcare | [Prior-auth packet assistant](builds/02-prior-auth-assistant) | RAG + human review | [mp4](site/videos/build-02.mp4) |
| 03 | Legal | [Contract review Skill](builds/03-contract-review-skill) | Skill | [mp4](site/videos/build-03.mp4) |
| 04 | Manufacturing | [Maintenance copilot](builds/04-maintenance-copilot) | RAG + MCP | [mp4](site/videos/build-04.mp4) |
| 05 | Property management | [Tenant request triage agent](builds/05-tenant-triage-agent) | Agent + approvals | [mp4](site/videos/build-05.mp4) |
| 06 | Accounting | [Month-end reconciliation](builds/06-month-end-reconciliation) | Claude Code + AI step | [mp4](site/videos/build-06.mp4) |
| 07 | E-commerce | [Catalog enrichment pipeline](builds/07-catalog-enrichment) | Batch + structured output | [mp4](site/videos/build-07.mp4) |
| 08 | Logistics | [Shipment exception agent](builds/08-shipment-exception-agent) | Event-driven agent | [mp4](site/videos/build-08.mp4) |
| 09 | Insurance | [Claims intake and extraction](builds/09-claims-intake) | Vision + workflow | [mp4](site/videos/build-09.mp4) |
| 10 | B2B sales | [Account research to proposal](builds/10-account-research-proposal) | Skill + MCP | [mp4](site/videos/build-10.mp4) |

## Run any build
```bash
pip install -r requirements.txt
cd builds/01-call-qa-coaching
python make_data.py && python pipeline.py
```
- **Offline mode (default):** with no API key, each Claude step is handled by a rule-based stand-in that returns the same schema. The whole pipeline runs end to end, and every output is labelled OFFLINE.
- **Live mode:** `export ANTHROPIC_API_KEY=...`, then run the same command. The same code calls Claude: structured outputs, the Batches API, vision, citations, tool use and web search.

All data is synthetic. No real customer, patient or client records are used.

## Layout
- `common/`: shared Claude helpers (structured output, batch, vision, citations, agent loops, retrieval, web research)
- `builds/NN-*/`: one folder per build, each with `make_data.py`, `pipeline.py`, a README (situation, constraints, architecture, demo, results, replay) and `outputs/`
- `site/`: the portfolio page (`index.html`, which reads `traces.json`), `build_site.py` and `record.js` (the Playwright screen recorder)

## Rebuild the site and the videos
```bash
python site/build_site.py
cd site
python -m http.server 8765 &
node record.js 01 02 03 04 05 06 07 08 09 10
```
