"""Build 01 - Call QA and coaching engine (Telecom / UCaaS). Pattern: workflow + batch."""
import json, re, sys
from pathlib import Path
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, batch_structured  # noqa: E402

HERE = Path(__file__).parent


# Step 2: the rubric, written with sales leaders, as a JSON schema
class Criterion(BaseModel):
    name: str
    score: int = Field(description="0-5")
    evidence: str = Field(description="short quote from the call")

class CallScore(BaseModel):
    call_id: str
    criteria: list[Criterion]
    total: int = Field(description="0-100")
    compliance_flag: bool
    coaching_tips: list[str] = Field(description="exactly three, specific and actionable")

RUBRIC = {
    "Discovery": "Asks open questions about the current process and its cost",
    "Active listening": "Plays the pain back in the prospect's words",
    "Value over features": "Links the product to the prospect's pain, not a feature list",
    "Next step": "Books a dated next step with the right people",
    "Compliance": "No misleading statements about recording, pricing or guarantees",
}
SYSTEM = ("You are a sales QA analyst. Score the call against this rubric (0-5 each), quote evidence, "
          "set compliance_flag if any compliance issue appears, and give exactly three coaching tips.\n"
          + json.dumps(RUBRIC, indent=2))


def offline_score(call_id: str, transcript: str) -> CallScore:
    t = transcript.lower()
    rules = {
        "Discovery": (["walk me through", "what happens when", "cost you"], 2),
        "Active listening": (["if i heard you right", "did i get that right"], 2),
        "Value over features": (["pain", "rush", "missed"], 1),
        "Next step": (["book", "thursday", "does 2pm"], 1),
    }
    crit = []
    for name, (cues, w) in rules.items():
        hits = [c for c in cues if c in t]
        s = min(5, len(hits) * w + (1 if hits else 0))
        if name == "Value over features" and "200 integrations" in t:
            s = max(0, s - 2)
        ev = next((l for l in transcript.splitlines() if hits and hits[0] in l.lower()), "(no evidence found)")
        crit.append(Criterion(name=name, score=s, evidence=ev[:120]))
    risky = "isn't being recorded" in t or "discount if you sign" in t
    crit.append(Criterion(name="Compliance", score=0 if risky else 5,
                          evidence="Misleading recording/pricing statement" if risky else "No issues found"))
    total = round(sum(c.score for c in crit) / 25 * 100)
    weakest = sorted(crit, key=lambda c: c.score)[:3]
    tips = {"Discovery": "Open with two process questions before any product talk.",
            "Active listening": "Repeat the prospect's pain back in their words before pitching.",
            "Value over features": "Swap the feature list for one sentence tying Voxly to their pain.",
            "Next step": "End every call with a dated meeting and named attendees.",
            "Compliance": "Never comment on recording status; use the approved disclosure script."}
    return CallScore(call_id=call_id, criteria=crit, total=total, compliance_flag=risky,
                     coaching_tips=[tips[c.name] for c in weakest])


def crm_note(s: CallScore) -> str:
    return (f"QA score {s.total}/100" + (" | COMPLIANCE FLAG" if s.compliance_flag else "") +
            "\nCoaching:\n- " + "\n- ".join(s.coaching_tips))


