"""Build 05 - Tenant request triage agent (Property management). Pattern: agent + approvals."""
import json, re, sys, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, ask_structured  # noqa: E402
from common.agent import run_agent  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
SPEND_LIMIT = 500.00          # vendor spend above this needs a manager's approval in Slack
OFFICE_OPEN, OFFICE_CLOSE = 9, 17


# ---------- Step 1: classify ----------
class Triage(BaseModel):
    message_id: str
    category: Literal["question", "repair", "emergency", "billing"]
    urgency: Literal["now", "today", "routine"]
    reason: str = Field(description="one sentence citing the words that decided it")

CLASSIFY_SYSTEM = (
    "You triage tenant messages for a property manager. Pick exactly one category: "
    "emergency (risk to life or property right now: gas, flooding, fire, no heat in freezing weather), "
    "repair (something broken but not dangerous), billing (rent charges, fees, receipts, payments), "
    "question (anything answerable from the lease or FAQ). Set urgency and give a one-sentence reason.")

EMERGENCY_CUES = ["gas", "pouring", "flood", "fire", "smoke", "sparking", "carbon monoxide", "no heat"]
BILLING_CUES = ["late fee", "charged", "receipt", "autopay", "balance", "invoice", "refund", "rent payment"]
REPAIR_CUES = ["broken", "clogged", "leak", "stopped working", "isn't", "not working", "noise", "won't"]


def offline_classify(msg: dict) -> Triage:
    t = msg["text"].lower()
    for cat, cues, urg in [("emergency", EMERGENCY_CUES, "now"), ("billing", BILLING_CUES, "routine"),
                           ("repair", REPAIR_CUES, "today")]:
        hit = next((c for c in cues if c in t), None)
        if hit:
            return Triage(message_id=msg["id"], category=cat, urgency=urg, reason=f"mentions '{hit}'")
    return Triage(message_id=msg["id"], category="question", urgency="routine",
                  reason="no repair, billing or safety cue; reads as a policy question")


# ---------- Tools (same Python functions LIVE and OFFLINE) ----------
STOP = set("the a an and or is are to of for in on at my i me it its can do does what how when where there "
           "this that with be any each get have has before need need anymore you your our".split())


def tokens(s: str) -> list[str]:
    return [w[:-1] if w.endswith("s") and len(w) > 3 else w
            for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2]


def load_chunks() -> list[dict]:
    chunks = []
    for fname, label in [("lease.md", "Lease"), ("faq.md", "FAQ")]:
        for block in (DATA / fname).read_text().split("\n## ")[1:]:
            head, body = block.split("\n", 1)
            src = f"Lease §{head}" if label == "Lease" else f"FAQ: {head}"
            chunks.append({"source": src, "heading": head, "text": body.strip()})
    return chunks


