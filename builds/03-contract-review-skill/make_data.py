"""Generate 10 synthetic past contracts (4 NDAs, 6 MSAs), the partner's final calls, and associates' history.

All parties are fictional. Each clause is written from a known value, and some are phrased the way real
drafters write them (for example "two times the annual fees" or indemnities split across two sentences).
"""
import json, random
from pathlib import Path

random.seed(11)
HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
PLAYBOOK = json.loads((HERE / "skill/contract-review/playbook.json").read_text())["rules"]

WORDS = {3: "three", 4: "four", 5: "five", 7: "seven", 10: "ten", 12: "twelve", 18: "eighteen", 24: "twenty-four",
         30: "thirty", 36: "thirty-six", 45: "forty-five", 60: "sixty", 75: "seventy-five", 90: "ninety", 120: "one hundred twenty"}
num = lambda n: f"{WORDS.get(n, n)} ({n})"


def clause(ctype, v):
    """Return (heading, text, true_value) for a clause type and a chosen variant."""
    h = PLAYBOOK[ctype]["title"]
    if ctype == "confidentiality_term":
        if v == "perpetual":
            return h, "The Receiving Party's obligations under this Section survive in perpetuity.", "perpetual"
        return h, f"The Receiving Party shall hold Confidential Information in confidence for {num(v)} years from the date of disclosure.", v
    if ctype == "limitation_of_liability":
        if v == "unlimited":
            return h, "Nothing in this Agreement limits or excludes either party's liability for any claim.", "unlimited"
        if v == "2x_annual":
            return h, "Provider's aggregate liability shall not exceed two times the annual fees payable under this Agreement.", 24
        return h, f"Each party's aggregate liability shall not exceed the fees paid in the {num(v)} months preceding the claim.", v
    if ctype == "indemnification":
        t = {"mutual": "Each party shall defend and indemnify the other party against third-party claims arising from its breach of this Agreement.",
             "mutual_split": "Provider shall indemnify Customer against third-party claims arising from Provider's breach. "
                             "Customer shall likewise indemnify Provider against third-party claims arising from Customer's breach.",
             "one_sided_capped": "Provider shall defend and indemnify Customer against all third-party claims, subject to the limitation of liability.",
             "one_sided_uncapped": "Provider shall defend and indemnify Customer against all claims, without regard to any limitation of liability in this Agreement."}[v]
        return h, t, {"mutual_split": "mutual"}.get(v, v)
    if ctype == "governing_law":
        if v == "England and Wales":
            return h, "This Agreement is governed by the laws of England and Wales.", v
        return h, f"This Agreement is governed by the laws of the State of {v}, without regard to conflict-of-laws rules.", v
    if ctype == "payment_terms":
        return h, f"Customer shall pay all undisputed invoices within {num(v)} days of the invoice date.", v
    if ctype == "auto_renewal":
        if v == 0:
            return h, "This Agreement does not renew automatically. Any renewal requires a signed amendment.", 0
        return h, (f"This Agreement automatically renews for successive one-year terms unless either party gives written notice "
                   f"of non-renewal at least {num(v)} days before the end of the then-current term."), v
    if ctype == "non_solicitation":
        return h, f"For {num(v)} months after termination, neither party shall solicit for employment any employee of the other party.", v
    if ctype == "assignment":
        t = {"reasonable_consent": "Neither party may assign this Agreement without the other party's written consent, not to be unreasonably withheld.",
             "strict_consent": "Neither party may assign or transfer this Agreement, including by change of control, without the other party's prior written consent.",
             "one_sided_free": "Customer may assign this Agreement without consent. Provider may not assign this Agreement without Customer's prior written consent."}[v]
        return h, t, v


def playbook_call(ctype, value):
    """How a partner applies the written playbook to the true value."""
    chk = PLAYBOOK[ctype]["check"]
    if ctype in ("confidentiality_term", "limitation_of_liability", "payment_terms", "auto_renewal", "non_solicitation"):
        if value in chk.get("escalate_flags", []):
            return "escalate"
        return "OK" if value <= chk["ok_max"] else ("escalate" if value > chk["escalate_above"] else "negotiate")
    if ctype == "indemnification":
        return {"mutual": "OK", "one_sided_capped": "negotiate", "one_sided_uncapped": "escalate"}[value]
    if ctype == "governing_law":
        return "OK" if value in chk["ok_in"] else ("escalate" if value == "England and Wales" else "negotiate")
    if ctype == "assignment":
        return {"reasonable_consent": "OK", "strict_consent": "negotiate", "one_sided_free": "escalate"}[value]


