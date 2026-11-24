"""Build 04 - Maintenance copilot (Manufacturing). Pattern: RAG + MCP."""
import asyncio, json, re, sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, ask_structured  # noqa: E402
from common.retrieval import TfidfIndex  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import cmms_mcp_server as cmms  # noqa: E402

DATA, OUT = HERE / "data", HERE / "outputs"
NOW = datetime(2026, 11, 24, 6, 10)
CAUSE_RE = re.compile(r"^\d+\. \[(\S+)\] (.+?)\. Steps: (.+?)(?: Sensor sign: (\w+) (below|above) ([\d.]+)\.)?$", re.M)


# ---------- Step 1: index manuals and SOPs by machine and fault code ----------
def build_index() -> TfidfIndex:
    idx = TfidfIndex()
    for f in sorted((DATA / "manuals").glob("*.md")):
        for sec in re.split(r"\n(?=## )", f.read_text()):
            if not sec.startswith("## "):
                continue
            head = sec.splitlines()[0][3:]
            if f.stem == "SOPs":
                idx.add(head.split(" - ")[0], sec, machine="all", fault_code="", kind="sop")
            else:
                mid, rest = head.split(" / ")
                idx.add(f"{mid}/{rest.split(' - ')[0]}", sec, machine=mid, fault_code=rest.split(" - ")[0], kind="manual")
    return idx.build()


# ---------- Step 4: rank likely causes (Claude, with an offline stand-in) ----------
class RankedCause(BaseModel):
    rank: int
    cause_id: str
    cause: str
    likelihood: float = Field(description="0-1, sums to about 1 across causes")
    why: str = Field(description="evidence for this cause: symptom match, past fixes, sensor readings")
    steps: str
    sources: list[str] = Field(description="manual section ids, SOP ids and work order ids used")

class Diagnosis(BaseModel):
    machine_id: str
    line: str
    fault_code: str
    causes: list[RankedCause]
    safety: list[str] = Field(description="SOP steps that apply before touching the machine")

SYSTEM = ("You are a maintenance copilot on a bottling line. Using ONLY the manual sections, SOPs, CMMS work-order "
          "history and live sensor readings provided, rank the likely causes of the fault, most likely first. For each, "
          "give the check/fix steps and cite sources (manual section id, SOP id, work order ids). Weigh past fixes that "
          "match the technician's symptoms and down-rank causes the sensors rule out. Always list the safety SOPs first.")


def offline_rank(ctx: dict) -> Diagnosis:
    """Rule-based stand-in: manual order prior + similar past fixes (recency weighted) + sensor evidence."""
    manual, hist, sensors = ctx["manual_section"], ctx["history"], ctx["sensors"]
    cands = {}
    for i, (cid, cause, steps, tag, op, val) in enumerate(CAUSE_RE.findall(manual["text"])):
        cands[cid] = {"cause": cause, "steps": steps, "score": 0.35 - 0.05 * i, "why": [f"manual #{i + 1}"],
                      "sources": [manual["id"]], "sign": (tag, op, float(val)) if tag else None}
    sim_idx = TfidfIndex()
    for wo in hist:
        sim_idx.add(wo["wo_id"], wo["symptom"])
    sims = {c["id"]: s for s, c in sim_idx.build().search(ctx["description"], k=len(hist))} if hist else {}
    for wo in hist:
        c = cands.setdefault(wo["root_cause_id"], {"cause": wo["root_cause"], "steps": wo["fix_steps"], "score": 0.0,
                                                   "why": ["not in manual"], "sources": [], "sign": None})
        age = (NOW - datetime.fromisoformat(wo["opened"])).days
        rec = 0.5 ** (max(age, 0) / 180)
        c.setdefault("hist", []).append((wo["wo_id"], rec, wo["first_time_fix"], sims.get(wo["wo_id"], 0.0)))
    for cid, c in cands.items():
        h = c.get("hist", [])
        if h:
            freq = 0.12 * sum(rec * (1 + ftf) for _, rec, ftf, _ in h)
            best = max(h, key=lambda x: x[3] * x[1])
            match = 1.2 * best[3] * best[1]
            c["score"] += freq + match
            c["why"].append(f"{len(h)} past fix(es); closest symptom match {best[0]} ({best[3]:.2f})")
            c["sources"] += [w for w, *_ in sorted(h, key=lambda x: -x[3])[:3]]
        if c["sign"]:
            tag, op, val = c["sign"]
            if tag in sensors:
                hit = sensors[tag] < val if op == "below" else sensors[tag] > val
                c["score"] += 0.3 if hit else -0.25
                c["why"].append(f"sensor {tag}={sensors[tag]} {'supports' if hit else 'rules out'} ({op} {val:g})")
    ranked = sorted(cands.items(), key=lambda kv: -kv[1]["score"])
    total = sum(max(c["score"], 0.01) for _, c in ranked)
    return Diagnosis(machine_id=ctx["machine_id"], line=ctx["line"], fault_code=ctx["fault_code"],
                     causes=[RankedCause(rank=i + 1, cause_id=cid, cause=c["cause"],
                                         likelihood=round(max(c["score"], 0.01) / total, 2), why="; ".join(c["why"]),
                                         steps=c["steps"], sources=c["sources"]) for i, (cid, c) in enumerate(ranked)],
                     safety=[f"{s['id']}: {s['text'].splitlines()[1][:110]}" for s in ctx["sops"]])