class World:
    """The systems the agent can touch: policy docs (RAG), ledger, work orders, vendors, pager, Slack, outbox."""

    def __init__(self):
        self.chunks = load_chunks()
        self.ledger = json.loads((DATA / "tenant_ledger.json").read_text())
        self.vendors = json.loads((DATA / "vendors.json").read_text())
        self.price_book = json.loads((DATA / "price_book.json").read_text())
        self.on_call = json.loads((DATA / "on_call.json").read_text())
        self.work_orders, self.pages, self.approvals, self.outbox = [], [], [], []
        self.now = None  # set to each message's received time (simulated clock)

    def search_policies(self, query: str, k: int = 2):
        q = set(tokens(query))
        scored = []
        for c in self.chunks:
            score = 2 * len(q & set(tokens(c["heading"]))) + len(q & set(tokens(c["text"])))
            scored.append({**c, "score": score})
        return sorted(scored, key=lambda c: -c["score"])[:k]

    def get_tenant_ledger(self, unit: str):
        return self.ledger.get(unit, [])

    def create_work_order(self, message_id: str, unit: str, issue: str, priority: str):
        t = issue.lower()
        name, item = next(((n, p) for n, p in self.price_book.items() if any(k in t for k in p["keywords"])),
                          ("general", {"trade": "handyman", "hours": 1.0, "parts": 0}))
        rate = next((v["hourly"] for v in self.vendors if v["trade"] == item["trade"]), 90)
        mult = 1.5 if priority == "emergency" else 1.0   # after-hours / emergency call-out rate
        est = round(item["hours"] * rate * mult + item["parts"], 2)
        wo = {"wo_id": f"WO-{2400 + len(self.work_orders) + 1}", "message_id": message_id, "unit": unit,
              "issue": name, "trade": item["trade"], "priority": priority, "estimate_usd": est,
              "needs_approval": priority != "emergency" and est > SPEND_LIMIT, "status": "draft"}
        self.work_orders.append(wo)
        return wo

    def find_vendor_slot(self, wo_id: str, trade: str, emergency: bool):
        wo = next(w for w in self.work_orders if w["wo_id"] == wo_id)
        v = next((v for v in self.vendors if v["trade"] == trade), None)
        if v is None:
            return {"error": f"no vendor for trade {trade}"}
        if emergency:
            if not v["after_hours_24_7"]:
                return {"error": f"{v['vendor']} has no 24/7 service"}
            slot = (self.now + timedelta(hours=1)).isoformat(timespec="minutes")
            wo.update(vendor=v["vendor"], slot=slot, status="dispatched")
            return {"vendor": v["vendor"], "slot": slot, "note": "24/7 call-out, ETA 1 hour"}
        earliest = self.now + timedelta(hours=8)  # give the vendor a working morning's notice
        slot = next((s for s in sorted(v["open_slots"]) if datetime.fromisoformat(s) >= earliest), None)
        if slot is None:
            return {"error": "no open slot this week"}
        v["open_slots"].remove(slot)
        wo.update(vendor=v["vendor"], slot=slot,
                  status="awaiting_approval" if wo["needs_approval"] else "scheduled")
        return {"vendor": v["vendor"], "slot": slot, "held": wo["needs_approval"]}

    def page_on_call(self, message_id: str, unit: str, summary: str):
        page = {"to": self.on_call["name"], "phone": self.on_call["phone"], "message_id": message_id,
                "unit": unit, "summary": summary,
                "paged_at": (self.now + timedelta(minutes=1)).isoformat(timespec="minutes"),
                "requires_ack_within_min": 10}
        self.pages.append(page)
        return page

    def request_spend_approval(self, wo_id: str, reason: str):
        wo = next(w for w in self.work_orders if w["wo_id"] == wo_id)
        slack = {
            "channel": "#maintenance-approvals",
            "text": f"Approval needed: {wo['wo_id']} {wo['vendor']} ${wo['estimate_usd']:,.2f}",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text",
                                            "text": f"Vendor spend approval: ${wo['estimate_usd']:,.2f}"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Work order:*\n{wo['wo_id']} (unit {wo['unit']})"},
                    {"type": "mrkdwn", "text": f"*Vendor:*\n{wo['vendor']}, {wo['slot']}"},
                    {"type": "mrkdwn", "text": f"*Issue:*\n{wo['issue']}"},
                    {"type": "mrkdwn", "text": f"*Why:*\n{reason}"}]},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "style": "primary",
                     "action_id": "approve_spend", "value": wo["wo_id"]},
                    {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "style": "danger",
                     "action_id": "reject_spend", "value": wo["wo_id"]}]},
            ],
            "posted_at": self.now.isoformat(timespec="minutes"),
        }
        self.approvals.append(slack)
        return {"queued": True, "wo_id": wo_id, "limit_usd": SPEND_LIMIT}

    def send_reply(self, message_id: str, text: str, sources: list[str]):
        out = {"message_id": message_id, "text": text, "sources": sources,
               "sent_at": (self.now + timedelta(minutes=1)).isoformat(timespec="minutes")}
        self.outbox.append(out)
        return {"sent": True}


