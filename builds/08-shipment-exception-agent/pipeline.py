"""Build 08 - Shipment exception agent (Logistics). Pattern: event-driven agent.

Events stream in time order. Plain code computes an ETA on every GPS/TMS event and wakes the agent
only when a shipment's ETA (or dock appointment) falls past the promised window. The agent then uses
tools to find the cause and price a fix, drafts the customer update in the account's tone, and a
dispatcher approves with one click.
"""
import html, json, statistics, sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, ask_structured  # noqa: E402
from common.agent_loop_events import Tool, run_agent  # noqa: E402

HERE = Path(__file__).parent
D = lambda name: json.loads((HERE / "data" / f"{name}.json").read_text())
ts = datetime.fromisoformat
fmt = lambda t: t.strftime("%H:%M") + (" (+1d)" if t.day > 24 else "")
PLAN_MPH = 50          # planning speed the TMS uses
WAKE_MARGIN_MIN = 0    # wake the agent as soon as ETA passes the window end

SHIP = {s["shipment_id"]: s for s in D("shipments")}
WEATHER, TRAFFIC, CARRIER = D("weather"), D("traffic"), D("carrier_status")
BACKUP, DOCKS, ACCOUNTS, TONES = D("backup_carriers"), D("dock_schedules"), D("accounts"), D("tone_profiles")
STATE: dict[str, dict] = {}   # live position per shipment, updated by the event stream


# ---------- Step 1: event stream -> ETA -> signal ----------
def on_event(e: dict) -> dict | None:
    """Update the shipment's ETA. Return a signal only if the promise is at risk."""
    s, now = SHIP[e["shipment_id"]], ts(e["ts"])
    st = STATE.setdefault(s["shipment_id"], {"flagged": False})
    window_end = ts(s["promised_window"][1])
    if e["type"] == "carrier_update":
        st["carrier_note"] = e["note"]
        return None
    if e["type"] == "appointment_moved":
        appt = ts(e["new_appointment"])
        st["appointment"] = appt
        if appt > window_end and not st["flagged"]:
            st["flagged"] = True
            return {"shipment_id": s["shipment_id"], "at": now, "reason": "dock appointment moved past window",
                    "eta": appt, "window_end": window_end}
        return None
    if "last" in st:  # recent speed from the last two positions, blended with the plan speed
        prev_t, prev_rem = st["last"]
        v_recent = (prev_rem - e["miles_remaining"]) / max(1e-6, (now - prev_t).total_seconds() / 3600)
        v_eff = max(10.0, 0.75 * v_recent + 0.25 * PLAN_MPH)
    else:
        v_eff = PLAN_MPH
    st["last"] = (now, e["miles_remaining"])
    eta = now + timedelta(hours=e["miles_remaining"] / v_eff)
    st["eta"] = eta
    if eta > window_end + timedelta(minutes=WAKE_MARGIN_MIN) and not st["flagged"]:
        st["flagged"] = True
        return {"shipment_id": s["shipment_id"], "at": now, "eta": eta, "window_end": window_end,
                "reason": f"ETA {fmt(eta)} past window end {fmt(window_end)} (speed now {v_eff:.0f} mph)"}
    return None


# ---------- Step 2-3: the agent's tools (backed by the synthetic feeds) ----------
def planned_eta(sid: str) -> datetime:
    t, rem = STATE[sid]["last"]
    return t + timedelta(hours=rem / PLAN_MPH)

def get_weather(region: str) -> dict:
    return {"region": region, **WEATHER[region]}

def get_traffic(corridor: str) -> dict:
    return {"corridor": corridor, **TRAFFIC[corridor]}

def get_carrier_status(truck: str) -> dict:
    return {"truck": truck, **CARRIER[truck]}

def get_dock_schedule(dc: str, shipment_id: str) -> dict:
    d = DOCKS[dc]
    moved = d["moved"].get(shipment_id)
    delay = 0
    if moved:
        delay = round((ts(moved["new"]) - ts(SHIP[shipment_id]["promised_window"][1])).total_seconds() / 60)
    return {"dc": dc, "congestion": d["congestion"], "appointment_change": moved,
            "est_delay_min": max(0, delay), "next_open_slots": d["open_slots"][:6]}

