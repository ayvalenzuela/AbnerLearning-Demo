"""Generate a synthetic tenant inbox, lease, FAQ, vendor list and ledger (no real tenant data)."""
import json
from pathlib import Path

D = Path("data")
D.mkdir(exist_ok=True)

# 15 tenant messages over one week (Mon 16 - Sun 22 Nov 2026), email and SMS.
# "label" is NOT given to the pipeline: it goes into the answer key below.
MESSAGES = [
    ("M01", "sms",   "2026-11-21T22:47", "4B", "Water is pouring through the ceiling from the unit above, it's all over the kitchen floor!", "emergency"),
    ("M02", "email", "2026-11-16T10:15", "2A", "Hi, what day is rent due each month, and is there a grace period?", "question"),
    ("M03", "sms",   "2026-11-16T19:30", "3C", "Kitchen sink is clogged and draining really slowly.", "repair"),
    ("M04", "email", "2026-11-17T09:05", "1D", "I was charged a $75 late fee but I paid rent on the 2nd. Can you check?", "billing"),
    ("M05", "sms",   "2026-11-18T02:10", "5A", "I smell gas near the stove, it's strong. What do I do?", "emergency"),
    ("M06", "email", "2026-11-17T13:40", "2C", "Can I have a cat in my apartment? Is there a pet deposit?", "question"),
    ("M07", "email", "2026-11-17T21:15", "4A", "The dishwasher stopped working and leaks a little water onto the floor when it runs.", "repair"),
    ("M08", "sms",   "2026-11-18T07:20", "1B", "Where do I put recycling and what day is pickup?", "question"),
    ("M09", "email", "2026-11-18T11:00", "3A", "The heater makes a loud banging noise and the bedroom stays cold at night.", "repair"),
    ("M10", "sms",   "2026-11-18T23:05", "5C", "Can I get a receipt for my October rent payment? Need it for taxes.", "billing"),
    ("M11", "email", "2026-11-19T15:30", "2B", "How much notice do I need to give before I move out?", "question"),
    ("M12", "sms",   "2026-11-19T18:45", "3D", "Bathroom exhaust fan is broken, it makes no sound at all.", "repair"),
    ("M13", "email", "2026-11-20T08:30", "1A", "Is guest parking available overnight for a visitor this weekend?", "question"),
    ("M14", "email", "2026-11-20T20:10", "4C", "The refrigerator isn't cooling anymore and food is going bad.", "repair"),
    ("M15", "sms",   "2026-11-22T12:00", "5B", "My autopay didn't go through this month, how do I pay my balance?", "billing"),
]
inbox = [{"id": i, "channel": ch, "received_at": t, "unit": u, "text": txt} for i, ch, t, u, txt, _ in MESSAGES]
(D / "inbox.json").write_text(json.dumps(inbox, indent=2))
(D / "answer_key.json").write_text(json.dumps({i: lab for i, *_, lab in MESSAGES}, indent=2))

LEASE = """# Residential Lease (Maple Court Apartments)
## 4.1 Rent due date
Rent is due on the 1st day of each month. A grace period runs through the 5th day of the month. Rent received after the 5th incurs a $75 late fee.
## 4.3 Payment methods
Rent can be paid by autopay, one-time online payment in the resident portal, or certified check at the office. If an autopay fails, pay the balance online within 5 days to avoid a late fee.
## 7.2 Pets
Cats and dogs under 40 lb are allowed with written approval. A refundable pet deposit of $400 and pet rent of $35 per month apply.
## 9.1 Notice to vacate
Residents must give written notice at least 60 days before moving out. Notice is submitted in the resident portal or by letter to the office.
## 11.4 Tenant-caused damage
Repairs needed because of tenant misuse are billed to the tenant after inspection.
"""
FAQ = """# Resident FAQ
## Recycling and trash
Recycling goes in the blue bins in the garage, level P1. Pickup is every Tuesday morning; bins must be out by 7am.
## Guest parking
Guest parking is in the marked spaces on the north lot. Overnight guest parking needs a free permit from the resident portal, valid up to 3 nights.
## Gas smell
If you smell gas, leave the unit at once, do not switch lights or appliances on or off, and call 911 and the gas utility from outside. Then call the emergency line.
## Water leak or flooding
For active water leaks, shut off the water valve under the sink or behind the toilet if safe, move valuables away, and call the emergency line. Maintenance responds within 1 hour.
## Rent receipts
Receipts for every payment are in the resident portal under Payments > History. The office can email a signed copy on request.
## Office hours
The office is open Monday to Friday, 9am to 5pm. Emergencies are covered 24/7 by the on-call manager.
"""
(D / "lease.md").write_text(LEASE)
(D / "faq.md").write_text(FAQ)

