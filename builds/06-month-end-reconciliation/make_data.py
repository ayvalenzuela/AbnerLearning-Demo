"""Generate a synthetic November 2026 bank export and GL cash ledger with planted exceptions."""
import json, random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

random.seed(11)
D = Path("data")
D.mkdir(exist_ok=True)

# Ledger vendor name -> how the same payee shows up on the bank statement
VENDORS = {
    "Amazon Web Services": "AMAZON WEB SVCS AWS.COM BILL",
    "Staples Business": "STAPLES BUSINESS #0442",
    "Gusto Payroll": "GUSTO PAYROLL 8842 ACH",
    "Pacific Gas and Electric": "PACIFIC GAS ELEC PMT",
    "Comcast Business": "COMCAST BUSINESS 8155",
    "Uline": "ULINE *SHIP SUPPLIES",
    "Delta Air Lines": "DELTA AIR 0062341",
    "WeWork": "WEWORK INC MEMBERSHIP",
    "Salesforce": "SALESFORCE.COM SFDC",
    "FedEx": "FEDEX 781234556",
    "Office Depot": "OFFICE DEPOT #221",
    "Adobe": "ADOBE *CREATIVE CLD",
    "Lyft": "LYFT *RIDE TUE 8PM",
    "Zoom Video": "ZOOM.US 888-799",
}
CUSTOMERS = {
    "Acme Corp": "DEPOSIT ACME CORP ACH CR",
    "Brightline Health": "BRIGHTLINE HEALTH ACH CR",
    "Northwind Dental": "NORTHWIND DENTAL WIRE IN",
    "Cobalt Labs": "COBALT LABS ACH CREDIT",
}
FOREIGN = {"Delta Air Lines", "Adobe"}  # card charges that settle a few cents different (FX)
ACCOUNTS = {"Amazon Web Services": "6100 Software", "Staples Business": "6200 Office supplies",
            "Gusto Payroll": "6000 Payroll", "Pacific Gas and Electric": "6300 Utilities",
            "Comcast Business": "6310 Telecom", "Uline": "5100 Shipping supplies", "Delta Air Lines": "6500 Travel",
            "WeWork": "6400 Rent", "Salesforce": "6100 Software", "FedEx": "5110 Freight",
            "Office Depot": "6200 Office supplies", "Adobe": "6100 Software", "Lyft": "6500 Travel",
            "Zoom Video": "6100 Software"}

start = date(2026, 11, 1)
bank, ledger, pairs = [], [], {}


def add(ledger_date, name, amount, bank_shift=0, bank_amount=None, memo=""):
    lid = f"GL-{len(ledger) + 1:04d}"
    is_cust = name in CUSTOMERS
    ledger.append({"line_id": lid, "date": ledger_date.isoformat(), "payee": name, "amount": round(amount, 2),
                   "account": "1200 Accounts receivable" if is_cust else ACCOUNTS[name], "memo": memo})
    if bank_shift is None:
        return lid, None
    bid = f"BK-{len(bank) + 1:04d}"
    bank.append({"line_id": bid, "date": (ledger_date + timedelta(days=bank_shift)).isoformat(),
                 "description": (CUSTOMERS | VENDORS)[name],
                 "amount": round(bank_amount if bank_amount is not None else amount, 2)})
    pairs[lid] = bid
    return lid, bid


key = []
# 190 ordinary transactions: most clear the same day, some 1-3 days later, a few settle with FX cents
for i in range(190):
    d = start + timedelta(days=random.randint(0, 26))
    if random.random() < 0.12:
        name = random.choice(list(CUSTOMERS))
        amt = round(random.uniform(1500, 18000), 2)
    else:
        name = random.choice(list(VENDORS))
        amt = -round(random.uniform(25, 4800), 2)
    r = random.random()
    if name in FOREIGN and r < 0.6:
        add(d, name, amt, bank_shift=random.choice([0, 1]), bank_amount=amt + random.choice([-0.37, -0.12, 0.08, 0.21]),
            memo=f"card {random.randint(1000, 9999)}")
    elif r < 0.09:
        add(d, name, amt, bank_shift=random.randint(1, 3), memo=f"ACH INV {random.randint(10000, 99999)}")
    else:
        add(d, name, amt, memo=f"INV {random.randint(10000, 99999)}")

# ---- Planted exceptions (the answer key) ----
def bank_only(d, desc, amt):
    bid = f"BK-{len(bank) + 1:04d}"
    bank.append({"line_id": bid, "date": d.isoformat(), "description": desc, "amount": amt})
    return bid

key.append({"type": "bank_fee", "lines": [bank_only(date(2026, 11, 30), "MONTHLY SERVICE FEE", -25.00)]})
key.append({"type": "bank_fee", "lines": [bank_only(date(2026, 11, 18), "OUTGOING WIRE TRANSFER FEE", -35.00)]})
key.append({"type": "bank_fee", "lines": [bank_only(date(2026, 11, 22), "INTL TRANSACTION FEE", -4.12)]})
# duplicate payment: Uline invoice paid twice by the bank, booked once
_, b1 = add(date(2026, 11, 10), "Uline", -1486.20, memo="INV 55120")
key.append({"type": "duplicate_payment", "lines": [bank_only(date(2026, 11, 12), VENDORS["Uline"], -1486.20)]})
# transposed amount: bank cleared 2,351.40, ledger keyed 2,315.40
lid, _ = add(date(2026, 11, 16), "Comcast Business", -2315.40, bank_shift=None, memo="INV CB-7781")
key.append({"type": "transposed_amount", "lines": [lid, bank_only(date(2026, 11, 16), VENDORS["Comcast Business"], -2351.40)]})
# timing differences: check and deposit booked on the 30th, not yet through the bank
lid, _ = add(date(2026, 11, 30), "WeWork", -4200.00, bank_shift=None, memo="CHECK 1043 December rent")
key.append({"type": "timing_difference", "lines": [lid]})
lid, _ = add(date(2026, 11, 30), "Brightline Health", 6750.00, bank_shift=None, memo="Deposit in transit")
key.append({"type": "timing_difference", "lines": [lid]})
# unknown vendor: card charge nobody booked, payee not in the vendor master
key.append({"type": "unknown_vendor", "lines": [bank_only(date(2026, 11, 24), "SQ *KAIZEN COFFEE ROASTER", -312.80)]})

# Bank line ids follow statement order, not ledger order (real exports share no keys)
bank_df = pd.DataFrame(bank).sample(frac=1, random_state=3).sort_values("date", kind="stable")
new_ids = {old: f"BK-{i + 1:04d}" for i, old in enumerate(bank_df.line_id)}
bank_df["line_id"] = bank_df.line_id.map(new_ids)
for k in key:
    k["lines"] = [new_ids.get(l, l) for l in k["lines"]]
ledger_df = pd.DataFrame(ledger).sort_values("date", kind="stable")
bank_df.to_csv(D / "bank_export_2026-11.csv", index=False)
ledger_df.to_csv(D / "ledger_export_2026-11.csv", index=False)
(D / "vendor_master.json").write_text(json.dumps(sorted(VENDORS) + sorted(CUSTOMERS), indent=2))
(D / "true_pairs.json").write_text(json.dumps({l: new_ids[b] for l, b in pairs.items()}, indent=2))
(D / "planted_exceptions.json").write_text(json.dumps(key, indent=2))
print(f"wrote {len(bank_df)} bank lines, {len(ledger_df)} ledger lines, {len(key)} planted exceptions")