def quote_reroute(shipment_id: str) -> dict:
    s = SHIP[shipment_id]; tr = TRAFFIC[s["corridor"]]
    eta = planned_eta(shipment_id) + timedelta(minutes=tr["est_delay_min"] - tr["alt_saving_min"])
    return {"option": "reroute", "route": tr["alt_route"], "extra_miles": 18, "cost_usd": 18 * 3,
            "new_eta": eta.isoformat(timespec="minutes")}

def quote_rebook(shipment_id: str) -> dict:
    s = SHIP[shipment_id]; b = BACKUP[s["carrier"]]
    t, rem = STATE[shipment_id]["last"]
    eta = t + timedelta(minutes=b["ready_in_min"]) + timedelta(hours=rem / PLAN_MPH)
    return {"option": "rebook", "carrier": b["backup_carrier"], "ready_in_min": b["ready_in_min"],
            "cost_usd": b["cost_usd"], "new_eta": eta.isoformat(timespec="minutes")}

def quote_appointment_reset(shipment_id: str, earliest_arrival: str) -> dict:
    s = SHIP[shipment_id]
    slot = next((x for x in DOCKS[s["dest_dc"]]["open_slots"] if ts(x) >= ts(earliest_arrival)), None)
    return {"option": "reset_appointment", "dc": s["dest_dc"], "new_appointment": slot, "cost_usd": 0,
            "new_eta": slot or earliest_arrival}

def schema(**props) -> dict:
    return {"type": "object", "properties": {k: {"type": "string"} for k in props}, "required": list(props)}

TOOLS = [
    Tool("get_weather", "Current conditions and expected delay for a region.", schema(region=1), get_weather),
    Tool("get_traffic", "Incidents, expected delay and alternate route for a highway corridor.",
         schema(corridor=1), get_traffic),
    Tool("get_carrier_status", "Carrier's live status for a truck (breakdown, hours of service).",
         schema(truck=1), get_carrier_status),
    Tool("get_dock_schedule", "Receiving appointment, congestion and open slots at the destination DC.",
         schema(dc=1, shipment_id=1), get_dock_schedule),
    Tool("quote_reroute", "Price and ETA for taking the alternate route.", schema(shipment_id=1), quote_reroute),
    Tool("quote_rebook", "Price and ETA for handing the load to the backup carrier.",
         schema(shipment_id=1), quote_rebook),
    Tool("quote_appointment_reset", "Book the earliest open dock slot at or after a given arrival time.",
         schema(shipment_id=1, earliest_arrival=1), quote_appointment_reset),
]
CAUSE_TOOL = {"get_weather": "weather", "get_traffic": "traffic", "get_carrier_status": "carrier",
              "get_dock_schedule": "dock"}
MATERIAL_MIN = 20  # a source must explain at least this many minutes to count as the cause

SYSTEM = ("You are a freight exception agent for Tallgrass Logistics. A shipment's promised delivery window "
          "is at risk. Use the tools to check weather, traffic, carrier status and the dock schedule, decide "
          "the single main cause (weather, traffic, carrier, dock, or none if no source explains 20+ minutes), "
          "then price ONE fix: reroute (traffic with an alternate route), rebook (carrier failure), or "
          "reset_appointment (weather, dock, or traffic with no alternate route). Prefer the fix that keeps the window; otherwise the cheapest. "
          "Finish with the cause, the evidence and the fix.")