VENDORS = [
    {"vendor": "BlueLine Plumbing",   "trade": "plumbing",   "hourly": 120, "after_hours_24_7": True,
     "open_slots": ["2026-11-17T08:00", "2026-11-17T14:00", "2026-11-19T10:00", "2026-11-23T09:00"]},
    {"vendor": "Apex Appliance Repair", "trade": "appliance", "hourly": 95, "after_hours_24_7": False,
     "open_slots": ["2026-11-19T13:00", "2026-11-20T09:00", "2026-11-23T11:00", "2026-11-24T10:00"]},
    {"vendor": "Northside HVAC",      "trade": "hvac",       "hourly": 140, "after_hours_24_7": True,
     "open_slots": ["2026-11-19T08:00", "2026-11-20T15:00", "2026-11-24T08:00"]},
    {"vendor": "Brightwire Electric", "trade": "electrical", "hourly": 110, "after_hours_24_7": False,
     "open_slots": ["2026-11-20T10:00", "2026-11-23T13:00"]},
    {"vendor": "Metro Gas Response",  "trade": "gas",        "hourly": 150, "after_hours_24_7": True,
     "open_slots": []},
]
(D / "vendors.json").write_text(json.dumps(VENDORS, indent=2))

# Price book: typical hours + parts per issue, used to estimate work-order spend.
PRICE_BOOK = {
    "clog":         {"keywords": ["clog", "drain"],          "trade": "plumbing",   "hours": 1.5, "parts": 0},
    "dishwasher":   {"keywords": ["dishwasher"],             "trade": "appliance",  "hours": 2.0, "parts": 190},
    "heater":       {"keywords": ["heater", "furnace"],      "trade": "hvac",       "hours": 3.0, "parts": 230},
    "exhaust fan":  {"keywords": ["fan"],                    "trade": "electrical", "hours": 1.0, "parts": 85},
    "refrigerator": {"keywords": ["refrigerator", "fridge"], "trade": "appliance",  "hours": 2.5, "parts": 480},
    "ceiling leak": {"keywords": ["ceiling", "pouring"],     "trade": "plumbing",   "hours": 6.0, "parts": 350},
    "gas leak":     {"keywords": ["gas"],                    "trade": "gas",        "hours": 2.0, "parts": 0},
}
(D / "price_book.json").write_text(json.dumps(PRICE_BOOK, indent=2))

LEDGER = {
    "1D": [{"date": "2026-11-02", "type": "payment", "amount": 1850.00, "ref": "ACH 88123"},
           {"date": "2026-11-06", "type": "late_fee", "amount": 75.00, "ref": "AUTO-LF"}],
    "5C": [{"date": "2026-10-01", "type": "payment", "amount": 1725.00, "ref": "ACH 77410"},
           {"date": "2026-11-01", "type": "payment", "amount": 1725.00, "ref": "ACH 80122"}],
    "5B": [{"date": "2026-11-01", "type": "autopay_failed", "amount": 1640.00, "ref": "NSF R01"}],
}
(D / "tenant_ledger.json").write_text(json.dumps(LEDGER, indent=2))

ON_CALL = {"name": "Rosa Imani", "role": "on-call property manager", "phone": "+1-555-0142"}
(D / "on_call.json").write_text(json.dumps(ON_CALL, indent=2))

# What the manager clicked in Slack (simulated human decisions for the approval queue).
(D / "manager_decisions.json").write_text(json.dumps(
    {"default": {"decision": "approve", "by": "Jordan Wells (portfolio manager)", "minutes_to_decide": 22}}, indent=2))
print(f"wrote {len(inbox)} messages, lease, FAQ, {len(VENDORS)} vendors, ledger, answer key")
