"""Build 03 - Contract review Skill (Legal). Pattern: Skill."""
import json, re, sys
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, batch_structured  # noqa: E402

HERE = Path(__file__).parent
SKILL = HERE / "skill" / "contract-review"
sys.dont_write_bytecode = True  # keep the Skill folder clean
sys.path.insert(0, str(SKILL / "scripts"))
from redline import write_memo, write_redline  # noqa: E402

DATA, OUT = HERE / "data", HERE / "outputs"
PB = json.loads((SKILL / "playbook.json").read_text())
RULES = PB["rules"]
LIBRARY = json.loads((SKILL / "clause_library.json").read_text())
US_STATES = {"Delaware", "New York", "California", "Texas", "Massachusetts", "Illinois", "Washington", "Florida", "Georgia"}


class ClauseCall(BaseModel):
    clause_id: str
    clause_type: str = Field(description="playbook rule key")
    extracted_value: str = Field(description="the deciding value, e.g. '5 years', 'mutual', 'Texas'")
    decision: Literal["OK", "negotiate", "escalate"]
    reason: str = Field(description="one sentence naming the playbook rule")

class ContractReview(BaseModel):
    contract_id: str
    clauses: list[ClauseCall]
    not_covered: list[str] = Field(description="clause ids the playbook does not cover")


def skill_system_prompt() -> str:
    body = (SKILL / "SKILL.md").read_text().split("---", 2)[2]
    return (body + "\n\n## playbook.json\n" + json.dumps(PB, indent=1) +
            "\n\n## clause_library.json\n" + json.dumps(LIBRARY, indent=1))


def contract_prompt(c: dict) -> str:
    return (f"{c['contract_id']} | {c['title']}\n\n" +
            "\n\n".join(f"[{cl['clause_id']}] {cl['heading']}\n{cl['text']}" for cl in c["clauses"]))


# ---------- offline stand-in: reads each clause and applies playbook.json ----------
def extract(ctype: str, text: str):
    t = text.lower()
    m = re.search(r"\((\d+)\)\s*(years?|months?|days?)", t)
    n, unit = (int(m[1]), m[2]) if m else (None, None)
    if ctype == "confidentiality_term":
        if re.search(r"perpetu|indefinite", t):
            return "perpetual", "perpetual"
        return (n / 12 if unit and unit.startswith("month") else n), f"{n} {unit}" if n else None
    if ctype == "limitation_of_liability":
        if re.search(r"nothing in this agreement limits|unlimited|uncapped", t):
            return "unlimited", "unlimited"
        return (n * 12 if unit and unit.startswith("year") else n), f"{n} {unit} of fees" if n else None
    if ctype in ("payment_terms", "auto_renewal", "non_solicitation"):
        if ctype == "auto_renewal" and "does not renew" in t:
            return 0, "no auto-renewal"
        return n, f"{n} {unit}" if n else None
    if ctype == "indemnification":
        mutual = bool(re.search(r"each party|either party|mutual", t))
        uncapped = bool(re.search(r"without regard to any limitation|notwithstanding any limitation", t))
        v = "mutual" if mutual else ("one_sided_uncapped" if uncapped else "one_sided_capped")
        return v, v.replace("_", " ")
    if ctype == "governing_law":
        m = re.search(r"laws of the (?:state|commonwealth) of ([a-z ]+?)(?:,|\.|$)", t)
        if m:
            return m[1].title(), m[1].title()
        m = re.search(r"laws of ([a-z ]+?)(?:,|\.|$)", t)
        return ("non_us", m[1].title().replace(" And ", " and ")) if m else (None, None)
    if ctype == "assignment":
        if "not to be unreasonably withheld" in t or "not be unreasonably withheld" in t:
            return "reasonable_consent", "consent, not unreasonably withheld"
        if re.search(r"customer may assign[^.]*without consent", t) and "provider may not" in t:
            return "one_sided_free", "counterparty may assign freely; our client may not"
        return "strict_consent", "consent required, incl. change of control"
    return None, None