def offline_policy_for(sig: dict):
    s = SHIP[sig["shipment_id"]]

    def policy(calls: list[dict]):
        if not calls:  # turn 1: check every possible cause in parallel
            return [("get_weather", {"region": s["region"]}), ("get_traffic", {"corridor": s["corridor"]}),
                    ("get_carrier_status", {"truck": s["truck"]}),
                    ("get_dock_schedule", {"dc": s["dest_dc"], "shipment_id": s["shipment_id"]})]
        if len(calls) == 4:  # turn 2: price the fix that matches the biggest explained delay
            cause = pick_cause(calls)
            sid = s["shipment_id"]
            if cause == "traffic" and TRAFFIC[s["corridor"]]["alt_route"]:
                return [("quote_reroute", {"shipment_id": sid})]
            if cause == "carrier":
                return [("quote_rebook", {"shipment_id": sid})]
            if cause in ("weather", "traffic"):  # no way around it: book the dock for when it can arrive
                src = WEATHER[s["region"]] if cause == "weather" else TRAFFIC[s["corridor"]]
                arr = planned_eta(sid) + timedelta(minutes=src["est_delay_min"])
                return [("quote_appointment_reset", {"shipment_id": sid, "earliest_arrival": arr.isoformat()})]
            if cause == "dock":
                return [("quote_appointment_reset",
                         {"shipment_id": sid, "earliest_arrival": planned_eta(sid).isoformat()})]
        return []
    return policy


def pick_cause(calls: list[dict]) -> str:
    delays = {CAUSE_TOOL[c["name"]]: c["output"].get("est_delay_min", 0) for c in calls if c["name"] in CAUSE_TOOL}
    cause, mins = max(delays.items(), key=lambda kv: kv[1])
    return cause if mins >= MATERIAL_MIN else "none"


class ExceptionCase(BaseModel):
    shipment_id: str
    cause: Literal["weather", "traffic", "carrier", "dock", "none"]
    evidence: str = Field(description="one line citing the tool output that proves the cause")
    fix: Literal["reroute", "rebook", "reset_appointment", "monitor"]
    fix_detail: str
    revised_eta: str = Field(description="ISO time")
    within_window: bool
    cost_usd: int


def offline_case(sig, calls) -> ExceptionCase:
    sid = sig["shipment_id"]
    cause = pick_cause(calls)
    src = next(c for c in calls if CAUSE_TOOL.get(c["name"]) == cause) if cause != "none" else None
    quote = next((c["output"] for c in calls if c["name"].startswith("quote_")), None)
    window_end = ts(SHIP[sid]["promised_window"][1])
    if quote is None:
        eta = planned_eta(sid)
        return ExceptionCase(shipment_id=sid, cause="none", fix="monitor", cost_usd=0,
                             evidence="No source explains 20+ min: " + "; ".join(
                                 f"{c['name']}={c['output'].get('est_delay_min', 0)}m" for c in calls),
                             fix_detail="Keep watching; slowdown already cleared.",
                             revised_eta=eta.isoformat(timespec="minutes"), within_window=eta <= window_end)
    o = src["output"]
    evidence = {"weather": lambda: f"{o['condition']} in {o['region']}, severity {o['severity']}, +{o['est_delay_min']} min",
                "traffic": lambda: f"{o['incident']} on {o['corridor']}, +{o['est_delay_min']} min",
                "carrier": lambda: f"{o['note']} (truck {o['truck']}), +{o['est_delay_min']} min",
                "dock": lambda: f"{o['dc']} congestion '{o['congestion']}', appointment moved to {o['appointment_change']['new'][11:]}"}[cause]()
    detail = {"reroute": lambda: f"Take {quote['route']} (+{quote['extra_miles']} mi)",
              "rebook": lambda: f"Hand trailer to {quote['carrier']}, tractor ready in {quote['ready_in_min']} min",
              "reset_appointment": lambda: f"Rebook {quote['dc']} dock for {quote['new_appointment'][11:] if quote['new_appointment'] else 'next free slot'}"}[quote["option"]]()
    eta = ts(quote["new_eta"])
    return ExceptionCase(shipment_id=sid, cause=cause, evidence=evidence, fix=quote["option"], fix_detail=detail,
                         revised_eta=eta.isoformat(timespec="minutes"), within_window=eta <= window_end,
                         cost_usd=quote["cost_usd"])