POOLS = {
    "confidentiality_term": [2, 3, 3, 5, 5, 10, "perpetual"],
    "limitation_of_liability": [12, 12, 24, "unlimited", "2x_annual"],
    "indemnification": ["mutual", "mutual_split", "one_sided_capped", "one_sided_uncapped"],
    "governing_law": ["Delaware", "New York", "California", "Texas", "England and Wales"],
    "payment_terms": [30, 30, 45, 60, 90],
    "auto_renewal": [0, 30, 60, 120],
    "non_solicitation": [12, 12, 18, 36],
    "assignment": ["reasonable_consent", "reasonable_consent", "strict_consent", "one_sided_free"],
}
NDA = ["confidentiality_term", "non_solicitation", "governing_law", "assignment"]
MSA = ["limitation_of_liability", "indemnification", "payment_terms", "auto_renewal", "confidentiality_term",
       "governing_law", "assignment"]
PARTIES = ["Alder Robotics", "Brightwater Foods", "Corvid Analytics", "Delmar Freight", "Evergreen Clinics",
           "Fathom Media", "Granite Payroll", "Helio Solar", "Ironbark Insurance", "Juniper Schools"]
# Tricky variants placed so every one appears at least once.
FORCE = {("CT-05", "limitation_of_liability"): "2x_annual", ("CT-06", "indemnification"): "mutual_split",
         ("CT-08", "indemnification"): "mutual_split", ("CT-09", "governing_law"): "England and Wales",
         ("CT-03", "confidentiality_term"): 5, ("CT-07", "payment_terms"): 60}
# Partner judgment calls that depart from the written playbook (the reason associates disagree).
OVERRIDES = {("CT-03", "confidentiality_term"): ("OK", "Strategic client; partner accepted 5 years."),
             ("CT-07", "payment_terms"): ("escalate", "Client flagged cash-flow risk; partner wants to decide on 60 days.")}

contracts, key = [], {}
for i in range(10):
    cid = f"CT-{i + 1:02d}"
    kind = "NDA" if i < 4 else "MSA"
    clauses, k = [], {}
    for j, ctype in enumerate(NDA if kind == "NDA" else MSA, start=1):
        v = FORCE.get((cid, ctype), random.choice(POOLS[ctype]))
        heading, text, truth = clause(ctype, v)
        clid = f"{cid}-{j}"
        clauses.append({"clause_id": clid, "heading": f"{j}. {heading}", "text": text})
        decision, note = OVERRIDES.get((cid, ctype), (playbook_call(ctype, truth), ""))
        k[clid] = {"clause_type": ctype, "partner_decision": decision, "true_value": truth, "partner_note": note}
    if kind == "MSA":  # one clause the playbook does not cover, to test that the Skill leaves it alone
        clauses.append({"clause_id": f"{cid}-{len(clauses) + 1}", "heading": f"{len(clauses) + 1}. Notices",
                        "text": "Notices must be in writing and sent to the addresses on the signature page."})
    contracts.append({"contract_id": cid, "type": kind, "counterparty": PARTIES[i],
                      "title": f"{'Mutual Non-Disclosure Agreement' if kind == 'NDA' else 'Master Services Agreement'} - {PARTIES[i]}",
                      "clauses": clauses})
    key[cid] = k

# Associates' past reviews of the same contracts: each applies the playbook with their own habits.
HABITS = {"Associate A": {"soften": 0.30, "harden": 0.05}, "Associate B": {"soften": 0.05, "harden": 0.30},
          "Associate C": {"soften": 0.15, "harden": 0.15}}
ORDER = ["OK", "negotiate", "escalate"]
history = {}
for c in contracts:
    calls = {}
    for a, h in HABITS.items():
        row = {}
        for clid, kk in key[c["contract_id"]].items():
            idx = ORDER.index(kk["partner_decision"])
            r = random.random()
            if r < h["soften"] and idx > 0:
                idx -= 1
            elif r > 1 - h["harden"] and idx < 2:
                idx += 1
            row[clid] = ORDER[idx]
        calls[a] = row
    history[c["contract_id"]] = {"handled_by": list(HABITS)[contracts.index(c) % 3],
                                 "review_minutes": random.randint(70, 110), "associate_calls": calls}

(DATA / "contracts.json").write_text(json.dumps(contracts, indent=2))
(DATA / "partner_answer_key.json").write_text(json.dumps(key, indent=2))
(DATA / "associate_history.json").write_text(json.dumps(history, indent=2))
(DATA / "baseline.json").write_text(json.dumps({"skill_review_minutes_base": 10, "minutes_per_flagged_clause": 3}, indent=2))
n = sum(len(v) for v in key.values())
print(f"Wrote {len(contracts)} contracts ({n} playbook clauses), partner answer key and associate history -> {DATA}")