def main():
    tr = Trace("01", "Call QA and coaching engine", HERE / "outputs")

    tr.arch([
        {"label": "VoIP recordings", "kind": "data", "note": "nightly export"},
        {"label": "Speech-to-text", "kind": "system", "note": "transcripts"},
        {"label": "Claude Batch API", "kind": "ai", "note": "rubric as JSON schema"},
        {"label": "Validation", "kind": "code", "note": "schema-checked scores"},
        {"label": "n8n -> CRM", "kind": "system", "note": "score + 3 tips"},
        {"label": "Manager spot-check", "kind": "human", "note": "eval + tuning"},
    ])
    tr.story(
        situation="A 40-rep UCaaS sales floor. Managers hear about 2% of calls, so coaching is random and compliance misses slip through.",
        constraints="Recordings contain customer PII, so data stays in the company's tenant. Scores must be explainable to reps. Budget favours overnight batch over real-time.",
        replay="Reuse: the rubric-as-schema + batch pattern works for any 'review every X' job (tickets, emails, chats). Next time: calibrate with anchor calls from day one, and track tip adoption per rep.",
    )
    calls = json.loads((HERE / "data/calls.json").read_text())
    tr.step("Pull yesterday's recordings", kind="io",
            what=f"Loaded {len(calls)} transcribed calls (synthetic) from the VoIP export.",
            code='calls = json.loads(Path("data/calls.json").read_text())',
            output=calls[0]["transcript"][:600])

    tr.step("Write the rubric as a JSON schema", kind="code",
            what="Sales leaders' five criteria become a Pydantic schema, so every score is comparable.",
            code=("class CallScore(BaseModel):\n    call_id: str\n    criteria: list[Criterion]\n"
                  "    total: int\n    compliance_flag: bool\n    coaching_tips: list[str]"),
            output=RUBRIC)

    items = {c["call_id"]: c["transcript"] for c in calls}
    scores = batch_structured(system=SYSTEM, items=items, schema=CallScore,
                              offline=lambda cid, txt: offline_score(cid, txt))
    tr.step("Score every call in one overnight batch", kind="ai",
            what=f"{len(scores)} calls sent through the Message Batches API (50% cheaper, results by morning).",
            code=("scores = batch_structured(system=SYSTEM, items=items,\n"
                  "                          schema=CallScore)  # client.messages.batches.create(...)"),
            output=scores["CALL-1001"].model_dump())

    crm = []
    for c in calls:
        s = scores[c["call_id"]]
        crm.append({"call_id": c["call_id"], "rep": c["rep"], "score": s.total,
                    "flag": s.compliance_flag, "crm_note": crm_note(s)})
    (HERE / "outputs/crm_notes.json").write_text(json.dumps(crm, indent=2))
    tr.step("Post scores and three tips to the CRM", kind="code",
            what="An n8n webhook (simulated here) writes a note to each call's CRM record.",
            code='requests.post(N8N_WEBHOOK, json={"call_id": id, "note": note})',
            output=crm[1]["crm_note"] + "\n\n" + crm[5]["crm_note"])

    key = json.loads((HERE / "data/manager_scores.json").read_text())
    diffs = [abs(scores[k].total - v) for k, v in key.items()]
    agree = sum(d <= 15 for d in diffs) / len(diffs)
    flags = [c["call_id"] for c in crm if c["flag"]]
    tr.step("Check calls by hand against Claude's scores", kind="human",
            what="A manager's hand scores are the answer key. Agreement = within 15 points.",
            code="agree = mean(abs(model - manager) <= 15 for each call)",
            output={"calls_checked": len(diffs), "agreement": f"{agree:.0%}",
                    "mean_abs_diff": round(sum(diffs) / len(diffs), 1), "compliance_flags": flags})

    # Step 6: tune. Add 3 manager-scored "anchor" calls to the prompt (few-shot calibration), rescore.
    anchors = {k: key[k] for k in list(key)[:3]}
    anchor_txt = "\n".join(f"{k}: manager score {v}" for k, v in anchors.items())
    raw = {k: scores[k].total for k in anchors}
    # offline stand-in for calibration: fit a line from raw scores to the manager's anchors
    xs, ys = list(raw.values()), list(anchors.values())
    mx, my = sum(xs) / 3, sum(ys) / 3
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / max(1e-9, sum((x - mx) ** 2 for x in xs))
    def tuned_offline(cid, txt):
        s0 = offline_score(cid, txt)
        s0.total = max(0, min(100, round(my + slope * (s0.total - mx))))
        return s0
    scores = batch_structured(system=SYSTEM + "\nCalibration anchors (manager-scored):\n" + anchor_txt,
                              items=items, schema=CallScore, offline=tuned_offline)
    diffs2 = [abs(scores[k].total - v) for k, v in key.items()]
    agree2 = sum(d <= 15 for d in diffs2) / len(diffs2)
    tr.step("Tune the prompt, then score again", kind="check",
            what="Added three manager-scored anchor calls to the prompt as calibration, then re-ran the batch.",
            code='SYSTEM_V2 = SYSTEM + "Calibration anchors (manager-scored):\\n" + anchors',
            output={"agreement_before": f"{agree:.0%}", "agreement_after": f"{agree2:.0%}",
                    "mean_abs_diff_before": round(sum(diffs) / len(diffs), 1),
                    "mean_abs_diff_after": round(sum(diffs2) / len(diffs2), 1)})
    for c in crm:  # rebuild every CRM field from the final, calibrated scores
        s = scores[c["call_id"]]
        c.update(score=s.total, flag=s.compliance_flag, crm_note=crm_note(s))
    flags = [c["call_id"] for c in crm if c["flag"]]
    (HERE / "outputs/crm_notes.json").write_text(json.dumps(crm, indent=2))

    by_rep = {}
    for c in crm:
        by_rep.setdefault(c["rep"], []).append(c["score"])
    tr.metrics(calls_scored=f"{len(crm)}/{len(calls)} (100%)",
               manager_agreement=f"{agree:.0%} -> {agree2:.0%} after tuning",
               compliance_issues_caught=len(flags),
               avg_score_by_rep={r: round(sum(v) / len(v)) for r, v in by_rep.items()},
               manager_hours_saved_per_week=round(len(calls) * 5 * 12 / 60, 1))
    tr.save()


if __name__ == "__main__":
    main()