def decide(ctype: str, value):
    rule, chk = RULES[ctype], RULES[ctype]["check"]
    if value is None:
        return "escalate", f"Could not read the {chk['param']} with confidence; a partner should review."
    if "ok_max" in chk:
        if value in chk.get("escalate_flags", []):
            return "escalate", f"Hits walk-away: {rule['walk_away']}"
        unit, u1 = chk["param"], chk["param"][:-1]
        if ctype == "auto_renewal" and value == 0:
            return "OK", "No auto-renewal, matching the position."
        if value <= chk["ok_max"]:
            return "OK", f"{value:g} {unit} is within the {chk['ok_max']}-{u1} position."
        if value > chk["escalate_above"]:
            return "escalate", f"{value:g} {unit} is past the {chk['escalate_above']}-{u1} walk-away."
        return "negotiate", f"{value:g} {unit} exceeds the {chk['ok_max']}-{u1} position but not the {chk['escalate_above']}-{u1} walk-away; propose the fallback."
    if ctype == "governing_law":
        if value in chk["ok_in"]:
            return "OK", f"{value} law matches the position."
        if value == "non_us" or value not in US_STATES:
            return "escalate", f"Hits walk-away: {rule['walk_away']}"
        return "negotiate", f"{value} law is a US state but not Delaware or New York; propose the fallback."
    if ctype == "indemnification":
        return {"mutual": ("OK", "Indemnities are mutual, matching the position."),
                "one_sided_capped": ("negotiate", "Indemnity runs only from our client; propose mutual indemnities."),
                "one_sided_uncapped": ("escalate", f"Hits walk-away: {rule['walk_away']}")}[value]
    if ctype == "assignment":
        return {"reasonable_consent": ("OK", "Consent not unreasonably withheld, matching the position."),
                "strict_consent": ("negotiate", "Consent required even on change of control; propose the M&A carve-out."),
                "one_sided_free": ("escalate", f"Hits walk-away: {rule['walk_away']}")}[value]


def offline_review(cid: str, text: str) -> ContractReview:
    titles = {r["title"].lower(): k for k, r in RULES.items()}
    calls, skipped = [], []
    for m in re.finditer(r"\[(CT-\d+-\d+)\] \d+\. (.+)\n(.+)", text):
        clid, heading, body = m[1], m[2].strip(), m[3]
        ctype = titles.get(heading.lower())
        if not ctype:
            skipped.append(clid)
            continue
        value, shown = extract(ctype, body)
        decision, reason = decide(ctype, value)
        calls.append(ClauseCall(clause_id=clid, clause_type=ctype, extracted_value=shown or "unreadable",
                                decision=decision, reason=reason))
    return ContractReview(contract_id=cid, clauses=calls, not_covered=skipped)


