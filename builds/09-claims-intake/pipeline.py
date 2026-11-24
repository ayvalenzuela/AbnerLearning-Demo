"""Build 09 - Claims intake and extraction (Insurance). Pattern: vision + workflow.

Each first-notice-of-loss packet (police report PDF/PNG, damage photo, phone note) goes to Claude in
one call and comes back as the claims schema with a confidence per field. Code then checks coverage,
runs fraud rules and routes by severity. Any field under the confidence bar goes to a person before
the claim is saved.
"""
import json, re, sys, uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, ask_structured, _strict_schema, MODEL  # noqa: E402
from common.vision_extract import packet_content  # noqa: E402

HERE = Path(__file__).parent
D = lambda name: json.loads((HERE / "data" / f"{name}.json").read_text())
CONF_BAR = 0.80
FIELDS = ["policy_number", "claimant_name", "phone", "loss_date", "loss_location", "police_report_number",
          "vin", "vehicle_year", "vehicle_make", "vehicle_model", "injuries", "estimated_amount_usd",
          "damage_severity"]


class ExtractedField(BaseModel):
    name: str = Field(description="one of the claims-schema field names")
    value: str | None = Field(description="normalised value; dates as YYYY-MM-DD; null if not found")
    confidence: float = Field(description="0-1: how sure you are this value is right")
    source: str = Field(description="police_report | phone_note | damage_photo | both")

class ClaimExtraction(BaseModel):
    claim_id: str
    fields: list[ExtractedField]
    notes: str = Field(description="conflicts between documents, unreadable parts")

SYSTEM = ("You are a claims intake specialist. Extract every field of the claims schema from the packet: "
          f"{', '.join(FIELDS)}. damage_severity is minor, moderate or severe, judged from the photo. "
          "injuries is yes or no. Give a confidence per field. Lower the confidence when documents disagree, "
          "when a value fails a format check (a VIN is 17 characters with a valid check digit), or when it is "
          "a guess. Prefer the police report over the phone note when they conflict, and say so in notes.")


# ---------- offline stand-in: real parsing, real pixel maths ----------
TRANSLIT = {**{str(d): d for d in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))),
            **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

def vin_valid(v: str | None) -> bool:
    if not v or len(v) != 17 or any(c not in TRANSLIT for c in v):
        return False
    r = sum(TRANSLIT[c] * w for c, w in zip(v, WEIGHTS)) % 11
    return v[8] == ("X" if r == 10 else str(r))

def damage_from_photo(path: Path) -> tuple[str, float, float]:
    """Share of the vehicle's pixels that are damage-red -> severity, confidence."""
    img = Image.open(path).convert("RGB")
    px = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
    bg = px[0]
    body = sum(1 for p in px if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 30)
    red = sum(1 for r, g, b in px if r > 150 and g < 90 and b < 90)
    share = red / max(1, body)
    sev = "minor" if share < 0.045 else "moderate" if share < 0.14 else "severe"
    edge = min(abs(share - c) / c for c in (0.045, 0.14))  # within 20% of a cut-off = less sure
    return sev, share, 0.95 if edge > 0.2 else 0.70

def parse_report(text: str) -> dict:
    kv = dict(re.findall(r"^([A-Z ]+):\s*(.+)$", text, flags=re.M))
    year, make, model = (kv.get("VEHICLE", "").split(" ", 2) + [None, None, None])[:3]
    d = kv.get("DATE OF INCIDENT")
    return {"police_report_number": kv.get("REPORT NO"), "claimant_name": kv.get("DRIVER NAME"),
            "loss_date": datetime.strptime(d, "%m/%d/%Y").date().isoformat() if d else None,
            "loss_location": kv.get("LOCATION"), "policy_number": kv.get("INSURANCE POLICY"),
            "vin": kv.get("VIN"), "vehicle_year": year, "vehicle_make": make, "vehicle_model": model,
            "injuries": None if "INJURIES" not in kv else ("no" if "NONE" in kv["INJURIES"] else "yes")}

def parse_phone_note(text: str, year: int = 2026) -> dict:
    g = lambda pat: (m.group(1) if (m := re.search(pat, text)) else None)
    happened = re.search(r"happened (\d{1,2})/(\d{1,2})", text)
    amt = g(r"\$([\d,]+)")
    hurt = re.search(r"nobody hurt|no one hurt|not injured", text, re.I)
    return {"claimant_name": g(r"Caller ([A-Z][a-z]+ [A-Z][a-z]+)"), "policy_number": g(r"policy (PA-\d{6})"),
            "loss_date": date(year, int(happened[1]), int(happened[2])).isoformat() if happened else None,
            "loss_location": g(r"happened \d{1,2}/\d{1,2} at ([^.]+)\."), "phone": g(r"Callback (555-\d{4})"),
            "police_report_number": g(r"Police report (RPD-[\d-]+)"),
            "estimated_amount_usd": amt.replace(",", "") if amt else None,
            "injuries": "no" if hurt else ("yes" if re.search(r"hurt|pain|injur|urgent care", text, re.I) else None)}