# ---------- Step 4: customer update in the account's tone ----------
class CustomerUpdate(BaseModel):
    to: str
    tone: Literal["formal", "friendly", "terse"]
    subject: str
    body: str

CAUSE_WORDS = {"weather": "severe weather on the route", "traffic": "a major traffic incident",
               "carrier": "an equipment problem with the carrier", "dock": "congestion at the receiving dock"}

def offline_update(case: ExceptionCase) -> CustomerUpdate:
    s = SHIP[case.shipment_id]; acct = ACCOUNTS[s["account"]]; tone = acct["tone"]; prof = TONES[tone]
    contact, eta, end = acct["contact"], fmt(ts(case.revised_eta)), fmt(ts(s["promised_window"][1]))
    first = contact.split()[-2] if contact.split()[0].endswith(".") else contact.split()[0]
    late_by = round((ts(case.revised_eta) - ts(s["promised_window"][1])).total_seconds() / 60)
    fixw = case.fix_detail[0].lower() + case.fix_detail[1:]
    if tone == "formal":
        body = (f"{prof['greeting'].format(contact=contact)}\n\nWe are writing to let you know that shipment "
                f"{case.shipment_id} has been delayed by {CAUSE_WORDS[case.cause]}. To limit the impact we have "
                f"taken the following step: {fixw}. The revised arrival time is {eta}, which is {late_by} minutes "
                f"after your agreed window closing at {end}. We apologise for the inconvenience and will confirm "
                f"on arrival.\n\n{prof['signoff']}")
        subject = f"Shipment {case.shipment_id}: revised delivery time {eta}"
    elif tone == "friendly":
        body = (f"{prof['greeting'].format(first=first)}\n\nQuick heads-up on {case.shipment_id}: it's been held up "
                f"by {CAUSE_WORDS[case.cause]}. We've already acted ({fixw}), and it's now due at {eta}, about "
                f"{late_by} minutes past your {end} window. We'll ping you again when it's at the dock.\n\n{prof['signoff']}")
        subject = f"Heads-up: {case.shipment_id} now arriving {eta}"
    else:
        body = (f"{case.shipment_id} delayed: {case.cause}. New ETA {eta} (window end {end}, +{late_by} min). "
                f"Action: {fixw}.\n{prof['signoff']}")
        subject = f"{case.shipment_id} new ETA {eta}"
    return CustomerUpdate(to=contact, tone=tone, subject=subject, body=body)


