"""Build 02 - Prior-auth packet assistant (Healthcare). Pattern: RAG + human review."""
import difflib, json, re, sys
from pathlib import Path
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.claude import Trace, ask_structured  # noqa: E402
from common.citations import CitedBlock, Citation, ask_cited  # noqa: E402
from common.retrieval import TfidfIndex  # noqa: E402

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "outputs"
STATUS_RE = re.compile(r"\[([A-Z]{3}-\d{5}-\d+)\]\s*(MET|NOT MET|MISSING)\b")


# ---------- Step 1: chunk policies by section and embed ----------
def build_index() -> TfidfIndex:
    idx = TfidfIndex()
    for f in sorted((DATA / "policies").glob("*.md")):
        for sec in re.split(r"\n(?=## )", f.read_text()):
            if sec.startswith("## "):
                heading = sec.splitlines()[0][3:]
                idx.add(f"{f.stem}:{heading.split(' - ')[0]}", sec, payer=f.stem, heading=heading)
    return idx.build()


def criteria_from_section(text: str) -> list[dict]:
    return [{"id": m[0], "text": m[1]} for m in re.findall(r"^- \[(\S+)\] (.+)$", text, re.M)]


# ---------- Step 3: Claude maps chart evidence to each criterion, with citations ----------
MAP_SYSTEM = ("You are a prior-authorization nurse. For each payer criterion, decide whether the chart notes "
              "document it. Start each criterion on a new line as '[CRITERION_ID] MET:', '[CRITERION_ID] NOT MET:' "
              "(evidence exists but falls short) or '[CRITERION_ID] MISSING:' (nothing in the chart). "
              "Cite the exact chart sentence for every MET or NOT MET. Never infer facts that are not written.")

RULES = json.loads((DATA / "offline_rules.json").read_text()) if (DATA / "offline_rules.json").exists() else {}


def sentences(notes):
    for n in notes:
        for s in re.split(r"(?<=[.!?])\s+", n["text"]):
            if s.strip():
                yield n["title"], s.strip()


def offline_map(criteria, notes) -> list[CitedBlock]:
    """Rule-based stand-in: checks each criterion's test against every chart sentence."""
    blocks = []
    for c in criteria:
        t = RULES[c["id"]]
        status, cite, why = "MISSING", None, "No supporting documentation found in the chart."
        for title, s in sentences(notes):
            low = s.lower()
            if t["type"] == "any" and any(term in low for term in t["terms"]):
                status, cite, why = "MET", (title, s), "Documented in the chart."
                break
            if t["type"] == "weeks" and any(term in low for term in t["terms"]):
                m = re.search(r"(\d+)\s*(weeks?|months?)", low)
                if m:
                    weeks = int(m[1]) * (4.33 if m[2].startswith("month") else 1)
                    ok = weeks >= t["min"]
                    status, cite = ("MET" if ok else "NOT MET"), (title, s)
                    why = f"Chart shows {m[1]} {m[2]}; policy requires at least {t['min']} weeks."
                    if ok:
                        break
            if t["type"] == "value" and t["label"] in low:
                m = re.search(re.escape(t["label"]) + r"[^0-9]{0,30}(\d+(?:\.\d+)?)", low)
                if m:
                    v = float(m[1])
                    ok = v >= t["bound"] if t["op"] == ">=" else v < t["bound"]
                    status, cite = ("MET" if ok else "NOT MET"), (title, s)
                    why = f"Chart value {m[1]}; policy requires {t['op']} {t['bound']}."
                    break
        blocks.append(CitedBlock(text=f"[{c['id']}] {status}: {why}\n",
                                 citations=[Citation(cited_text=cite[1], document_title=cite[0])] if cite else []))
    return blocks


def parse_findings(blocks: list[CitedBlock]) -> dict:
    """Group cited text blocks under the criterion marker they follow (works for live and offline output)."""
    findings, cur = {}, None
    for b in blocks:
        for m in STATUS_RE.finditer(b.text):
            cur = m[1]
            findings[cur] = {"status": m[2], "explanation": b.text[m.end():].strip(" :\n"), "citations": []}
        if cur:
            findings[cur]["citations"] += [c.model_dump() for c in b.citations]
    return findings


# ---------- Step 4: flag missing evidence and draft the letter ----------
class PacketDraft(BaseModel):
    request_id: str
    ready_to_submit: bool = Field(description="true only if every criterion is MET with a citation")
    missing_items: list[str] = Field(description="what staff must obtain before submitting")
    letter: str = Field(description="medical necessity letter that quotes the cited chart evidence")