def offline_extract(cid: str, folder: Path) -> ClaimExtraction:
    rep = parse_report((folder / "police_report.txt").read_text())
    note = parse_phone_note((folder / "phone_note.txt").read_text())
    out, notes = [], []
    for f in FIELDS:
        if f == "damage_severity":
            sev, share, conf = damage_from_photo(folder / "damage_photo.png")
            out.append(ExtractedField(name=f, value=sev, confidence=conf, source="damage_photo"))
            notes.append(f"damage area {share:.1%} of vehicle")
            continue
        a, b = rep.get(f), note.get(f)
        agree = a and b and (a == b or a.startswith(b) or b.startswith(a))
        if agree:
            val, conf, src = a, 0.98, "both"
        elif a and b:
            val, conf, src = a, 0.55, "police_report"
            notes.append(f"{f}: report says {a}, caller says {b}")
        elif a or b:
            val, conf, src = a or b, 0.90, "police_report" if a else "phone_note"
        else:
            val, conf, src = None, 0.0, "none"
            notes.append(f"{f}: not found in any document")
        if f == "vin" and val and not vin_valid(val):
            conf = 0.35
            notes.append(f"vin {val} fails the check-digit test")
        out.append(ExtractedField(name=f, value=val, confidence=conf, source=src))
    return ClaimExtraction(claim_id=cid, fields=out, notes="; ".join(notes) or "no issues")


# ---------- Step 3-4: coverage, fraud rules, routing (plain code, auditable) ----------
POLICIES = {p["policy_number"]: p for p in D("policies")}
HISTORY = D("claims_history")

def check_and_route(rec: dict) -> dict:
    pol = POLICIES.get(rec.get("policy_number") or "")
    loss = date.fromisoformat(rec["loss_date"]) if rec.get("loss_date") else None
    amount = float(rec["estimated_amount_usd"]) if rec.get("estimated_amount_usd") else None
    coverage, flags = [], []
    if not pol:
        coverage.append("policy not found")
    else:
        if not (loss and date.fromisoformat(pol["start"]) <= loss <= date.fromisoformat(pol["end"])
                and pol["status"] == "active"):
            coverage.append(f"policy not active on loss date (status {pol['status']}, ends {pol['end']})")
        if "collision" not in pol["coverages"]:
            coverage.append("no collision coverage")
        if rec.get("vin") != pol["vehicle"]["vin"]:
            coverage.append("VIN does not match the insured vehicle")
        if loss and (loss - date.fromisoformat(pol["start"])).days <= 30:
            flags.append(f"loss {(loss - date.fromisoformat(pol['start'])).days} days after policy start")
        if amount and amount > 0.8 * pol["vehicle_value_usd"]:
            flags.append(f"estimate ${amount:,.0f} is {amount / pol['vehicle_value_usd']:.0%} of vehicle value")
    dups = [h["claim_id"] for h in HISTORY if h["vin"] == rec.get("vin")]
    if dups:
        flags.append(f"VIN already claimed in {', '.join(dups)}")
    sev = rec.get("damage_severity")
    if flags:
        route = "special_unit"
    elif coverage or sev != "minor" or rec.get("injuries") == "yes" or (amount or 0) >= 5000:
        route = "adjuster"
    else:
        route = "fast_track"
    return {"coverage_issues": coverage, "fraud_flags": flags, "route": route}