def main():
    tr = Trace("08", "Shipment exception agent", HERE / "outputs")
    tr.arch([
        {"label": "TMS + GPS webhooks", "kind": "data", "note": "event stream"},
        {"label": "ETA watcher", "kind": "code", "note": "wakes agent on risk only"},
        {"label": "Exception agent", "kind": "ai", "note": "tool loop: cause + fix"},
        {"label": "Weather / traffic / carrier / dock", "kind": "system", "note": "tools (MCP in prod)"},
        {"label": "Tone-matched update", "kind": "ai", "note": "per-account profile"},
        {"label": "Dispatcher one-click", "kind": "human", "note": "approve, then log"},
        {"label": "Ops dashboard", "kind": "system", "note": "ops_log + HTML"},
    ])
    tr.story(
        situation="A regional 3PL runs about 400 loads a day. Dispatchers learn a load is late when the customer calls, then dig through four systems and type the same apology email by hand.",
        constraints="The agent may not move freight on its own: every reroute, rebook or new appointment needs a dispatcher's click. Customer emails must match each account's agreed tone. The agent should only wake when a promise is at risk, to keep cost and noise down.",
        replay="Reuse: 'watch a stream, wake an agent on a signal, human approves' fits any SLA desk (field service, claims, IT incidents). Next time: link traffic incidents to their cause (a storm-closed lane is a weather problem), and learn each dispatcher's edits back into the tone profiles.",
    )

    # Step 1 -----------------------------------------------------------------
    events = D("events")
    signals = [sig for e in events if (sig := on_event(e))]
    tr.step("Stream shipment events and flag at-risk ETAs", kind="io",
            what=f"Replayed {len(events)} GPS/TMS events for {len(SHIP)} shipments in time order; the agent woke {len(signals)} times.",
            code=("for e in sorted(events, key=lambda e: e['ts']):\n"
                  "    v = 0.75 * recent_mph + 0.25 * PLAN_MPH\n"
                  "    eta = e.ts + miles_remaining / v\n"
                  "    if eta > window_end and not flagged:\n"
                  "        signals.append(wake_agent(shipment))"),
            output="\n".join(f"{fmt(s['at'])}  {s['shipment_id']}  {s['reason']}" for s in signals))

    # Step 2-3 ---------------------------------------------------------------
    cases, runs = [], {}
    for sig in signals:
        s = SHIP[sig["shipment_id"]]
        prompt = (f"Shipment {s['shipment_id']} for {s['account']}: {sig['reason']}. Carrier {s['carrier']}, truck "
                  f"{s['truck']}, region {s['region']}, corridor {s['corridor']}, destination {s['dest_dc']}, "
                  f"promised window {s['promised_window'][0]} to {s['promised_window'][1]}.")
        run = run_agent(system=SYSTEM, prompt=prompt, tools=TOOLS, offline_policy=offline_policy_for(sig))
        runs[s["shipment_id"]] = run
        case = ask_structured(system="Turn the agent's investigation into the exception record.",
                              content=prompt + "\n\nTool calls:\n" + json.dumps(run.calls, default=str) +
                              "\n\nAgent conclusion:\n" + run.final_text,
                              schema=ExceptionCase, offline=lambda: offline_case(sig, run.calls))
        cases.append(case)
    ex = next(c for c in cases if c.cause == "carrier")
    r = runs[ex.shipment_id]
    tr.step("Agent checks the cause with four tools", kind="ai",
            what="Each wake-up runs a tool loop: weather, traffic, carrier and dock are checked in one parallel turn, and the biggest explained delay wins.",
            code=("resp = client.messages.create(model=MODEL, max_tokens=16000,\n"
                  "                              tools=TOOLS, messages=msgs)\n"
                  "while resp.stop_reason == 'tool_use':\n"
                  "    results = [run(b) for b in resp.content if b.type == 'tool_use']\n"
                  "    msgs += [assistant(resp.content), user(results)]  # all results, one message"),
            output=f"Example {ex.shipment_id}, turn 1:\n" + "\n".join(
                f"  {c['name']}({', '.join(map(str, c['input'].values()))}) -> {c['output'].get('est_delay_min')} min"
                for c in r.calls if c["turn"] == 1) + "\n\nAll wake-ups:\n" + "\n".join(
                f"  {c.shipment_id}  cause={c.cause:<8} {c.evidence}" for c in cases))

    tr.step("Propose a fix: reroute, rebook or reset the appointment", kind="ai",
            what="In a second turn the agent prices one fix that matches the cause and checks it against the promised window.",
            code=("if cause == 'traffic': quote_reroute(sid)\n"
                  "elif cause == 'carrier': quote_rebook(sid)\n"
                  "elif cause in ('weather', 'dock'):\n"
                  "    quote_appointment_reset(sid, earliest_arrival)\n"
                  "case = ask_structured(..., schema=ExceptionCase)"),
            output="\n".join(f"{c.shipment_id}  {c.fix:<17} ${c.cost_usd:<4} new ETA {c.revised_eta[11:]}  "
                             f"{'keeps window' if c.within_window else 'still late'}  | {c.fix_detail}" for c in cases))

    # Step 4 -----------------------------------------------------------------
    updates = {}
    for c in cases:
        if c.cause == "none" or c.within_window:
            continue  # nothing to tell the customer: the fix keeps the promise
        s = SHIP[c.shipment_id]; acct = ACCOUNTS[s["account"]]
        updates[c.shipment_id] = ask_structured(
            system=f"Write a customer delay update. Tone profile: {json.dumps(TONES[acct['tone']])}. "
                   "Use only facts from the record. No promises beyond the revised ETA.",
            content=f"Account: {s['account']} (contact {acct['contact']}).\nRecord: {c.model_dump_json()}",
            schema=CustomerUpdate, offline=lambda c=c: offline_update(c))
    shown = []
    for tone in ("formal", "friendly", "terse"):
        u = next((u for u in updates.values() if u.tone == tone), None)
        if u:
            shown.append(f"--- {tone.upper()} ---\nSubject: {u.subject}\n{u.body}")
    tr.step("Draft the customer update in the account's tone", kind="ai",
            what=f"{len(updates)} updates drafted, one per still-late shipment; recovered shipments need no email.",
            code=("profile = TONES[ACCOUNTS[s.account]['tone']]\n"
                  "update = ask_structured(system=f'Tone profile: {profile}',\n"
                  "                        content=case.model_dump_json(),\n"
                  "                        schema=CustomerUpdate)"),
            output="\n\n".join(shown))

    # Step 5 -----------------------------------------------------------------
    base = D("baseline")
    log = []
    for c in cases:
        s = SHIP[c.shipment_id]
        decision = "dismissed (no action)" if c.fix == "monitor" else (
            "approved" if c.cost_usd <= 500 else "approved + manager notified (over $500)")
        log.append({"shipment_id": c.shipment_id, "account": s["account"],
                    "flagged_at": next(fmt(g["at"]) for g in signals if g["shipment_id"] == c.shipment_id),
                    "cause": c.cause, "fix": c.fix, "fix_detail": c.fix_detail, "cost_usd": c.cost_usd,
                    "revised_eta": c.revised_eta, "window_end": s["promised_window"][1],
                    "within_window": c.within_window, "customer_update_sent": c.shipment_id in updates,
                    "dispatcher_decision": decision, "clicks": 1,
                    "review_minutes": base["review_minutes_per_agent_proposal"]})
    (HERE / "outputs/ops_log.json").write_text(json.dumps(
        {"log": log, "customer_updates": {k: v.model_dump() for k, v in updates.items()}}, indent=2))
    write_dashboard(log)
    tr.step("Dispatcher approves in one click; outcome logged", kind="human",
            what="Each proposal is shown with its evidence; the dispatcher approves (simulated here) and the outcome goes to the ops log and dashboard.",
            code=("decision = 'approved' if case.cost_usd <= 500 else 'approved + manager notified'\n"
                  "ops_log.append({**case.model_dump(), 'decision': decision, 'clicks': 1})\n"
                  "write_dashboard(ops_log)  # outputs/ops_dashboard.html"),
            output="\n".join(f"{l['flagged_at']}  {l['shipment_id']}  {l['dispatcher_decision']:<40} "
                             f"email={'yes' if l['customer_update_sent'] else 'no'}" for l in log))

    # Step 6: score against the answer key ------------------------------------
    key = D("answer_key")
    late = {k for k, v in key.items() if v["late"]}
    by_id = {c.shipment_id: c for c in cases}
    correct = [sid for sid, c in by_id.items() if c.cause == key[sid]["true_cause"]]
    misses = [f"{sid}: agent said {c.cause}, truth {key[sid]['true_cause']}" for sid, c in by_id.items()
              if c.cause != key[sid]["true_cause"]]
    caught = late & set(by_id)
    warn_new = [(ts(SHIP[s]["promised_window"][1]) - next(g["at"] for g in signals if g["shipment_id"] == s))
                .total_seconds() / 60 for s in caught]
    warn_old = [(ts(SHIP[s]["promised_window"][1]) - ts(key[s]["customer_called_at"])).total_seconds() / 60
                for s in late]
    tr.step("Score causes and warning time against the answer key", kind="check",
            what="Ops leads hand-labelled the true cause of every flagged shipment; we score the agent and the warning time.",
            code=("acc = mean(case.cause == key[sid]['true_cause'] for sid, case in cases)\n"
                  "warning_new = window_end - flagged_at\n"
                  "warning_old = window_end - customer_called_at   # negative = after the fact"),
            output={"truly_late": len(late), "caught_before_window": f"{len(caught)}/{len(late)}",
                    "false_alarms": sorted(set(by_id) - late),
                    "cause_accuracy": f"{len(correct)}/{len(by_id)} ({len(correct) / len(by_id):.0%})",
                    "misses": misses,
                    "median_warning_min_new": round(statistics.median(warn_new)),
                    "median_warning_min_old": round(statistics.median(warn_old))})

    m = base["manual_minutes_per_exception"]; manual = sum(m.values())
    tickets_new = sum(1 for s in late if s not in by_id)
    tr.metrics(
        exceptions_caught_early=f"{len(caught)}/{len(late)} before the promised window",
        warning_minutes=f"{round(statistics.median(warn_old))} -> +{round(statistics.median(warn_new))} (median, vs window end)",
        cause_accuracy=f"{len(correct)}/{len(by_id)} ({len(correct) / len(by_id):.0%})",
        windows_saved_by_fix=f"{sum(c.within_window for c in cases if c.fix != 'monitor')}/{len(caught)}",
        customer_tickets=f"{len(late)} -> {tickets_new} (proactive updates instead of inbound calls)",
        dispatcher_hours=f"{len(late) * manual / 60:.1f} -> {len(log) * base['review_minutes_per_agent_proposal'] / 60:.2f}",
    )
    tr.save()