LETTER_SYSTEM = ("You draft prior-authorization packets. Given the payer criteria and the cited findings, list "
                 "anything MISSING or NOT MET as a concrete item to obtain, and draft a short medical necessity "
                 "letter that quotes only the cited chart evidence. Do not add clinical facts.")


def offline_letter(req, payer_name, proc, criteria, findings) -> PacketDraft:
    missing = [f"{c['id']}: {c['text']} ({findings[c['id']]['status']} - {findings[c['id']]['explanation']})"
               for c in criteria if findings[c["id"]]["status"] != "MET"]
    body = [f"To: {payer_name} Utilization Management",
            f"Re: Prior authorization for {proc} (CPT {req['cpt']}) - {req['patient']}",
            f"Diagnosis: {req['diagnosis']}", "",
            f"I am requesting authorization for {proc.lower()}. The chart documents each of your criteria:"]
    for c in criteria:
        f = findings[c["id"]]
        if f["status"] == "MET":
            q = f["citations"][0]
            body.append(f"- {c['text']} Chart ({q['document_title']}): \"{q['cited_text']}\"")
    body += ["", f"Sincerely, {req['clinician']}"]
    return PacketDraft(request_id=req["request_id"], ready_to_submit=not missing, missing_items=missing,
                       letter="\n".join(body))