def n8n_workflow() -> dict:
    """An importable n8n workflow: webhook -> Claude -> rules -> IF confidence -> claims API / review queue."""
    nid = lambda n: str(uuid.uuid5(uuid.NAMESPACE_URL, f"build09/{n}"))
    claude_req = {"model": MODEL, "max_tokens": 16000, "system": SYSTEM,
                  "output_config": {"format": {"type": "json_schema", "schema": _strict_schema(ClaimExtraction)}}}
    nodes = [
        {"name": "FNOL webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 300],
         "webhookId": nid("hook"), "parameters": {"httpMethod": "POST", "path": "fnol", "responseMode": "onReceived",
                                                  "options": {}}},
        {"name": "Build Claude request", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [240, 300],
         "parameters": {"jsCode": (
             "const base = " + json.dumps(claude_req) + ";\n"
             "const p = $json.body;\n"
             "const content = [\n"
             "  {type: 'document', source: {type: 'base64', media_type: 'application/pdf', data: p.police_report_pdf_b64}},\n"
             "  {type: 'image', source: {type: 'base64', media_type: 'image/png', data: p.damage_photo_b64}},\n"
             "  {type: 'text', text: 'Phone note:\\n' + p.phone_note + '\\nClaim id: ' + p.claim_id},\n"
             "];\n"
             "return [{json: {claim_id: p.claim_id, claude_request: {...base, messages: [{role: 'user', content}]}}}];")}},
        {"name": "Claude extract", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [480, 300],
         "credentials": {"httpHeaderAuth": {"id": "anthropic-api-key", "name": "Anthropic x-api-key"}},
         "parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
                        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                        "sendHeaders": True, "headerParameters": {"parameters": [
                            {"name": "anthropic-version", "value": "2023-06-01"},
                            {"name": "content-type", "value": "application/json"}]},
                        "sendBody": True, "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify($json.claude_request) }}", "options": {"timeout": 120000}}},
        {"name": "Coverage + fraud rules", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [720, 300],
         "parameters": {"jsCode": (
             "const ex = JSON.parse($json.content.find(b => b.type === 'text').text);\n"
             "const minConf = Math.min(...ex.fields.map(f => f.confidence));\n"
             "const rec = Object.fromEntries(ex.fields.map(f => [f.name, f.value]));\n"
             "// same rules as check_and_route() in pipeline.py; policy + history lookups via the claims API\n"
             "return [{json: {...ex, record: rec, min_confidence: minConf,\n"
             "  low_fields: ex.fields.filter(f => f.confidence < " + str(CONF_BAR) + ").map(f => f.name)}}];")}},
        {"name": "All fields confident?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [960, 300],
         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                                       "conditions": [{"id": nid("cond"), "leftValue": "={{ $json.min_confidence }}",
                                                       "rightValue": CONF_BAR,
                                                       "operator": {"type": "number", "operation": "gte"}}],
                                       "combinator": "and"}, "options": {}}},
        {"name": "Claims API: create claim", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [1200, 200],
         "parameters": {"method": "POST", "url": "https://claims.example.internal/api/v1/claims", "sendBody": True,
                        "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.record) }}", "options": {}}},
        {"name": "Human review queue", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [1200, 420],
         "parameters": {"method": "POST", "url": "https://claims.example.internal/api/v1/review-queue",
                        "sendBody": True, "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify({claim_id: $json.claim_id, fields: $json.low_fields, notes: $json.notes}) }}",
                        "options": {}}},
    ]
    for n in nodes:
        n["id"] = nid(n["name"])
    link = lambda to: {"node": to, "type": "main", "index": 0}
    conns = {"FNOL webhook": {"main": [[link("Build Claude request")]]},
             "Build Claude request": {"main": [[link("Claude extract")]]},
             "Claude extract": {"main": [[link("Coverage + fraud rules")]]},
             "Coverage + fraud rules": {"main": [[link("All fields confident?")]]},
             "All fields confident?": {"main": [[link("Claims API: create claim")], [link("Human review queue")]]}}
    return {"name": "FNOL intake - Claude extraction", "nodes": nodes, "connections": conns, "active": False,
            "settings": {"executionOrder": "v1"}, "pinData": {}, "tags": [], "meta": {"templateCredsSetupCompleted": False}}