# ---------- Step 3: gather context for a fault ----------
def gather(idx, machine_id, line, fault_code, description, sensors_df):
    manual = idx.search(f"{machine_id} {fault_code} {description}", k=1, machine=machine_id, kind="manual")[0][1]
    sops = sorted((c for _, c in idx.search("lockout nozzle valve product-contact sanitation " + description, k=2, kind="sop")),
                  key=lambda c: c["id"])  # lockout before sanitation
    history = cmms.get_work_order_history(machine_id, fault_code)
    snap = sensors_df[(sensors_df.machine_id == machine_id) & (sensors_df.line == line)]
    sensors = snap.sort_values("timestamp").groupby("tag")["value"].last().round(2).to_dict()
    return {"machine_id": machine_id, "line": line, "fault_code": fault_code, "description": description,
            "manual_section": manual, "sops": sops, "history": history, "sensors": sensors}


def diagnose(ctx) -> Diagnosis:
    payload = {k: v for k, v in ctx.items()}
    return ask_structured(system=SYSTEM, content=json.dumps(payload, indent=1, default=str), schema=Diagnosis,
                          offline=lambda: offline_rank(ctx))


def show(d: Diagnosis, n=3) -> str:
    return "\n".join(f"#{c.rank} {c.cause} ({c.likelihood:.0%})\n   why: {c.why}\n   sources: {', '.join(c.sources)}"
                     for c in d.causes[:n])


async def mcp_session(calls):
    """Talk to the CMMS MCP server in-process, exactly as an MCP client (Agent SDK, Claude Code) would."""
    from mcp.client import Client
    async with Client(cmms.mcp) as client:
        tools = await client.list_tools()
        results = [await client.call_tool(name, args) for name, args in calls]
    return tools.tools, results


def tool_result(r):
    """Read an MCP CallToolResult: structured content if the server sent it, else the JSON text blocks."""
    if r.structured_content is not None:
        return r.structured_content.get("result", r.structured_content)
    parts = [json.loads(c.text) for c in r.content if c.type == "text"]
    return parts[0] if len(parts) == 1 else parts


