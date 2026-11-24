"""Build 06 - Month-end bank reconciliation (Accounting). Pattern: Claude Code + one AI step.

Code does the exact math. Claude only sees the lines the rules could not match.
"""
import html, json, re, sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, batch_structured  # noqa: E402

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "outputs"
PERIOD = "2026-11"
DATE_WINDOW_DAYS = 5      # near-match rule: same amount, dates up to 5 days apart
AMOUNT_TOLERANCE = 1.00   # near-match rule: same payee, amounts within $1 (card FX cents)
NAME_THRESHOLD = 0.45     # fuzzy payee similarity needed for a near match
NOISE = {"ach", "pmt", "inc", "com", "web", "bill", "cr", "credit", "deposit", "wire", "in", "us", "sfdc"}


def norm(s: str) -> str:
    words = re.findall(r"[a-z]+", str(s).lower().replace("&", " and "))
    return " ".join(w for w in words if w not in NOISE and len(w) > 1)


def name_score(bank_desc: str, payee: str) -> float:
    """Fuzzy payee match: best of difflib ratio and share of the payee's words found in the bank text."""
    b, p = norm(bank_desc), norm(payee)
    ratio = SequenceMatcher(None, b, p).ratio()
    words = [w for w in p.split() if len(w) >= 3]
    share = sum(w in b for w in words) / len(words) if words else 0
    return round(max(ratio, share), 2)