def main():
    tr = Trace("09", "Claims intake and extraction", HERE / "outputs")
    tr.arch([
        {"label": "FNOL packet", "kind": "data", "note": "report PDF, photo, phone note"},
        {"label": "n8n webhook", "kind": "system", "note": "one run per claim"},
        {"label": "Claude vision", "kind": "ai", "note": "schema + confidence per field"},
        {"label": "Coverage + fraud rules", "kind": "code", "note": "auditable checks"},
        {"label": "Severity routing", "kind": "code", "note": "fast-track / adjuster / SIU"},
        {"label": "Review queue", "kind": "human", "note": "low-confidence fields"},
        {"label": "Claims system API", "kind": "system", "note": "save only when clean"},
    ])
    tr.story(
        situation="A regional auto insurer takes about 300 first notices of loss a week. Each arrives as photos, a police report and a phone note, and an adjuster retypes it all into the claims system before anyone triages it.",
        constraints="Nothing reaches the claims system unless every field is confident or a person has checked it. Fraud and coverage rules stay in plain code so auditors can read them. Claimant data stays inside the insurer's tenant.",
        replay="Reuse: 'extract with a confidence per field, check with plain rules, send only the doubtful fields to a person' fits any document intake (loan files, invoices, onboarding). Next time: measure reviewer edits per field and tune the confidence bar per field rather than one bar for all.",
    )

    packets = D("packets")
    p0 = HERE / "data/packets" / packets[0]["claim_id"]
    tr.step("Gather the claim packet", kind="io",
            what=f"Collected {len(packets)} synthetic FNOL packets: police report (PNG + PDF), damage photo, phone note.",
            code=("for p in packets:\n"
                  "    files = [p / 'police_report.pdf', p / 'damage_photo.png',\n"
                  "             p / 'phone_note.txt']\n"
                  "    content = packet_content(files, instructions)  # document + image blocks"),
            output="Packet " + packets[0]["claim_id"] + ":\n" + "\n".join(
                f"  {f}  ({(p0 / f).stat().st_size // 1024 or 1} KB)" for f in packets[0]["files"])
            + "\n\nphone_note.txt:\n" + (p0 / "phone_note.txt").read_text().strip())

    extractions = {}
    for p in packets:
        cid, folder = p["claim_id"], HERE / "data/packets" / p["claim_id"]
        content = packet_content([folder / "police_report.pdf", folder / "damage_photo.png", folder / "phone_note.txt"],
                                 f"Claim id: {cid}. Extract the claims schema.")
        extractions[cid] = ask_structured(system=SYSTEM, content=content, schema=ClaimExtraction,
                                          offline=lambda cid=cid, folder=folder: offline_extract(cid, folder))
    ex3 = extractions["CLM-5003"]
    tr.step("Extract fields into the claims schema, with a confidence per field", kind="ai",
            what="One vision call per packet reads the report and photo together; offline, the stand-in parses the OCR text, the phone note, and measures the red damage area in the photo.",
            code=("ex = ask_structured(system=SYSTEM, content=content,\n"
                  "                    schema=ClaimExtraction)\n"
                  "# offline: regex on report + note; severity from red pixels\n"
                  "share = red_pixels / vehicle_pixels  # <4.5% minor, <14% moderate"),
            output=f"{ex3.claim_id}:\n" + "\n".join(
                f"  {f.name:<22}{str(f.value):<38}{f.confidence:.2f}  {f.source}" for f in ex3.fields)
            + f"\n  notes: {ex3.notes}")

    records, checks = {}, {}
    for cid, ex in extractions.items():
        records[cid] = {f.name: f.value for f in ex.fields}
        checks[cid] = check_and_route(records[cid])
    tr.step("Check coverage and run fraud rules", kind="check",
            what="Plain-code rules: policy active on the loss date, VIN on the policy, claim soon after policy start, estimate vs vehicle value, VIN claimed before.",
            code=("if not pol.start <= loss <= pol.end: coverage.append('not active')\n"
                  "if (loss - pol.start).days <= 30: flags.append('new policy')\n"
                  "if amount > 0.8 * pol.vehicle_value: flags.append('amount')\n"
                  "if vin in prior_claim_vins: flags.append('duplicate VIN')"),
            output="\n".join(f"{cid}  coverage: {'; '.join(c['coverage_issues']) or 'ok'}  |  fraud: "
                             f"{'; '.join(c['fraud_flags']) or 'none'}" for cid, c in checks.items()))

    tr.step("Route by severity: fast-track, adjuster or special unit", kind="code",
            what="Fraud flags go to the special investigations unit; coverage questions, injuries or moderate-plus damage go to an adjuster; the rest fast-track.",
            code=("route = ('special_unit' if flags else\n"
                  "         'adjuster' if coverage or severity != 'minor'\n"
                  "                    or injuries or amount >= 5000 else\n"
                  "         'fast_track')"),
            output="\n".join(f"{cid}  {records[cid]['damage_severity']:<9} injuries={records[cid]['injuries'] or '?':<4}"
                             f" ${records[cid]['estimated_amount_usd'] or '?':<6} -> {c['route']}" for cid, c in checks.items()))

    # Step 5: human review queue for low-confidence fields, then save
    key, base = D("answer_key"), D("baseline")
    route_before = {cid: c["route"] for cid, c in checks.items()}
    queue, saved, review_min, rerouted = [], {}, {}, []
    for cid, ex in extractions.items():
        low = [f for f in ex.fields if f.confidence < CONF_BAR]
        rec = dict(records[cid])
        if low:
            # the reviewer opens the original images and types the right value (simulated from the answer key)
            for f in low:
                queue.append({"claim_id": cid, "field": f.name, "extracted": f.value, "confidence": f.confidence,
                              "reviewer_value": key[cid][f.name]})
                rec[f.name] = key[cid][f.name]
            review_min[cid] = base["review_overhead_minutes_per_claim"] + base["review_minutes_per_field"] * len(low)
            new = check_and_route(rec)
            if new["route"] != checks[cid]["route"]:
                rerouted.append(f"{cid}: {checks[cid]['route']} -> {new['route']}")
            checks[cid] = new
        saved[cid] = {**rec, **checks[cid], "reviewed_fields": [f.name for f in low]}
    out = HERE / "outputs"
    (out / "review_queue.json").write_text(json.dumps(queue, indent=2))
    (out / "claims_saved.json").write_text(json.dumps(saved, indent=2))
    (out / "n8n_workflow.json").write_text(json.dumps(n8n_workflow(), indent=2))
    tr.step("Low-confidence fields go to a person before anything is saved", kind="human",
            what=f"{len(queue)} fields on {len(review_min)} claims fell under the {CONF_BAR:.0%} bar and were checked against the originals; the rest saved straight through.",
            code=("low = [f for f in ex.fields if f.confidence < 0.80]\n"
                  "if low: review_queue.post(claim_id, low)   # n8n IF node, false branch\n"
                  "else:   claims_api.post(record)            # true branch\n"
                  "route = check_and_route(record_after_review)"),
            output="\n".join(f"{q['claim_id']}  {q['field']:<21} extracted={str(q['extracted']):<20} "
                             f"conf={q['confidence']:.2f}  reviewer={q['reviewer_value']}" for q in queue)
            + "\n\nRe-routed after review: " + ("; ".join(rerouted) or "none"))

    # Step 6: score against the answer key
    def acc(recs):
        pairs = [(recs[c].get(f), key[c][f]) for c in key for f in FIELDS]
        return sum(a == b for a, b in pairs) / len(pairs), len(pairs)
    auto_acc, n_fields = acc(records)
    saved_acc, _ = acc(saved)
    route_ok = sum(saved[c]["route"] == key[c]["route"] for c in key)
    wrong_auto = [f"{c}.{f}: got {records[c].get(f)}, truth {key[c][f]}" for c in key for f in FIELDS
                  if records[c].get(f) != key[c][f]]
    flagged_wrong = sum(1 for w in wrong_auto if any(q["claim_id"] + "." + q["field"] == w.split(":")[0] for q in queue))
    tr.step("Score field accuracy against the answer key", kind="check",
            what="A claims supervisor hand-keyed the true values for all 8 packets; we score extraction before and after review.",
            code=("acc = mean(record[c][f] == key[c][f]\n"
                  "           for c in claims for f in FIELDS)\n"
                  "caught = wrong fields that were sent to review / all wrong fields"),
            output={"fields_scored": n_fields, "auto_accuracy": f"{auto_acc:.1%}", "saved_accuracy": f"{saved_acc:.1%}",
                    "wrong_before_review": wrong_auto,
                    "wrong_fields_caught_by_confidence_bar": f"{flagged_wrong}/{len(wrong_auto)}",
                    "route_accuracy_before_review": f"{sum(route_before[c] == key[c]['route'] for c in key)}/{len(key)}",
                    "route_accuracy_saved": f"{route_ok}/{len(key)}"})

    # timing: old = one clerk retypes in arrival order; new = review minutes only, then auto acknowledgement
    t = datetime.fromisoformat(base["clerk_day_starts"]); old_first, new_first = [], []
    for p in sorted(packets, key=lambda p: p["received_at"]):
        rcv = datetime.fromisoformat(p["received_at"])
        t = max(t, rcv) + timedelta(minutes=base["manual_retype_minutes_per_claim"])
        old_first.append((t - rcv).total_seconds() / 60)
        new_first.append(review_min.get(p["claim_id"], 0) + base["auto_acknowledgement_minutes"])
    intake_new = sum(review_min.values()) / len(packets)
    tr.metrics(
        intake_minutes_per_claim=f"{base['manual_retype_minutes_per_claim']} -> {intake_new:.1f} (average human minutes)",
        data_accuracy=f"{auto_acc:.1%} auto -> {saved_acc:.1%} saved after review",
        fields_sent_to_review=f"{len(queue)}/{n_fields}",
        time_to_first_contact_min=f"{sum(old_first) / len(old_first):.0f} -> {sum(new_first) / len(new_first):.0f} (average)",
        route_accuracy=f"{route_ok}/{len(key)}",
        routes={r: sum(1 for s in saved.values() if s["route"] == r) for r in ("fast_track", "adjuster", "special_unit")},
    )
    tr.save()


if __name__ == "__main__":
    main()
