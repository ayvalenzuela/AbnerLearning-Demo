"""Generate 12 synthetic sales-call transcripts (no real customer data)."""
import json, random
from pathlib import Path

random.seed(7)
REPS = ["Dana Ortiz", "Marcus Lee", "Priya Shah", "Tom Becker"]
COMPANIES = ["Northwind Dental", "Bluepeak Logistics", "Harbor Credit Union", "Cobalt Labs",
             "Summit Realty", "Gridline Energy"]
GOOD = [
    "Before I pitch anything, can you walk me through how calls get routed today?",
    "What happens when a call is missed after hours, and what does that cost you?",
    "So if I heard you right, the pain is dropped calls during the lunch rush. Did I get that right?",
    "Who else needs to be part of this decision, and when are you looking to go live?",
    "Let's book thirty minutes Thursday with your IT lead to look at the number port. Does 2pm work?",
]
WEAK = [
    "So our platform has 99.999 percent uptime, AI transcription, and over 200 integrations.",
    "Honestly it's the best product on the market, everyone loves it.",
    "I'll just send you some info and you can let me know.",
    "We can definitely give you a discount if you sign this week.",
]
RISK = "This call isn't being recorded, so don't worry about what we say."
OBJ = ["We already have a contract with our current provider.", "Price is the big concern for us.",
       "I'm not sure we have time to switch right now."]

calls = []
for i in range(12):
    rep = REPS[i % 4]
    quality = ["strong", "mixed", "weak"][i % 3]
    lines = [f"REP: Hi, this is {rep} from Voxly. Thanks for taking the call.",
             f"PROSPECT: Sure. I'm the office manager at {random.choice(COMPANIES)}."]
    pool = GOOD if quality == "strong" else (GOOD[:2] + WEAK[:2] if quality == "mixed" else WEAK)
    for s in pool:
        lines.append(f"REP: {s}")
        lines.append(f"PROSPECT: {random.choice(OBJ) if random.random() < .4 else 'Okay, that makes sense.'}")
    if i in (5, 10):
        lines.append(f"REP: {RISK}")
    calls.append({"call_id": f"CALL-{1001+i}", "rep": rep, "duration_sec": random.randint(240, 1500),
                  "transcript": "\n".join(lines)})

Path("data").mkdir(exist_ok=True)
Path("data/calls.json").write_text(json.dumps(calls, indent=2))
# A sales manager hand-scored 12 calls: the 'answer key' used for the eval step.
key = {c["call_id"]: (88 if i % 3 == 0 else 62 if i % 3 == 1 else 30) for i, c in enumerate(calls)}
Path("data/manager_scores.json").write_text(json.dumps(key, indent=2))
print(f"wrote {len(calls)} calls")