def write_dashboard(log: list[dict]):
    rows = "\n".join(
        f"<tr><td>{l['flagged_at']}</td><td>{l['shipment_id']}</td><td>{html.escape(l['account'])}</td>"
        f"<td><span class='chip {l['cause']}'>{l['cause']}</span></td><td>{html.escape(l['fix_detail'])}</td>"
        f"<td>${l['cost_usd']}</td><td>{l['revised_eta'][11:]} / {l['window_end'][11:]}</td>"
        f"<td class='{'ok' if l['within_window'] else 'late'}'>{'on time' if l['within_window'] else 'late'}</td>"
        f"<td>{'sent' if l['customer_update_sent'] else '-'}</td><td>{l['dispatcher_decision']}</td></tr>"
        for l in log)
    saved = sum(l["within_window"] and l["fix"] != "monitor" for l in log)
    kpis = [("Exceptions flagged", len(log)), ("Windows saved", saved),
            ("Customer updates", sum(l["customer_update_sent"] for l in log)), ("Dispatcher clicks", len(log))]
    tiles = "".join(f"<div class='tile'><b>{v}</b><span>{k}</span></div>" for k, v in kpis)
    (HERE / "outputs/ops_dashboard.html").write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Exception Ops Dashboard</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e4e3de;--ok:#1f7a4d;--late:#b3402e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;--card:#20201e;--line:#33322f;--ok:#5cc28d;--late:#ef8a76}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:var(--muted);margin:0 0 16px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}
.tile b{{display:block;font-size:26px}} .tile span{{color:var(--muted)}}
.wrap{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}}
table{{border-collapse:collapse;width:100%;min-width:900px}} th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
th{{color:var(--muted);font-weight:600}} .ok{{color:var(--ok)}} .late{{color:var(--late)}}
.chip{{border:1px solid var(--line);border-radius:999px;padding:1px 8px}}
</style></head><body><h1>Shipment exceptions - today</h1>
<p>Offline run on synthetic data. Every action below was approved by a dispatcher.</p>
<div class="tiles">{tiles}</div><div class="wrap"><table><thead><tr><th>Flagged</th><th>Shipment</th>
<th>Account</th><th>Cause</th><th>Fix</th><th>Cost</th><th>ETA / window end</th><th>Result</th><th>Update</th>
<th>Dispatcher</th></tr></thead><tbody>{rows}</tbody></table></div></body></html>""")


if __name__ == "__main__":
    main()