def main():
    tr = Trace("03", "Contract review Skill", OUT)
    tr.arch([
        {"label": "Firm playbook", "kind": "data", "note": "position / fallback / walk-away"},
        {"label": "contract-review Skill", "kind": "system", "note": "SKILL.md + rules + clause library + scripts"},
        {"label": "Claude", "kind": "ai", "note": "OK / negotiate / escalate per clause"},
        {"label": "redline.py", "kind": "code", "note": ".docx redline + issues memo"},
        {"label": "Project per client", "kind": "system", "note": "client context and history"},
        {"label": "Partner review", "kind": "human", "note": "answer key + escalations"},
    ])
    tr.story(
        situation="A commercial team reviews dozens of NDAs and MSAs a month. Associates redline the same issues by hand, and each applies the playbook a little differently, so partners keep re-editing.",
        constraints="Client documents are confidential and stay inside the firm's Claude workspace (a Project per client). Fallback wording must come from the approved clause library, never be drafted on the fly. Walk-away terms always go to a partner.",
        replay="Reuse: playbook-as-Skill fits any team that applies written rules to documents (procurement terms, lease abstracts, policy checks). Next time: have partners label 20 contracts before writing the rules, and track why partners override the playbook so the rules improve.",
        problem_cost="About 90 minutes of associate time per contract, plus partner time re-editing inconsistent redlines.",
    )

    # Step 1: playbook -> rules
    table = "\n".join(f"{r['title']}\n  position:  {r['position']}\n  fallback:  {r['fallback']}\n  walk-away: {r['walk_away']}"
                      for r in list(RULES.values())[:4]) + f"\n... and {len(RULES) - 4} more rules in playbook.json"
    tr.step("Turn the playbook into rules: position, fallback, walk-away", kind="code",
            what=f"The firm's written playbook became {len(RULES)} rules, each with a position, a fallback, a walk-away and a machine-readable check.",
            code=('"confidentiality_term": {\n'
                  '  "position": "No more than 3 years after disclosure.",\n'
                  '  "fallback": "3 years, trade secrets while they remain trade secrets.",\n'
                  '  "walk_away": "Perpetual, or longer than 7 years.",\n'
                  '  "check": {"param": "years", "ok_max": 3, "escalate_above": 7}}'),
            output=table)

    # Step 2: package as a Skill
    front = (SKILL / "SKILL.md").read_text().split("---")[1]
    meta = dict(re.findall(r"^(\w+): (.+)$", front, re.M))
    files = sorted(str(p.relative_to(SKILL.parent)) for p in SKILL.rglob("*") if p.is_file() and "__pycache__" not in str(p))
    missing_fallbacks = [k for k in RULES if k not in LIBRARY]
    tr.step("Package rules, clause library and scripts as one Skill", kind="code",
            what=f"One folder holds the instructions, rules, approved fallback wording and the redline script; frontmatter has name and description, and {len(RULES) - len(missing_fallbacks)}/{len(RULES)} rules have library wording.",
            code=("skill/contract-review/\n  SKILL.md            # name + description frontmatter, review steps\n"
                  "  playbook.json       # rules\n  clause_library.json # approved fallbacks\n"
                  "  scripts/redline.py  # .docx redline + memo"),
            output={"files": files, "frontmatter": {"name": meta.get("name"), "description": meta.get("description", "")[:120] + "..."},
                    "rules_without_fallback": missing_fallbacks})

    # Step 3: Claude reviews every contract
    contracts = json.loads((DATA / "contracts.json").read_text())
    by_id = {c["contract_id"]: c for c in contracts}
    items = {c["contract_id"]: contract_prompt(c) for c in contracts}
    system = skill_system_prompt()
    reviews = batch_structured(system=system, items=items, schema=ContractReview, offline=offline_review)
    counts = {"OK": 0, "negotiate": 0, "escalate": 0}
    for r in reviews.values():
        for c in r.clauses:
            counts[c.decision] += 1
    show = reviews["CT-05"]
    tr.step("Mark each clause OK / negotiate / escalate with a reason", kind="ai",
            what=f"Claude, loaded with the Skill, reviewed {len(reviews)} contracts ({sum(counts.values())} clauses): {counts['OK']} OK, {counts['negotiate']} negotiate, {counts['escalate']} escalate.",
            code=("system = SKILL.md + playbook.json + clause_library.json\n"
                  "reviews = batch_structured(system=system, items=contracts,\n"
                  "                           schema=ContractReview)\n"
                  "# ClauseCall: clause_id, clause_type, extracted_value, decision, reason"),
            output="CT-05 (MSA, Evergreen Clinics):\n" + "\n".join(
                f"  {c.clause_id}  {c.decision:<9} {c.extracted_value:<22} {c.reason}" for c in show.clauses) +
                f"\n  not covered by playbook: {show.not_covered}")

    # Step 4: redlined .docx + memo
    (OUT / "redlines").mkdir(parents=True, exist_ok=True)
    (OUT / "memos").mkdir(parents=True, exist_ok=True)
    totals = {"OK": 0, "negotiate": 0, "escalate": 0}
    memo05 = ""
    for cid, r in reviews.items():
        rv = r.model_dump()
        cts = write_redline(by_id[cid], rv, LIBRARY, OUT / "redlines" / f"{cid}_redline.docx")
        memo = write_memo(by_id[cid], rv, RULES, LIBRARY, OUT / "memos" / f"{cid}_memo.md")
        for k in totals:
            totals[k] += cts[k]
        if cid == "CT-05":
            memo05 = memo
    from docx import Document
    d = Document(OUT / "redlines" / "CT-05_redline.docx")
    struck = sum(1 for p in d.paragraphs for run in p.runs if run.font.strike)
    tr.step("Output a redlined .docx and a one-page issues memo", kind="io",
            what=f"Wrote {len(reviews)} redlines and {len(reviews)} memos; CT-05's redline has {struck} struck clause(s) with library fallbacks inserted and a Word comment on every flagged clause.",
            code=("old = p.add_run(clause_text); old.font.strike = True\n"
                  "new = p.add_run(LIBRARY[clause_type]); new.font.underline = True\n"
                  "doc.add_comment([old, new], text=f\"Negotiate: {reason}\")\n"
                  "write_memo(contract, review, RULES, LIBRARY, memo_path)"),
            output=memo05)

    # Step 5: test against what partners changed
    key = json.loads((DATA / "partner_answer_key.json").read_text())
    pairs, misses = [], []
    for cid, r in reviews.items():
        for c in r.clauses:
            k = key[cid][c.clause_id]
            pairs.append((c.decision, k["partner_decision"]))
            if c.decision != k["partner_decision"]:
                misses.append(f"{c.clause_id} {c.clause_type}: skill {c.decision}, partner {k['partner_decision']}"
                              + (f" ({k['partner_note']})" if k["partner_note"] else f" (text: {c.extracted_value})"))
    agree = sum(a == b for a, b in pairs) / len(pairs)
    confusion = {p: {s: sum(1 for a, b in pairs if a == s and b == p) for s in ("OK", "negotiate", "escalate")}
                 for p in ("OK", "negotiate", "escalate")}
    walkaways = [(a, b) for a, b in pairs if b == "escalate"]
    esc_recall = sum(a == "escalate" for a, b in walkaways) / len(walkaways)
    tr.step("Test on 10 past contracts against what partners changed", kind="check",
            what=f"Compared {len(pairs)} clause calls with the partner's final decisions: {agree:.0%} agreement, {esc_recall:.0%} of partner escalations caught.",
            code=("for clause in review.clauses:\n"
                  "    pairs.append((clause.decision, key[clause.clause_id].partner_decision))\n"
                  "agree = mean(skill == partner for skill, partner in pairs)"),
            output={"agreement": f"{agree:.0%}", "partner_escalations_caught": f"{esc_recall:.0%}",
                    "confusion (rows = partner, cols = skill)": confusion, "disagreements": misses})

    # Step 6: before/after against associates' past reviews
    hist = json.loads((DATA / "associate_history.json").read_text())
    base = json.loads((DATA / "baseline.json").read_text())
    all_agree = tot = 0
    assoc_edits = []
    for cid, h in hist.items():
        calls = h["associate_calls"]
        for clid in key[cid]:
            tot += 1
            all_agree += len({calls[a][clid] for a in calls}) == 1
        mine = calls[h["handled_by"]]
        assoc_edits.append(sum(mine[clid] != key[cid][clid]["partner_decision"] for clid in key[cid]))
    rerun = batch_structured(system=system, items=items, schema=ContractReview, offline=offline_review)
    same = sum(a.decision == b.decision for cid in reviews for a, b in zip(reviews[cid].clauses, rerun[cid].clauses))
    skill_edits = [sum(c.decision != key[cid][c.clause_id]["partner_decision"] for c in r.clauses) for cid, r in reviews.items()]
    before_min = sum(h["review_minutes"] for h in hist.values()) / len(hist)
    after_min = sum(base["skill_review_minutes_base"] + base["minutes_per_flagged_clause"] *
                    sum(c.decision != "OK" for c in r.clauses) for r in reviews.values()) / len(reviews)
    tr.step("Compare with how associates reviewed the same contracts", kind="check",
            what="Three associates' past calls on the same clauses are the baseline for consistency and partner edits.",
            code=("consistency_before = share of clauses where all 3 associates agreed\n"
                  "consistency_after = share of clauses with the same call on a second run\n"
                  "partner_edits = clauses per contract where the call differs from the partner"),
            output={"associates_all_agree": f"{all_agree / tot:.0%}", "skill_same_call_on_rerun": f"{same / tot:.0%}",
                    "partner_edits_per_contract": {"associates": round(sum(assoc_edits) / len(assoc_edits), 1),
                                                   "skill": round(sum(skill_edits) / len(skill_edits), 1)},
                    "review_minutes_per_contract": {"associates": round(before_min), "skill + associate check (est.)": round(after_min)}})

    tr.metrics(
        review_time_per_contract=f"{before_min:.0f} min -> {after_min:.0f} min (estimate: 10 min + 3 min per flagged clause)",
        consistency=f"{all_agree / tot:.0%} of clauses where 3 associates agree -> {same / tot:.0%} same call on rerun",
        partner_edits_per_contract=f"{sum(assoc_edits) / len(assoc_edits):.1f} -> {sum(skill_edits) / len(skill_edits):.1f}",
        agreement_with_partner=f"{agree:.0%} ({sum(a == b for a, b in pairs)}/{len(pairs)} clauses)",
        partner_escalations_caught=f"{esc_recall:.0%}",
        outputs=f"{len(reviews)} redlined .docx + {len(reviews)} issues memos",
    )
    tr.save()


if __name__ == "__main__":
    main()