# ---------- Step 1: exact match ----------
def exact_match(bank: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    b = bank.assign(k=bank.groupby(["date", "amount"]).cumcount())
    g = ledger.assign(k=ledger.groupby(["date", "amount"]).cumcount())
    m = b.merge(g, on=["date", "amount", "k"], suffixes=("_bank", "_gl"))
    return m.assign(rule="exact: same date and amount", amount_diff=0.0)[
        ["line_id_bank", "line_id_gl", "date", "amount", "description", "payee", "rule", "amount_diff"]]


# ---------- Step 2: near-match rules ----------
def near_match(bank: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    rows, used_gl = [], set()
    cands = bank.merge(ledger, how="cross", suffixes=("_bank", "_gl"))
    cands["days"] = (pd.to_datetime(cands.date_bank) - pd.to_datetime(cands.date_gl)).dt.days.abs()
    cands["diff"] = (cands.amount_bank - cands.amount_gl).round(2)
    cands = cands[(cands.days <= DATE_WINDOW_DAYS) & (cands["diff"].abs() <= AMOUNT_TOLERANCE)].copy()
    cands["name"] = [name_score(d, p) for d, p in zip(cands.description, cands.payee)]
    cands = cands[cands.name >= NAME_THRESHOLD].sort_values(["diff", "days", "name"],
                                                             key=lambda s: s.abs() if s.name != "name" else -s)
    for _, r in cands.iterrows():
        if r.line_id_bank in {x["line_id_bank"] for x in rows} or r.line_id_gl in used_gl:
            continue
        rule = (f"near: amount off ${abs(r['diff']):.2f}, payee {r['name']:.0%}" if r["diff"]
                else f"near: date off {r.days}d, payee {r['name']:.0%}")
        rows.append({"line_id_bank": r.line_id_bank, "line_id_gl": r.line_id_gl, "date": r.date_bank,
                     "amount": r.amount_bank, "description": r.description, "payee": r.payee,
                     "rule": rule, "amount_diff": r["diff"]})
        used_gl.add(r.line_id_gl)
    return pd.DataFrame(rows)


# ---------- Step 3: Claude explains what the rules could not match ----------
class SuggestedEntry(BaseModel):
    debit: str
    credit: str
    amount: float
    memo: str

class ExceptionNote(BaseModel):
    line_id: str
    side: Literal["bank", "ledger"]
    exception_type: Literal["bank_fee", "duplicate_payment", "transposed_amount", "timing_difference",
                            "unknown_vendor", "other"]
    related_line_id: Optional[str] = Field(description="the line on either side this one relates to, if any")
    explanation: str = Field(description="one or two plain sentences for the controller")
    suggested_entry: Optional[SuggestedEntry] = Field(description="journal entry to propose, or null if none needed")
    action: str
    confidence: Literal["high", "medium", "low"]

SYSTEM = ("You are a staff accountant helping close the books. Each item is ONE bank or ledger line that exact "
          "and near-match rules could not match, plus nearby candidate lines and the vendor master. Explain the "
          "most likely cause, link a related line if there is one, and propose a journal entry only when the books "
          "need one (cash account 1010). Never invent amounts; use the numbers given. If unsure, say so and set "
          "confidence low.")


def transposed(a: float, b: float) -> bool:
    da, db = f"{abs(a):.2f}".replace(".", ""), f"{abs(b):.2f}".replace(".", "")
    diff = round(abs(abs(a) - abs(b)) * 100)
    return a * b > 0 and diff > 0 and diff % 9 == 0 and sorted(da) == sorted(db)


def offline_explain(cid: str, ctx: dict) -> ExceptionNote:
    """Rule-based stand-in for Claude, working from the same context the prompt contains."""
    line, side, amt = ctx["line"], ctx["side"], ctx["line"]["amount"]
    who = line.get("description") or line.get("payee")
    for c in ctx["unmatched_other_side"]:
        if transposed(amt, c["amount"]) and (side == "ledger" or name_score(who, c["payee"]) >= NAME_THRESHOLD):
            bank_amt, gl_amt = (amt, c["amount"]) if side == "bank" else (c["amount"], amt)
            diff = round(abs(bank_amt - gl_amt), 2)
            gl_line = c if side == "bank" else line
            return ExceptionNote(
                line_id=cid, side=side, exception_type="transposed_amount", related_line_id=c["line_id"],
                explanation=(f"Bank shows {abs(bank_amt):,.2f} and the ledger {abs(gl_amt):,.2f}: the same digits in a "
                             f"different order (difference {diff:,.2f} divides by 9), so the ledger entry was likely mistyped."),
                suggested_entry=SuggestedEntry(debit=gl_line.get("account", "6310 Telecom"), credit="1010 Cash",
                                               amount=diff, memo=f"Correct keying error on {gl_line['line_id']}"),
                action="Check the invoice amount, then post the correction.", confidence="high")
    if side == "bank":
        if re.search(r"\bFEE\b|SERVICE CHARGE", who.upper()):
            return ExceptionNote(line_id=cid, side=side, exception_type="bank_fee", related_line_id=None,
                                 explanation=f"'{who}' is a bank charge with no ledger entry; it was never booked.",
                                 suggested_entry=SuggestedEntry(debit="6450 Bank fees", credit="1010 Cash",
                                                                amount=abs(amt), memo=f"{who} {line['date']}"),
                                 action="Post the fee.", confidence="high")
        twin = next((m for m in ctx["matched_same_amount"] if name_score(who, m["description"]) >= 0.8), None)
        if twin:
            return ExceptionNote(line_id=cid, side=side, exception_type="duplicate_payment", related_line_id=twin["line_id_bank"],
                                 explanation=(f"Same payee and amount ({abs(amt):,.2f}) already cleared on {twin['date']} "
                                              f"and matched to {twin['line_id_gl']}; this second debit looks like a duplicate payment."),
                                 suggested_entry=SuggestedEntry(debit="1250 Vendor refunds receivable", credit="1010 Cash",
                                                                amount=abs(amt), memo=f"Duplicate payment to {twin['payee']}"),
                                 action=f"Ask {twin['payee']} for a refund or credit.", confidence="high")
        best = max((name_score(who, v) for v in ctx["vendor_master"]), default=0)
        if best < NAME_THRESHOLD:
            return ExceptionNote(line_id=cid, side=side, exception_type="unknown_vendor", related_line_id=None,
                                 explanation=f"'{who}' does not match any vendor in the master (best match {best:.0%}) and has no ledger entry.",
                                 suggested_entry=SuggestedEntry(debit="1999 Suspense", credit="1010 Cash",
                                                                amount=abs(amt), memo=f"Unidentified: {who}"),
                                 action="Ask card holders for the receipt; reclass from suspense once known.", confidence="medium")
    else:
        day = int(line["date"][8:])
        if day >= ctx["period_last_day"] - 2:
            kind = "an outstanding check" if amt < 0 else "a deposit in transit"
            return ExceptionNote(line_id=cid, side=side, exception_type="timing_difference", related_line_id=None,
                                 explanation=f"Booked on {line['date']}, at month end, and not yet through the bank: {kind}.",
                                 suggested_entry=None, action="No entry. Confirm it clears in the first days of next month.",
                                 confidence="high")
    return ExceptionNote(line_id=cid, side=side, exception_type="other", related_line_id=None,
                         explanation="No rule or pattern explains this line.", suggested_entry=None,
                         action="Investigate manually.", confidence="low")


def main():
    tr = Trace("06", "Month-end reconciliation", OUT)
    tr.arch([
        {"label": "Bank export (CSV)", "kind": "data", "note": "statement lines"},
        {"label": "QuickBooks / NetSuite", "kind": "data", "note": "GL cash ledger export"},
        {"label": "pandas matcher", "kind": "code", "note": "exact + near-match rules"},
        {"label": "Claude (unmatched only)", "kind": "ai", "note": "explain + suggest entries"},
        {"label": "Exceptions report", "kind": "system", "note": "Sheets-ready CSV + HTML"},
        {"label": "Controller approval", "kind": "human", "note": "approves entries"},
        {"label": "Nightly schedule", "kind": "system", "note": "cron, 02:30"},
    ])
    tr.story(
        situation="A 60-person company closes its books in about 6 working days. Two of those days go to ticking bank lines against the ledger in spreadsheets, and odd items are found late.",
        constraints="The numbers must be exact and auditable, so matching is plain pandas code, never a model. Bank and ledger data stay inside the finance tenant. The controller approves every journal entry; nothing posts automatically.",
        replay="Reuse: 'rules do the bulk, the model explains the leftovers' fits any matching job (invoices to POs, payouts to orders, claims to remits). Next time: feed the controller's decisions back as new rules, so the leftover pile shrinks every month.",
    )

    bank = pd.read_csv(DATA / f"bank_export_{PERIOD}.csv")
    ledger = pd.read_csv(DATA / f"ledger_export_{PERIOD}.csv")
    tr.step("Load the bank and ledger exports", kind="io",
            what=f"{len(bank)} bank lines and {len(ledger)} ledger lines for {PERIOD} (synthetic exports).",
            code=(f'bank = pd.read_csv("data/bank_export_{PERIOD}.csv")\n'
                  f'ledger = pd.read_csv("data/ledger_export_{PERIOD}.csv")'),
            output="BANK\n" + bank.head(4).to_string(index=False) + "\n\nLEDGER\n"
            + ledger.head(4).to_string(index=False)
            + f"\n\nbank total {bank.amount.sum():,.2f} | ledger total {ledger.amount.sum():,.2f} | "
              f"difference {bank.amount.sum() - ledger.amount.sum():,.2f}")

    exact = exact_match(bank, ledger)
    tr.step("Match bank to ledger lines exactly (pandas)", kind="code",
            what=f"A pandas script, written with Claude Code, pairs lines with the same date and amount one-to-one: {len(exact)} of {len(bank)} bank lines matched.",
            code=('b = bank.assign(k=bank.groupby(["date", "amount"]).cumcount())\n'
                  'g = ledger.assign(k=ledger.groupby(["date", "amount"]).cumcount())\n'
                  'exact = b.merge(g, on=["date", "amount", "k"], suffixes=("_bank", "_gl"))'),
            output=exact.head(6)[["line_id_bank", "line_id_gl", "date", "amount", "description", "payee"]].to_string(index=False)
            + f"\n... {len(exact)} exact matches")

    rb = bank[~bank.line_id.isin(exact.line_id_bank)]
    rg = ledger[~ledger.line_id.isin(exact.line_id_gl)]
    near = near_match(rb, rg)
    matched = pd.concat([exact, near], ignore_index=True)
    ub = bank[~bank.line_id.isin(matched.line_id_bank)]
    ug = ledger[~ledger.line_id.isin(matched.line_id_gl)]
    tr.step("Add rules for near matches: dates, amounts, payee names", kind="code",
            what=f"Rules catch ACH lines that clear a few days late and card charges a few cents off, using difflib to match payee names: {len(near)} more matched, {len(ub)} bank + {len(ug)} ledger lines left over.",
            code=(f'cands = cands[(cands.days <= {DATE_WINDOW_DAYS}) & (cands["diff"].abs() <= {AMOUNT_TOLERANCE})]\n'
                  'cands["name"] = [name_score(d, p) for d, p in zip(cands.description, cands.payee)]\n'
                  f'cands = cands[cands.name >= {NAME_THRESHOLD}]   # SequenceMatcher ratio / word overlap'),
            output=near.head(8)[["line_id_bank", "line_id_gl", "description", "payee", "rule"]].to_string(index=False)
            + f"\n... {len(near)} near matches\n\nleft for Claude: " + ", ".join(list(ub.line_id) + list(ug.line_id)))

    # Step 3: only the leftovers go to Claude, each with its candidate lines as context
    last_day = pd.Period(PERIOD).days_in_month
    vendor_master = json.loads((DATA / "vendor_master.json").read_text())
    contexts = {}
    for side, rows, other in [("bank", ub, ug), ("ledger", ug, ub)]:
        for r in rows.to_dict("records"):
            near_other = [o for o in other.to_dict("records")
                          if abs((pd.Timestamp(o["date"]) - pd.Timestamp(r["date"])).days) <= 7]
            same_amt = matched[matched.amount == r["amount"]].to_dict("records") if side == "bank" else []
            contexts[r["line_id"]] = {"side": side, "line": r, "unmatched_other_side": near_other,
                                      "matched_same_amount": same_amt, "vendor_master": vendor_master,
                                      "period_last_day": last_day}
    items = {cid: (f"Period {PERIOD}. Unmatched {c['side']} line:\n{json.dumps(c['line'])}\n"
                   f"Unmatched lines on the other side within 7 days:\n{json.dumps(c['unmatched_other_side'])}\n"
                   f"Already-matched lines with the same amount:\n{json.dumps(c['matched_same_amount'], default=str)}\n"
                   f"Vendor master: {', '.join(vendor_master)}")
             for cid, c in contexts.items()}
    notes = batch_structured(system=SYSTEM, items=items, schema=ExceptionNote,
                             offline=lambda cid, txt: offline_explain(cid, contexts[cid]))
    share = len(items) / (len(bank) + len(ledger))
    sample = notes[next(k for k, n in notes.items() if n.exception_type == "duplicate_payment")]
    tr.step("Send only unmatched lines to Claude to explain", kind="ai",
            what=f"Claude saw {len(items)} of {len(bank) + len(ledger)} lines ({share:.1%}), each with its nearby candidates, and returned a structured explanation and suggested entry.",
            code=('notes = batch_structured(system=SYSTEM, items=items,  # unmatched lines only\n'
                  '                         schema=ExceptionNote,\n'
                  '                         offline=lambda cid, txt: offline_explain(cid, contexts[cid]))'),
            output="\n".join(f"{k} {n.side:6} {n.exception_type:18} {n.confidence:6} {n.explanation[:80]}"
                             for k, n in notes.items()) + "\n\nexample:\n" + sample.model_dump_json(indent=1))

    # Step 4: exceptions report. Pair lines that point at each other (e.g. both sides of a transposition)
    exceptions, seen = [], set()
    for k, n in notes.items():
        if k in seen:
            continue
        pair = n.related_line_id if n.related_line_id in notes else None
        seen |= {k, pair} - {None}
        line = contexts[k]["line"]
        bank_id = k if n.side == "bank" else pair
        gl_id = k if n.side == "ledger" else pair
        e = n.suggested_entry
        exceptions.append({
            "exception_id": f"EX-{len(exceptions) + 1:02d}", "type": n.exception_type,
            "bank_line": bank_id or "", "ledger_line": gl_id or "", "related_line": n.related_line_id or "",
            "date": line["date"], "description": line.get("description") or line.get("payee"),
            "amount": line["amount"], "explanation": n.explanation,
            "suggested_debit": e.debit if e else "", "suggested_credit": e.credit if e else "",
            "suggested_amount": e.amount if e else "", "action": n.action, "confidence": n.confidence,
            "controller_decision": "", "approved_by": ""})
    rep = pd.DataFrame(exceptions)
    rep.to_csv(OUT / "exceptions_report.csv", index=False)
    matched.to_csv(OUT / "matched_lines.csv", index=False)

    # Proof: every cent of the bank-ledger difference is explained by matches + exceptions
    diff = round(bank.amount.sum() - ledger.amount.sum(), 2)
    explained = round(matched.amount_diff.sum() + ub.amount.sum() - ug.amount.sum(), 2)
    rows_html = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[c]))}</td>" for c in
                        ["exception_id", "type", "bank_line", "ledger_line", "amount", "explanation",
                         "suggested_debit", "suggested_amount", "action"]) + "<td><input type=checkbox></td></tr>"
                        for r in exceptions)
    (OUT / "exceptions_report.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>Exceptions {PERIOD}</title>"
        "<style>body{font:14px system-ui;margin:24px}td,th{border:1px solid #ccc;padding:4px 8px;vertical-align:top}"
        "table{border-collapse:collapse}</style>"
        f"<h1>Bank reconciliation exceptions, {PERIOD}</h1><p>{len(matched)} lines matched by code. "
        f"Bank minus ledger: {diff:,.2f}; explained: {explained:,.2f}; unexplained: {diff - explained:,.2f}.</p>"
        "<table><tr><th>ID</th><th>Type</th><th>Bank</th><th>Ledger</th><th>Amount</th><th>Explanation</th>"
        f"<th>Debit</th><th>Entry</th><th>Action</th><th>Approve</th></tr>{rows_html}</table>")
    tr.step("Write the exceptions report for the controller", kind="human",
            what=f"{len(rep)} exceptions go to a Sheets-ready CSV and an HTML page with an approve box per line; the controller approves {int(rep.suggested_debit.astype(bool).sum())} proposed entries.",
            code=('rep.to_csv("outputs/exceptions_report.csv", index=False)   # import into Google Sheets\n'
                  'explained = matched.amount_diff.sum() + ub.amount.sum() - ug.amount.sum()\n'
                  'assert round(diff - explained, 2) == 0   # every cent accounted for'),
            output=rep[["exception_id", "type", "bank_line", "ledger_line", "amount", "suggested_debit", "suggested_amount"]].to_string(index=False)
            + f"\n\nbank - ledger = {diff:,.2f} | explained by matches + exceptions = {explained:,.2f} | unexplained = {diff - explained:,.2f}")
    assert round(diff - explained, 2) == 0

    # Step 5: schedule it nightly
    sched = OUT / "schedule"
    sched.mkdir(exist_ok=True)
    cron = ("# Nightly bank reconciliation, 02:30 server time (after the bank's SFTP drop at 01:00)\n"
            "30 2 * * * cd /opt/finance/recon && ./fetch_exports.sh && python3 pipeline.py >> logs/recon.log 2>&1\n")
    (sched / "crontab.txt").write_text(cron)
    cfg = {"schedule": "30 2 * * *", "inputs": {"bank": "sftp://bank/exports/{period}.csv",
                                                "ledger": "netsuite saved search 'GL Cash 1010' -> CSV"},
           "outputs": {"report": "Google Sheets 'Close {period}' tab Exceptions", "html": "outputs/exceptions_report.html"},
           "rules": {"date_window_days": DATE_WINDOW_DAYS, "amount_tolerance": AMOUNT_TOLERANCE,
                     "name_threshold": NAME_THRESHOLD},
           "alert_if": "unexplained difference != 0 or exceptions > 20"}
    (sched / "recon_job.json").write_text(json.dumps(cfg, indent=2))
    tr.step("Schedule it nightly", kind="code",
            what="A cron job reruns the match every night, so exceptions surface daily instead of piling up for month end.",
            code=cron.strip().splitlines()[1],
            output=cron + "\n" + json.dumps(cfg, indent=1))

    # Evaluation against the planted exceptions
    key = json.loads((DATA / "planted_exceptions.json").read_text())
    found = []
    for k in key:
        hit = next((e for e in exceptions if e["type"] == k["type"]
                    and set(k["lines"]) & {e["bank_line"], e["ledger_line"]}), None)
        found.append({"type": k["type"], "lines": k["lines"], "found_as": hit["exception_id"] if hit else "MISSED"})
    n_found = sum(f["found_as"] != "MISSED" for f in found)
    keyed = {l for k in key for l in k["lines"]}
    false_pos = [e["exception_id"] for e in exceptions if not ({e["bank_line"], e["ledger_line"]} & keyed)]

    truth = json.loads((DATA / "true_pairs.json").read_text())
    right = sum(truth.get(g) == b for b, g in zip(matched.line_id_bank, matched.line_id_gl))
    lines_total = len(bank) + len(ledger)
    manual_h = (lines_total * 2.5 + len(key) * 20) / 60          # 2.5 min per line ticked, 20 min per exception chased
    after_h = (len(exceptions) * 5 + 30) / 60                     # 5 min reviewing each explanation + 30 min sign-off
    tr.step("Check against the planted exceptions", kind="check",
            what=f"The answer key lists {len(key)} planted problems; the run found {n_found} with {len(false_pos)} false alarms.",
            code=('hit = next(e for e in exceptions if e["type"] == k["type"]\n'
                  '           and set(k["lines"]) & {e["bank_line"], e["ledger_line"]})'),
            output="\n".join(f"{f['type']:18} {', '.join(f['lines']):18} -> {f['found_as']}" for f in found)
            + f"\n\nfound {n_found}/{len(key)} | false alarms {len(false_pos)}"
            + f"\ncode matches that pair the right lines: {right}/{len(matched)}"
            + f"\nrecon hours this account: {manual_h:.1f} h by hand -> {after_h:.1f} h reviewing exceptions"
            + "\n(assumes 2.5 min per line and 20 min per exception by hand; 5 min per exception review)")

    tr.metrics(lines_matched_by_code=f"{len(matched)}/{len(bank)} bank lines ({len(exact)} exact + {len(near)} near)",
               match_precision=f"{right}/{len(matched)} pairs correct",
               lines_sent_to_claude=f"{len(items)} of {lines_total} ({share:.1%})",
               exceptions_found=f"{n_found}/{len(key)} planted, {len(false_pos)} false alarms",
               unexplained_difference=f"{diff - explained:,.2f}",
               recon_hours_per_month=f"{manual_h:.1f} -> {after_h:.1f}",
               hours_saved_per_month=round(manual_h - after_h, 1),
               days_to_close_recon_step=f"{manual_h / 6:.1f} -> {max(after_h / 6, 0.1):.1f} working days (6 h/day)")
    tr.save()


if __name__ == "__main__":
    main()
