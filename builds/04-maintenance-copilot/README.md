# Build 04 · Manufacturing — Maintenance copilot

**Pattern:** RAG + MCP · **Claude features:** structured output (JSON schema), MCP tools (Model Context Protocol), Agent SDK in production

## 1 · Situation
A bottling plant with two lines. When a filler or capper stops, a technician digs through PDF manuals and old work
orders, then tries causes in the order the manual lists them, while the line loses output every minute it is down.
Fixes that worked last month are buried in the CMMS free text.

## 2 · Constraints
- The CMMS is the system of record. The copilot reads and writes it only through a narrow MCP server with two tools, running as a plant service account.
- Every suggestion must cite the manual section or work order it came from, so a technician can check it on the tablet.
- Lockout/tagout and sanitation SOPs always come first, before any repair step.
- The answer has to get better as fixes are logged, without retraining anything.

## 3 · Architecture
```
Manuals + SOPs -> chunk by machine and fault code -> vector index (TF-IDF stand-in here)
CMMS work orders <-> cmms_mcp_server.py (get_work_order_history, create_work_order)
Sensors + alarms (historian / PLC tags)
   -> Claude (Agent SDK in production): ranked causes, steps, sources
   -> tablet / Teams chat -> technician fixes -> create_work_order -> next answer improves
```
`cmms_mcp_server.py` is a real MCP server (the `mcp` Python SDK; `MCPServer` in mcp 2.x, `FastMCP` in 1.x) backed by
SQLite. Run it with `python cmms_mcp_server.py` (stdio) or register it with `claude mcp add cmms -- python cmms_mcp_server.py`.
The pipeline lists its tools and calls them through an in-process MCP client, the same protocol an Agent SDK agent
uses. In production the two tools wrap the CMMS vendor's API and the retrieval uses a real embedding model and vector store.

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 3 fictional manuals, SOPs, 23 work orders, sensor + alarm data, 8 past incidents
python pipeline.py       # runs all 7 steps, writes outputs/ (including outputs/cmms.db)
```
With no API key it runs in **OFFLINE mode**: a rule-based stand-in ranks causes from the manual order, similar past
fixes (recency weighted) and the live sensor readings, returning the same `Diagnosis` schema. Set `ANTHROPIC_API_KEY`
to run the identical pipeline against Claude.

| Step | What happens | Code / output |
|---|---|---|
| 1 | Index manuals and SOPs, chunked by machine and fault code | `build_index()`, `common/retrieval.py` |
| 2 | MCP server for the CMMS: read history, create orders | `cmms_mcp_server.py` |
| 3 | The technician describes the fault; pull docs, past fixes and sensors | `gather()` |
| 4 | Claude ranks likely causes and steps, with sources cited | `diagnose()` |
| 5 | The fix is logged to the CMMS through the MCP tool | `create_work_order` |
| 6 | A similar fault on the other line: the logged fix now ranks first | `pipeline.py` |
| 7 | Replay 8 past incidents against technician-confirmed causes | `outputs/replay.json` |

## 5 · Results (offline run on synthetic data)
- Mean time to repair: **128 min → 62 min** (replay estimate: search time + 20 min per cause checked + repair time)
- First-time fixes: **3 of 8** following the manual order → **8 of 8** with the copilot
- Repeat failures: **3 of 23** past work orders were repeats within 14 days; wrong first fix (the usual cause of repeats) **5 of 8 → 0 of 8** in the replay
- Write-back effect: top-1 **6 of 8** before the O-ring fix was logged → **8 of 8** after. The first answer this morning ranked "clogged nozzle screen" first, which was wrong; after one logged fix the same symptom on Line 1 returned the O-ring fix at #1.
- Caveat: 8 incidents is a small, synthetic test set, and two of them are the same O-ring problem. Treat the numbers as a demonstration of the method, not a forecast.

## 6 · Replay
Reuse docs-by-RAG plus system-of-record-by-MCP for any field-service or IT-ops desk: the manual says what can go wrong, the history says what actually did.
Next time I'd make logging the confirmed root cause a one-tap step for technicians, because that write-back is what makes the next answer better.