TOOLS = [
    {"name": "search_policies", "description": "Search the lease and resident FAQ. Returns the best passages with their source.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_tenant_ledger", "description": "Charges and payments for a unit.",
     "input_schema": {"type": "object", "properties": {"unit": {"type": "string"}}, "required": ["unit"]}},
    {"name": "create_work_order", "description": "Draft a work order; returns trade and a cost estimate from the price book.",
     "input_schema": {"type": "object", "properties": {
         "message_id": {"type": "string"}, "unit": {"type": "string"}, "issue": {"type": "string"},
         "priority": {"type": "string", "enum": ["emergency", "standard"]}},
         "required": ["message_id", "unit", "issue", "priority"]}},
    {"name": "find_vendor_slot", "description": "Book the vendor's earliest slot for a work order (24/7 call-out if emergency).",
     "input_schema": {"type": "object", "properties": {
         "wo_id": {"type": "string"}, "trade": {"type": "string"}, "emergency": {"type": "boolean"}},
         "required": ["wo_id", "trade", "emergency"]}},
    {"name": "page_on_call", "description": "Page the on-call manager immediately. Use for every emergency.",
     "input_schema": {"type": "object", "properties": {
         "message_id": {"type": "string"}, "unit": {"type": "string"}, "summary": {"type": "string"}},
         "required": ["message_id", "unit", "summary"]}},
    {"name": "request_spend_approval", "description": f"Post a Slack approval for work orders over ${SPEND_LIMIT:.0f}.",
     "input_schema": {"type": "object", "properties": {"wo_id": {"type": "string"}, "reason": {"type": "string"}},
                      "required": ["wo_id", "reason"]}},
    {"name": "send_reply", "description": "Reply to the tenant on the channel they used. Cite sources for policy answers.",
     "input_schema": {"type": "object", "properties": {
         "message_id": {"type": "string"}, "text": {"type": "string"},
         "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["message_id", "text", "sources"]}},
]

AGENT_SYSTEM = (
    "You are the after-hours and daytime triage agent for Maple Court Apartments. For each message:\n"
    "- question: search_policies, answer ONLY from the passages, and cite the source in send_reply.\n"
    "- billing: check get_tenant_ledger and search_policies, then reply with the facts and the source.\n"
    "- repair: create_work_order, find_vendor_slot, and if needs_approval is true call request_spend_approval; "
    "then tell the tenant what happens next.\n"
    "- emergency: page_on_call FIRST, then create_work_order (priority emergency), find_vendor_slot with "
    "emergency=true, search_policies for safety steps, and send_reply with those steps.\n"
    "Never promise anything a tool did not confirm.")


def offline_planner(user: str, calls: list[dict]) -> dict:
    """Deterministic stand-in for Claude's tool choices: reads the message, then the tool results so far."""
    m = dict(re.findall(r"(\w+)=([^|\n]+)", user.split("\n")[0]))
    mid, unit, cat = m["id"].strip(), m["unit"].strip(), m["category"].strip()
    text = user.split("\n", 1)[1].strip()
    done = {c["tool"]: c["result"] for c in calls}
    reply = lambda t, s: {"tool": "send_reply", "input": {"message_id": mid, "text": t, "sources": s}}

    if "send_reply" in done:
        return {"final": f"{mid}: handled as {cat} with {len(calls)} tool calls"}
    if cat == "emergency":
        if "page_on_call" not in done:
            return {"tool": "page_on_call", "input": {"message_id": mid, "unit": unit, "summary": text[:90]}}
        if "create_work_order" not in done:
            return {"tool": "create_work_order",
                    "input": {"message_id": mid, "unit": unit, "issue": text, "priority": "emergency"}}
        wo = done["create_work_order"]
        if "find_vendor_slot" not in done:
            return {"tool": "find_vendor_slot", "input": {"wo_id": wo["wo_id"], "trade": wo["trade"], "emergency": True}}
        if "search_policies" not in done:
            return {"tool": "search_policies", "input": {"query": text}}
        top, slot = done["search_policies"][0], done["find_vendor_slot"]
        eta = f" {slot['vendor']} is on the way (ETA {slot['slot'][11:]})." if "vendor" in slot else ""
        return reply(f"This is an emergency and the on-call manager has been paged.{eta} Right now: {top['text']}",
                     [top["source"]])
    if cat == "repair":
        if "create_work_order" not in done:
            return {"tool": "create_work_order",
                    "input": {"message_id": mid, "unit": unit, "issue": text, "priority": "standard"}}
        wo = done["create_work_order"]
        if "find_vendor_slot" not in done:
            return {"tool": "find_vendor_slot", "input": {"wo_id": wo["wo_id"], "trade": wo["trade"], "emergency": False}}
        slot = done["find_vendor_slot"]
        if wo["needs_approval"] and "request_spend_approval" not in done:
            return {"tool": "request_spend_approval",
                    "input": {"wo_id": wo["wo_id"], "reason": f"estimate ${wo['estimate_usd']:,.2f} > ${SPEND_LIMIT:,.0f} limit"}}
        when = datetime.fromisoformat(slot["slot"]).strftime("%a %d %b at %H:%M") if "slot" in slot else "soon"
        held = " once a manager approves the cost (usually within the hour)" if wo["needs_approval"] else ""
        return reply(f"Thanks, we've opened work order {wo['wo_id']} for the {wo['issue']}. {slot.get('vendor', 'A vendor')} "
                     f"can come {when}{held}. Reply here if that time doesn't work.", [wo["wo_id"]])
    if cat == "billing":
        if "get_tenant_ledger" not in done:
            return {"tool": "get_tenant_ledger", "input": {"unit": unit}}
        if "search_policies" not in done:
            return {"tool": "search_policies", "input": {"query": text}}
        return reply(*billing_answer(text, done["get_tenant_ledger"], done["search_policies"][0]))
    if "search_policies" not in done:
        return {"tool": "search_policies", "input": {"query": text}}
    top = done["search_policies"][0]
    return reply(f"{top['text']} (Source: {top['source']})", [top["source"]])


def billing_answer(text: str, ledger: list[dict], top: dict) -> tuple[str, list[str]]:
    t = text.lower()
    fee = next((e for e in ledger if e["type"] == "late_fee"), None)
    pay = next((e for e in ledger if e["type"] == "payment" and e["date"][:7] == (fee or {}).get("date", "")[:7]), None)
    if fee and pay:
        grace = int(re.search(r"through the (\d+)", top["text"]).group(1)) if "through the" in top["text"] else 5
        day = int(pay["date"][8:])
        if day <= grace:
            return (f"Our ledger shows your payment of ${pay['amount']:,.2f} on {pay['date']}, inside the grace "
                    f"period (through day {grace}). The ${fee['amount']:.0f} late fee should not apply; "
                    f"the office will confirm the reversal next business day. (Source: {top['source']}; tenant ledger)", [top["source"], "Tenant ledger"])
    if "receipt" in t:
        month = next((m for m in ["january", "february", "march", "april", "may", "june", "july", "august",
                                  "september", "october", "november", "december"] if m in t), None)
        mnum = f"{['january','february','march','april','may','june','july','august','september','october','november','december'].index(month)+1:02d}" if month else ""
        p = next((e for e in ledger if e["type"] == "payment" and e["date"][5:7] == mnum), None)
        found = f"We have your {month.title()} payment of ${p['amount']:,.2f} on {p['date']} (ref {p['ref']}). " if p else ""
        return (found + top["text"] + f" (Source: {top['source']})", [top["source"], "Tenant ledger"])
    failed = next((e for e in ledger if e["type"] == "autopay_failed"), None)
    if failed:
        return (f"Your autopay of ${failed['amount']:,.2f} on {failed['date']} was returned ({failed['ref']}). "
                + top["text"] + f" (Source: {top['source']})", [top["source"], "Tenant ledger"])
    return (top["text"], [top["source"]])


def slack_preview(msg: dict) -> str:
    """Slack Block Kit message, one block per line so it stays readable in the trace."""
    lines = ["{", f'  "channel": {json.dumps(msg["channel"])},', f'  "text": {json.dumps(msg["text"])},', '  "blocks": [']
    lines += [f"    {json.dumps(b)}," for b in msg["blocks"]]
    lines += ["  ],", f'  "response": {json.dumps(msg.get("response"))}', "}"]
    return "\n".join(lines)


def after_hours(ts: datetime) -> bool:
    return ts.weekday() >= 5 or not (OFFICE_OPEN <= ts.hour < OFFICE_CLOSE)


def next_office_open(ts: datetime) -> datetime:
    t = ts
    while after_hours(t):
        t = (t + timedelta(hours=1)).replace(minute=0)
    return t


def main():
    tr = Trace("05", "Tenant request triage agent", HERE / "outputs")
    tr.arch([
        {"label": "Email + SMS inbox", "kind": "data", "note": "tenant messages, 24/7"},
        {"label": "Claude triage", "kind": "ai", "note": "question / repair / emergency / billing"},
        {"label": "Agent with tools", "kind": "ai", "note": "lease + FAQ search, ledger, vendors"},
        {"label": "Work-order API", "kind": "system", "note": "draft WO + vendor slot"},
        {"label": "On-call pager", "kind": "system", "note": "emergencies, within 1 minute"},
        {"label": "Slack approvals", "kind": "human", "note": f"spend over ${SPEND_LIMIT:.0f}"},
    ])
    tr.story(
        situation="A 240-unit apartment portfolio with a two-person office. Tenant emails and texts pile up; simple questions wait days and an urgent leak can sit unread overnight.",
        constraints="Emergencies must reach a human in minutes, not wait for the agent's judgement on spend. Answers must cite the lease or FAQ so staff can stand behind them. Any vendor spend over the limit needs a manager's click; the agent never spends on its own above it.",
        replay="Reuse: classify -> agent with narrow tools -> human approval over a threshold fits any service inbox (IT helpdesk, facilities, field service). Next time: connect the real work-order API first, and log every tool call so the owner can audit what the agent did overnight.",
    )

    inbox = json.loads((DATA / "inbox.json").read_text())
    ah = [m for m in inbox if after_hours(datetime.fromisoformat(m["received_at"]))]
    tr.step("Read the email and SMS inbox", kind="io",
            what=f"Loaded {len(inbox)} synthetic tenant messages from one week; {len(ah)} arrived outside office hours.",
            code=('inbox = json.loads(Path("data/inbox.json").read_text())\n'
                  'ah = [m for m in inbox if after_hours(datetime.fromisoformat(m["received_at"]))]'),
            output="\n".join(f"{m['id']} {m['channel']:5} {datetime.fromisoformat(m['received_at']):%a %H:%M}"
                             f"{' (after hours)' if m in ah else '':15} {m['text'][:58]}" for m in inbox))

    # Step 1: classify each message (real-time call per message, not batch: emergencies can't wait)
    triage = {}
    for m in inbox:
        triage[m["id"]] = ask_structured(system=CLASSIFY_SYSTEM, content=f"Message {m['id']}: {m['text']}",
                                         schema=Triage, offline=lambda m=m: offline_classify(m))
    counts = {c: sum(t.category == c for t in triage.values()) for c in ["question", "repair", "emergency", "billing"]}
    tr.step("Classify each message", kind="ai",
            what="Claude labels every message as question, repair, emergency or billing, with urgency and a reason.",
            code=('triage[m["id"]] = ask_structured(system=CLASSIFY_SYSTEM,\n'
                  '    content=f"Message {m[\'id\']}: {m[\'text\']}",\n'
                  '    schema=Triage, offline=lambda: offline_classify(m))'),
            output="\n".join(f"{k}  {t.category:9} {t.urgency:7} {t.reason}" for k, t in triage.items())
            + f"\n\ncounts: {counts}")

    # Steps 2-4: one agent run per message, emergencies first
    world = World()
    handlers = {t["name"]: getattr(world, t["name"]) for t in TOOLS}
    order = sorted(inbox, key=lambda m: (triage[m["id"]].category != "emergency", m["received_at"]))
    runs, runtime = {}, {}
    for m in order:
        world.now = datetime.fromisoformat(m["received_at"])
        tg = triage[m["id"]]
        user = (f"id={m['id']} | unit={m['unit']} | channel={m['channel']} | category={tg.category} | urgency={tg.urgency}\n"
                f"{m['text']}")
        t0 = time.perf_counter()
        runs[m["id"]] = run_agent(system=AGENT_SYSTEM, user=user, tools=TOOLS, handlers=handlers,
                                  offline_planner=offline_planner)
        runtime[m["id"]] = time.perf_counter() - t0

    def show(mid):
        lines = [f"{mid}: \"{next(x['text'] for x in inbox if x['id'] == mid)[:70]}\""]
        for c in runs[mid].calls:
            arg = json.dumps(c["input"])[:80]
            res = c["result"]
            if c["tool"] == "search_policies":
                res = [f"{h['source']} (score {h['score']})" for h in res]
            elif c["tool"] == "send_reply":
                res = "sent"
            lines.append(f"  -> {c['tool']}({arg})\n     = {json.dumps(res, default=str)[:110]}")
        r = next(o for o in world.outbox if o["message_id"] == mid)
        lines.append(f"  REPLY: {r['text'][:220]}")
        return "\n".join(lines)

    qs = [k for k, t in triage.items() if t.category in ("question", "billing")]
    cited = sum(1 for o in world.outbox if o["message_id"] in qs and o["sources"])
    tr.step("Answer questions from the lease and FAQ, with the source", kind="ai",
            what=f"The agent searches the lease and FAQ (and the ledger for billing), then replies with a citation: {cited}/{len(qs)} answers cite a source.",
            code=('run = run_agent(system=AGENT_SYSTEM, user=user, tools=TOOLS,\n'
                  '                handlers=handlers, offline_planner=offline_planner)\n'
                  '# LIVE: loop while resp.stop_reason == "tool_use";\n'
                  '#       all tool_result blocks go back in ONE user message'),
            output=show("M02") + "\n\n" + show("M04"))

    repairs = [w for w in world.work_orders if w["priority"] == "standard"]
    tr.step("Draft a work order and propose a vendor slot", kind="ai",
            what=f"{len(repairs)} repairs became draft work orders with a cost estimate and the vendor's earliest slot; {sum(w['needs_approval'] for w in repairs)} are over ${SPEND_LIMIT:.0f} and held for approval.",
            code=('wo = create_work_order(message_id, unit, issue, priority="standard")\n'
                  'slot = find_vendor_slot(wo["wo_id"], wo["trade"], emergency=False)\n'
                  'if wo["needs_approval"]:  # estimate > SPEND_LIMIT\n'
                  '    request_spend_approval(wo["wo_id"], reason)'),
            output=show("M09") + "\n\nWork orders:\n" + "\n".join(
                f"  {w['wo_id']} unit {w['unit']} {w['issue']:13} {w['vendor']:22} {w['slot']}  ${w['estimate_usd']:>8,.2f}  {w['status']}"
                for w in repairs))

    em = [k for k, t in triage.items() if t.category == "emergency"]
    page_delay = []
    for p in world.pages:
        rec = datetime.fromisoformat(next(x["received_at"] for x in inbox if x["id"] == p["message_id"]))
        page_delay.append((datetime.fromisoformat(p["paged_at"]) - rec).total_seconds() / 60)
    first_tool = {k: runs[k].calls[0]["tool"] for k in em}
    tr.step("Page on-call staff at once for any emergency", kind="code",
            what=f"Emergencies run first and the agent's first tool call is the pager: {len(world.pages)}/{len(em)} paged within {max(page_delay):.0f} minute, with a 24/7 vendor dispatched.",
            code=('order = sorted(inbox, key=lambda m: (triage[m["id"]].category != "emergency", m["received_at"]))\n'
                  'page_on_call(message_id, unit, summary)   # first tool call for every emergency'),
            output=show("M05") + "\n\nPages sent:\n" + "\n".join(json.dumps(pg) for pg in world.pages)
            + f"\nfirst tool per emergency: {first_tool}")

    # Step 5: manager approves vendor spend over the limit in Slack (simulated approval queue)
    decisions = json.loads((DATA / "manager_decisions.json").read_text())
    for a in world.approvals:
        wo_id = a["blocks"][-1]["elements"][0]["value"]
        d = decisions.get(wo_id, decisions["default"])
        wo = next(w for w in world.work_orders if w["wo_id"] == wo_id)
        decided = datetime.fromisoformat(a["posted_at"]) + timedelta(minutes=d["minutes_to_decide"])
        a["response"] = {"action_id": f"{d['decision']}_spend", "user": d["by"], "at": decided.isoformat(timespec="minutes")}
        wo["status"] = "scheduled" if d["decision"] == "approve" else "rejected"
        wo["approved_by"] = d["by"]
    em_wos = [w for w in world.work_orders if w["priority"] == "emergency"]
    tr.step("Manager approves vendor spend over the limit in Slack", kind="human",
            what=f"{len(world.approvals)} work orders over ${SPEND_LIMIT:.0f} were posted to #maintenance-approvals with Approve/Reject buttons; nothing was booked until a manager clicked. Emergency call-outs (${sum(w['estimate_usd'] for w in em_wos):,.2f}) skip the queue by policy and are reviewed after.",
            code=('slack = {"channel": "#maintenance-approvals", "blocks": [header, fields,\n'
                  '         {"type": "actions", "elements": [approve_btn, reject_btn]}]}\n'
                  'wo["status"] = "scheduled" if decision == "approve" else "rejected"'),
            output=slack_preview(world.approvals[0]) + "\n\nQueue:\n" + "\n".join(
                f"  {a['text']} -> {a['response']['action_id']} by {a['response']['user']} at {a['response']['at']}"
                for a in world.approvals))

    # Evaluation + response-time metrics
    key = json.loads((DATA / "answer_key.json").read_text())
    correct = [k for k in key if triage[k].category == key[k]]
    wrong = {k: f"{triage[k].category} (key: {key[k]})" for k in key if k not in correct}
    em_key = [k for k, v in key.items() if v == "emergency"]
    em_paged = [k for k in em_key if any(p["message_id"] == k for p in world.pages)]

    def before_first_response(rec: datetime) -> datetime:
        # Old process: two office staff work the shared inbox 9-5 Mon-Fri, about 3 working hours behind.
        t, office_minutes = rec, 0
        while office_minutes < 180:
            if not after_hours(t):
                office_minutes += 15
            t += timedelta(minutes=15)
        return t

    before_h, after_min, ah_cov = [], [], 0
    for m in inbox:
        rec = datetime.fromisoformat(m["received_at"])
        before_h.append((before_first_response(rec) - rec).total_seconds() / 3600)
        sent = datetime.fromisoformat(next(o["sent_at"] for o in world.outbox if o["message_id"] == m["id"]))
        sent = max(sent, rec + timedelta(seconds=runtime[m["id"]]))
        after_min.append((sent - rec).total_seconds() / 60)
        if after_hours(rec) and sent < next_office_open(rec):
            ah_cov += 1
    med = lambda xs: sorted(xs)[len(xs) // 2]
    tr.step("Check against the answer key and time every reply", kind="check",
            what="A property manager hand-labelled all 15 messages; we score the triage and compare first-response times with the old office-hours process.",
            code=('accuracy = mean(triage[k].category == key[k] for k in key)\n'
                  'before = office_hours_queue(received)   # 9-5 Mon-Fri, ~3 working hours behind\n'
                  'after  = outbox[k]["sent_at"] - received'),
            output={"category_accuracy": f"{len(correct)}/{len(key)} ({len(correct)/len(key):.0%})",
                    "misclassified": wrong or "none",
                    "emergencies_paged": f"{len(em_paged)}/{len(em_key)}",
                    "median_first_response": f"{med(before_h):.1f} h before -> {med(after_min):.0f} min after",
                    "worst_first_response": f"{max(before_h):.1f} h before -> {max(after_min):.0f} min after",
                    "after_hours_answered_before_office_opens": f"0/{len(ah)} before -> {ah_cov}/{len(ah)} after",
                    "answers_with_source": f"{cited}/{len(qs)}",
                    "spend_over_limit_without_approval": sum(1 for w in world.work_orders if w["needs_approval"] and not w.get("approved_by"))})

    (HERE / "outputs/triage_log.json").write_text(json.dumps(
        [{"message": m, "triage": triage[m["id"]].model_dump(), "tool_calls": runs[m["id"]].calls,
          "reply": next(o for o in world.outbox if o["message_id"] == m["id"])} for m in inbox], indent=2, default=str))
    (HERE / "outputs/work_orders.json").write_text(json.dumps(world.work_orders, indent=2))
    (HERE / "outputs/slack_approvals.json").write_text(json.dumps(world.approvals, indent=2))
    (HERE / "outputs/pages.json").write_text(json.dumps(world.pages, indent=2))

    tr.metrics(median_first_response=f"{med(before_h):.1f} h -> {med(after_min):.0f} min",
               after_hours_coverage=f"0/{len(ah)} -> {ah_cov}/{len(ah)} answered before the office opens",
               emergencies_routed=f"{len(em_paged)}/{len(em_key)} paged within {max(page_delay):.0f} min (before: {max(before_h[i] for i, m in enumerate(inbox) if key[m['id']] == 'emergency'):.1f} h worst case)",
               triage_accuracy=f"{len(correct)}/{len(key)} ({len(correct)/len(key):.0%})",
               answers_citing_lease_or_faq=f"{cited}/{len(qs)}",
               work_orders_drafted=len(world.work_orders),
               spend_approvals_in_slack=len(world.approvals),
               tool_calls=sum(len(r.calls) for r in runs.values()))
    tr.save()


if __name__ == "__main__":
    main()