def main():
    tr = Trace("04", "Maintenance copilot", OUT)
    tr.arch([
        {"label": "Manuals + SOPs", "kind": "data", "note": "chunked by machine and fault code"},
        {"label": "Sensors + alarms", "kind": "data", "note": "historian / PLC tags"},
        {"label": "CMMS MCP server", "kind": "system", "note": "history + create work order"},
        {"label": "Claude (Agent SDK)", "kind": "ai", "note": "ranked causes with sources"},
        {"label": "Tablet / Teams chat", "kind": "system", "note": "technician's interface"},
        {"label": "Technician", "kind": "human", "note": "fixes, confirms, logs"},
    ])
    tr.story(
        situation="A bottling plant with two lines. When a filler or capper stops, a technician digs through PDFs and old work orders while the line loses about 300 bottles a minute.",
        constraints="The CMMS is the system of record, so the copilot reads and writes it through a narrow MCP server (two tools, plant service account). Answers must cite the manual section or work order they come from. Lockout and sanitation SOPs always come first.",
        replay="Reuse: docs-by-RAG plus system-of-record-by-MCP fits any field-service or IT-ops desk. Next time: get technicians to log the confirmed root cause in one tap, because that write-back is what makes the next answer better.",
        problem_cost="Mean time to repair of about 1.5 hours on E14 faults, much of it searching and trying causes in manual order.",
    )

    # Step 1
    idx = build_index()
    n_seed = cmms.reset_db(DATA / "cmms_seed.json")
    by_kind = {}
    for c in idx.chunks:
        by_kind.setdefault(c["meta"]["kind"], []).append(c["id"])
    tr.step("Index manuals and SOPs, chunked by machine and fault code", kind="io",
            what=f"Split 3 service manuals and the SOP book into {idx.stats()['chunks']} chunks, each tagged with machine and fault code (TF-IDF stand-in for embeddings + a vector store).",
            code=('for sec in re.split(r"\\n(?=## )", manual_md):\n'
                  '    mid, code = parse_heading(sec)\n'
                  '    idx.add(f"{mid}/{code}", sec, machine=mid, fault_code=code, kind="manual")\n'
                  'idx.build()'),
            output={"manual_chunks": by_kind["manual"], "sop_chunks": by_kind["sop"],
                    "sample": idx.chunks[0]["text"][:420]})

    # Step 2
    tools, (hist_res,) = asyncio.run(mcp_session([("get_work_order_history", {"machine_id": "F-200", "fault_code": "E14", "limit": 3})]))
    hist_preview = tool_result(hist_res)
    tr.step("Build an MCP server for the CMMS: read history, create orders", kind="code",
            what=f"cmms_mcp_server.py exposes two tools over MCP, backed by SQLite seeded with {n_seed} work orders; an MCP client listed the tools and called one.",
            code=('mcp = MCPServer("cmms")  # FastMCP in mcp 1.x\n\n'
                  '@mcp.tool()\n'
                  'def get_work_order_history(machine_id: str, fault_code: str, limit: int = 20) -> list[dict]:\n'
                  '    return db.execute("SELECT * FROM work_orders WHERE machine_id=? AND fault_code=? ...")\n\n'
                  '@mcp.tool()\ndef create_work_order(machine_id, line, fault_code, symptom, root_cause, ...) -> dict'),
            output={"tools": {t.name: ", ".join(t.input_schema["properties"]) for t in tools},
                    "call get_work_order_history(F-200, E14, limit=3)": [
                        f"{w['wo_id']} {w['opened'][:10]} {w['line']}: {w['root_cause']} (first-time fix: {w['first_time_fix']})"
                        for w in hist_preview]})

    # Step 3
    msg = ("Line 2 filler F-200 is down on E14. Fill weights running low on nozzle 3 and product is dripping "
           "from nozzle 3 after the fill.")
    alarms = pd.read_csv(DATA / "alarms.csv")
    sensors_df = pd.read_csv(DATA / "sensors.csv")
    machine = re.search(r"\b([A-Z]-\d+)\b", msg)[1]
    line = f"Line {re.search(r'[Ll]ine (\d)', msg)[1]}"
    code_m = re.search(r"\bE\d{2}\b", msg)
    fault = code_m[0] if code_m else alarms[(alarms.machine_id == machine) & (alarms.line == line)].iloc[-1]["code"]
    active = alarms[(alarms.machine_id == machine) & (alarms.line == line)].iloc[-1].to_dict()
    ctx = gather(idx, machine, line, fault, msg, sensors_df)
    tr.step("The technician describes the fault; pull docs and past fixes", kind="io",
            what=f"From the chat message and the live alarm, the copilot pulled the {ctx['manual_section']['id']} manual section, {len(ctx['sops'])} SOPs, {len(ctx['history'])} past work orders and the latest sensor readings.",
            code=("manual = idx.search(f\"{machine} {fault} {msg}\", k=1, machine=machine, kind=\"manual\")\n"
                  "sops = idx.search(\"lockout ... \" + msg, k=2, kind=\"sop\")\n"
                  "history = cmms.get_work_order_history(machine, fault)   # MCP tool\n"
                  "sensors = latest reading per tag for (machine, line)"),
            output={"tech_message": msg, "active_alarm": f"{active['timestamp']} {active['machine_id']} {active['line']} {active['code']}",
                    "parsed": f"machine={machine}, line={line}, fault_code={fault}",
                    "manual_section": ctx["manual_section"]["id"], "sops": ", ".join(s["id"] for s in ctx["sops"]),
                    "past_work_orders": ", ".join(w["wo_id"] for w in ctx["history"]),
                    "sensors": ", ".join(f"{k}={v}" for k, v in ctx["sensors"].items())})

    # Step 4
    d1 = diagnose(ctx)
    tr.step("Rank likely causes and steps, with sources cited", kind="ai",
            what=f"Claude ranked {len(d1.causes)} causes: past fixes that match the symptom move up, and the supply-pressure cause drops because the sensor reads normal.",
            code=("diag = ask_structured(system=SYSTEM, content=json.dumps(ctx), schema=Diagnosis)\n"
                  "# RankedCause: rank, cause, likelihood, why, steps, sources\n"
                  "# prod: Agent SDK agent with the CMMS MCP server attached, answering in Teams"),
            output="Safety first:\n  " + "\n  ".join(d1.safety) + "\n\n" + show(d1, 4))

    # Step 5: the technician fixes it and logs the fix through the MCP server
    finding = json.loads((DATA / "tech_finding.json").read_text())
    wo_args = {"machine_id": machine, "line": line, "fault_code": fault, "symptom": "fill weight low on nozzle 3, product dripping from nozzle 3 after the fill",
               "opened": NOW.isoformat(timespec="minutes"),
               **{k: finding[k] for k in ("root_cause_id", "root_cause", "fix_steps", "parts", "minutes_down", "first_time_fix", "technician")}}
    _, (created,) = asyncio.run(mcp_session([("create_work_order", wo_args)]))
    created = tool_result(created)
    rank_found = next((c.rank for c in d1.causes if c.cause_id == finding["root_cause_id"]), None)
    tr.step("Log the fix to the CMMS so the next answer improves", kind="human",
            what=f"The technician tried the #1 suggestion ({finding['tried_first']}), then found a cause the manual does not cover and logged it through the MCP create_work_order tool as {created['created']}.",
            code=('await client.call_tool("create_work_order", {\n'
                  '    "machine_id": "F-200", "line": "Line 2", "fault_code": "E14",\n'
                  '    "symptom": ..., "root_cause": finding["root_cause"],\n'
                  '    "fix_steps": ..., "minutes_down": 95, "first_time_fix": False})'),
            output={"created": created["created"], "root_cause": created["root_cause"], "fix_steps": created["fix_steps"],
                    "minutes_down": created["minutes_down"],
                    "rank_in_first_answer": rank_found or "not listed (not in manual or history yet)"})

    # Step 6: the next technician, the next day, on the other line
    msg2 = "Line 1 F-200 alarm E14. Nozzle 5 dripping after the fill and running underweight."
    ctx2 = gather(idx, "F-200", "Line 1", "E14", msg2, sensors_df)
    d2 = diagnose(ctx2)
    new_rank = next(c.rank for c in d2.causes if c.cause_id == finding["root_cause_id"])
    tr.step("Ask again: the logged fix now ranks first", kind="check",
            what=f"A similar fault on Line 1 now returns the O-ring fix at #{new_rank}, citing {created['created']}.",
            code=('msg2 = "Line 1 F-200 alarm E14. Nozzle 5 dripping after the fill ..."\n'
                  'ctx2 = gather(idx, "F-200", "Line 1", "E14", msg2, sensors)\n'
                  "diag2 = diagnose(ctx2)  # history now includes the new work order"),
            output=f"Tech: {msg2}\n\n" + show(d2, 3))

    # Step 7: replay held-out incidents, before vs after the write-back, vs manual order
    tests = json.loads((DATA / "test_incidents.json").read_text())
    base = json.loads((DATA / "baseline.json").read_text())
    rows = []
    for t in tests:
        c = gather(idx, t["machine_id"], t["line"], t["fault_code"], t["description"], sensors_df)
        c["sensors"] = t["sensors_at_incident"]  # replay with the readings from that day, not today's
        manual_ids = [m[0] for m in CAUSE_RE.findall(c["manual_section"]["text"])]
        r_manual = manual_ids.index(t["confirmed_cause_id"]) + 1 if t["confirmed_cause_id"] in manual_ids else None
        d = diagnose(c)
        r_copilot = next((x.rank for x in d.causes if x.cause_id == t["confirmed_cause_id"]), None)
        c_before = dict(c, history=[w for w in c["history"] if w["wo_id"] != created["created"]])
        r_before_log = next((x.rank for x in diagnose(c_before).causes if x.cause_id == t["confirmed_cause_id"]), None)
        n_c = len(manual_ids)
        mins = lambda search, r: search + (r if r else n_c) * base["minutes_per_cause_checked"] + \
            (0 if r else base["escalation_minutes_if_not_in_manual"]) + t["repair_minutes"]
        rows.append({"id": t["incident_id"], "cause": t["confirmed_cause_id"], "manual_rank": r_manual,
                     "copilot_rank_before_log": r_before_log, "copilot_rank": r_copilot,
                     "mttr_manual": mins(base["manual_search_minutes"], r_manual),
                     "mttr_copilot": mins(base["copilot_search_minutes"], r_copilot)})
    n = len(rows)
    top1 = lambda key: sum(r[key] == 1 for r in rows)
    mttr_b = sum(r["mttr_manual"] for r in rows) / n
    mttr_a = sum(r["mttr_copilot"] for r in rows) / n
    tr.step("Replay past incidents against technician-confirmed causes", kind="check",
            what=f"Re-ran {n} held-out incidents: the confirmed cause came first {top1('manual_rank')}/{n} times in manual order, {top1('copilot_rank_before_log')}/{n} for the copilot before the write-back, {top1('copilot_rank')}/{n} after.",
            code=("rank = position of the confirmed cause in each ordering\n"
                  "mttr = search_min + rank * 20 min per cause checked + repair_min\n"
                  "first_time_fix = rank == 1"),
            output="\n".join(f"{r['id']} {r['cause']:<12} manual #{r['manual_rank'] or '-'}  copilot #{r['copilot_rank_before_log'] or '-'} -> #{r['copilot_rank'] or '-'}"
                             f"  MTTR {r['mttr_manual']} -> {r['mttr_copilot']} min" for r in rows))

    seed = json.loads((DATA / "cmms_seed.json").read_text())
    repeats = 0
    for w in seed:
        t0 = datetime.fromisoformat(w["opened"])
        repeats += any(o is not w and o["machine_id"] == w["machine_id"] and o["line"] == w["line"] and
                       o["fault_code"] == w["fault_code"] and 0 < (t0 - datetime.fromisoformat(o["opened"])).days <= 14
                       for o in seed)
    wrong_first_b = n - top1("manual_rank")
    wrong_first_a = n - top1("copilot_rank")
    tr.metrics(
        mean_time_to_repair=f"{mttr_b:.0f} min -> {mttr_a:.0f} min (replay of {n} incidents, estimate)",
        first_time_fixes=f"{top1('manual_rank')}/{n} in manual order -> {top1('copilot_rank')}/{n} with the copilot",
        repeat_failures=f"{repeats} of {len(seed)} past work orders were repeats within 14 days; wrong first fix (repeat risk) {wrong_first_b}/{n} -> {wrong_first_a}/{n}",
        write_back_effect=f"top-1 {top1('copilot_rank_before_log')}/{n} before logging the O-ring fix -> {top1('copilot_rank')}/{n} after",
        cmms_tools="get_work_order_history, create_work_order (MCP)",
    )
    (OUT / "replay.json").write_text(json.dumps(rows, indent=2))
    tr.save()


if __name__ == "__main__":
    main()