def main():
    tr = Trace("02", "Prior-auth packet assistant", OUT)
    tr.arch([
        {"label": "Payer policy docs", "kind": "data", "note": "3 payers, chunked by section"},
        {"label": "Embeddings + pgvector", "kind": "system", "note": "TF-IDF stand-in here"},
        {"label": "EHR chart notes", "kind": "data", "note": "per request, under a BAA"},
        {"label": "Claude + citations", "kind": "ai", "note": "criterion -> cited chart text"},
        {"label": "Gap check + letter", "kind": "code", "note": "missing items, draft letter"},
        {"label": "Staff review screen", "kind": "human", "note": "edits become eval data"},
    ])
    tr.story(
        situation="A specialty clinic's prior-auth team spends hours per request matching each payer's rules to chart notes, and incomplete packets come back denied weeks later.",
        constraints="Chart notes are PHI, so the whole system runs under a BAA with no data retention outside the tenant. Every claim in a packet must point to a chart sentence. Staff, not the model, submit.",
        replay="Reuse: retrieve-the-rules, map-evidence-with-citations, human-submits works for any rules-vs-records check (claims, underwriting, audits). Next time: capture staff edits from day one so the eval set grows with real cases.",
        problem_cost="About 2.4 staff hours per request, and roughly 3 in 10 first submissions denied for missing documentation.",
    )

    # Step 1
    idx = build_index()
    payers = {f.stem: f.read_text().splitlines()[0][2:].split(" - ")[0] for f in (DATA / "policies").glob("*.md")}
    tr.step("Load payer policies, chunk by section, embed", kind="io",
            what=f"Split {len(payers)} payer policy manuals into {idx.stats()['chunks']} sections and embedded each one (TF-IDF stand-in for an embedding model + pgvector).",
            code=('for sec in re.split(r"\\n(?=## )", policy_md):\n'
                  '    idx.add(chunk_id, sec, payer=payer, heading=heading)\n'
                  'idx.build()  # prod: embed with a real model, INSERT INTO policy_chunks (embedding vector)'),
            output={"payers": payers, **idx.stats(),
                    "sample_chunk": idx.chunks[4]["id"] + "\n" + idx.chunks[4]["text"]})

    requests = json.loads((DATA / "requests.json").read_text())
    proc_names = {m[1]: m[0] for m in re.findall(r"## Section 4\.\d - (.+) \(CPT (\d+)\)", (DATA / "policies/RHP.md").read_text())}

    # Step 2
    retrieved = {}
    for r in requests:
        hits = idx.search(f"{proc_names[r['cpt']]} CPT {r['cpt']} medically necessary criteria", k=3, payer=r["payer"])
        retrieved[r["request_id"]] = (hits, criteria_from_section(hits[0][1]["text"]))
    hits0, crit0 = retrieved["REQ-102"]
    hit_ok = sum(f"CPT {r['cpt']}" in retrieved[r["request_id"]][0][0][1]["text"] for r in requests)
    tr.step("Retrieve this payer's criteria for the procedure", kind="code",
            what=f"For each request, searched only that payer's sections; the top hit was the right procedure section for {hit_ok}/{len(requests)} requests.",
            code=('hits = idx.search(f"{procedure} CPT {cpt} medically necessary criteria",\n'
                  '                  k=3, payer=req["payer"])  # metadata filter = WHERE payer = $1\n'
                  'criteria = criteria_from_section(hits[0].text)'),
            output="REQ-102 (Cascade Mutual, CPT 72148) top hits:\n" +
                   "\n".join(f"  {s:.3f}  {c['meta']['heading']}" for s, c in hits0) +
                   "\n\nCriteria retrieved:\n" + "\n".join(f"  [{c['id']}] {c['text']}" for c in crit0))

    # Step 3
    all_findings = {}
    for r in requests:
        crit = retrieved[r["request_id"]][1]
        prompt = (f"Payer: {payers[r['payer']]}. Procedure: {proc_names[r['cpt']]} (CPT {r['cpt']}).\nCriteria:\n" +
                  "\n".join(f"[{c['id']}] {c['text']}" for c in crit))
        blocks = ask_cited(system=MAP_SYSTEM, documents=r["notes"], prompt=prompt,
                           offline=lambda crit=crit, r=r: offline_map(crit, r["notes"]))
        all_findings[r["request_id"]] = parse_findings(blocks)
    uncited = [(rid, cid) for rid, fs in all_findings.items() for cid, f in fs.items()
               if f["status"] == "MET" and not f["citations"]]
    ex = all_findings["REQ-102"]
    tr.step("Map chart evidence to each criterion, with citations", kind="ai",
            what=f"Claude read each request's chart notes as cited documents and marked every criterion MET / NOT MET / MISSING; {len(uncited)} MET claims lacked a citation.",
            code=('content = [{"type": "document", "title": note["title"],\n'
                  '            "source": {"type": "text", "media_type": "text/plain", "data": note["text"]},\n'
                  '            "citations": {"enabled": True}} for note in req["notes"]]\n'
                  'blocks = ask_cited(system=MAP_SYSTEM, documents=req["notes"], prompt=criteria_list)\n'
                  'findings = parse_findings(blocks)  # block.citations -> cited_text, document_title'),
            output="REQ-102:\n" + "\n".join(
                f"  {cid}  {f['status']:<8} {f['explanation']}" +
                "".join(f"\n      cites ({c['document_title']}): \"{c['cited_text']}\"" for c in f["citations"])
                for cid, f in ex.items()))

    # Step 4
    drafts = {}
    for r in requests:
        crit = retrieved[r["request_id"]][1]
        findings = all_findings[r["request_id"]]
        drafts[r["request_id"]] = ask_structured(
            system=LETTER_SYSTEM,
            content=json.dumps({"request": {k: v for k, v in r.items() if k != "notes"}, "criteria": crit,
                                "findings": findings}, indent=2),
            schema=PacketDraft,
            offline=lambda r=r, crit=crit, findings=findings: offline_letter(
                r, payers[r["payer"]], proc_names[r["cpt"]], crit, findings))
    (OUT / "packets").mkdir(parents=True, exist_ok=True)
    for rid, d in drafts.items():
        (OUT / "packets" / f"{rid}.json").write_text(d.model_dump_json(indent=2))
    flagged = [rid for rid, d in drafts.items() if not d.ready_to_submit]
    tr.step("Flag missing evidence and draft the necessity letter", kind="ai",
            what=f"Packets for {len(drafts) - len(flagged)} requests are ready; {len(flagged)} are flagged with the exact items staff must obtain first.",
            code=("class PacketDraft(BaseModel):\n    ready_to_submit: bool\n    missing_items: list[str]\n    letter: str\n\n"
                  "draft = ask_structured(system=LETTER_SYSTEM, content=findings_json, schema=PacketDraft)"),
            output={"flagged": {rid: drafts[rid].missing_items for rid in flagged},
                    "REQ-101 letter": drafts["REQ-101"].letter})

    # Step 5: staff review. The nurse's decisions (answer key) are what staff would correct to.
    key = json.loads((DATA / "answer_key.json").read_text())
    letter_adds = json.loads((DATA / "staff_letter_edits.json").read_text())
    base = json.loads((DATA / "baseline.json").read_text())
    eval_rows, review_minutes, submitted, held = [], {}, [], []
    for r in requests:
        rid, edits = r["request_id"], 0
        for cid, staff_status in key[rid].items():
            model_status = all_findings[rid][cid]["status"]
            if model_status != staff_status:
                edits += 1
                eval_rows.append({"request_id": rid, "field": cid, "model": model_status, "staff": staff_status,
                                  "chart": [n["text"] for n in r["notes"]]})
        draft = drafts[rid].letter
        final = draft.replace("\n\nSincerely", f"\n{letter_adds[rid]}\n\nSincerely") if letter_adds.get(rid) else draft
        if final != draft:
            edits += 1
            eval_rows.append({"request_id": rid, "field": "letter", "model": draft, "staff": final,
                              "change_ratio": round(1 - difflib.SequenceMatcher(None, draft, final).ratio(), 3)})
        review_minutes[rid] = base["review_minutes_base"] + base["review_minutes_per_edit"] * edits
        (submitted if all(v == "MET" for v in key[rid].values()) else held).append(rid)
    with open(OUT / "eval_set.jsonl", "w") as fh:
        for row in eval_rows:
            fh.write(json.dumps(row) + "\n")
    n_fields = sum(len(v) + 1 for v in key.values())
    edit_rate = len(eval_rows) / n_fields
    tr.step("Staff review and submit; every edit becomes eval data", kind="human",
            what=f"Staff corrected {len(eval_rows)} of {n_fields} fields ({edit_rate:.0%} edit rate); each edit was saved to eval_set.jsonl. Complete packets went out; the rest were held for documents.",
            code=('if model_status != staff_status:\n'
                  '    eval_rows.append({"request_id": rid, "field": cid,\n'
                  '                      "model": model_status, "staff": staff_status})\n'
                  'submit if all(status == "MET") else hold_for_docs'),
            output={"submitted": submitted, "held_for_documents": held,
                    "edits": [f"{e['request_id']} {e['field']}: {e['model']} -> {e['staff']}" if e["field"] != "letter"
                              else f"{e['request_id']} letter: staff added a line ({e['change_ratio']:.0%} changed)"
                              for e in eval_rows],
                    "review_minutes": " ".join(f"{k}={v}" for k, v in review_minutes.items())})

    # Step 6: score against the nurse's answer key
    pairs = [(all_findings[rid][cid]["status"], s) for rid, crit in key.items() for cid, s in crit.items()]
    agree = sum(a == b for a, b in pairs) / len(pairs)
    gaps = [(rid, cid) for rid, crit in key.items() for cid, s in crit.items() if s != "MET"]
    caught = sum(all_findings[rid][cid]["status"] != "MET" for rid, cid in gaps)
    cite_ok = sum(bool(f["citations"]) for fs in all_findings.values() for f in fs.values() if f["status"] == "MET")
    n_met = sum(f["status"] == "MET" for fs in all_findings.values() for f in fs.values())
    false_flags = [(rid, cid) for rid, crit in key.items() for cid, s in crit.items()
                   if s == "MET" and all_findings[rid][cid]["status"] != "MET"]
    tr.step("Score against the nurse's answer key", kind="check",
            what="Compared every criterion decision with a prior-auth nurse's hand labels.",
            code=("pairs = [(findings[rid][cid].status, nurse) for rid, cid, nurse in answer_key]\n"
                  "agree = mean(model == nurse for model, nurse in pairs)\n"
                  "gaps = [c for c in answer_key if c.nurse != 'MET']\n"
                  "gap_recall = mean(findings[c].status != 'MET' for c in gaps)"),
            output={"criteria_checked": len(pairs), "agreement": f"{agree:.0%}",
                    "gap_recall": f"{caught}/{len(gaps)}", "MET_claims_with_citation": f"{cite_ok}/{n_met}",
                    "false_flags (model said gap, nurse said met)": [f"{a} {b}" for a, b in false_flags]})

    n = len(requests)
    after_hours = sum(review_minutes.values()) / n / 60
    tr.metrics(
        hours_per_request=f"{base['manual_hours_per_request']} -> {after_hours:.2f} (staff review time, simulated)",
        first_pass_approvals=f"{(n - len(held)) / n:.0%} if sent as-is -> {len(submitted)}/{len(submitted)} submitted packets complete",
        denials_avoided=f"{len(held)} incomplete packets held before submission ({', '.join(held)})",
        criterion_agreement_with_nurse=f"{agree:.0%}",
        gap_recall=f"{caught}/{len(gaps)}",
        staff_edit_rate=f"{edit_rate:.0%} ({len(eval_rows)} edits -> eval_set.jsonl)",
    )
    tr.save()


if __name__ == "__main__":
    main()
