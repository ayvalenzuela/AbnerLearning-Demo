"""Build 10 - Account research to proposal (B2B sales). Pattern: Skill + MCP.

CRM data comes through an MCP server, research through web search, and a proposal Skill maps the
account's pains to offers from the sales playbook. Code computes the ROI and renders a branded Word
proposal plus a first-call agenda for each account, filed by territory. The rep edits and sends, and
the win/loss log shows which sections win.
"""
import asyncio, json, re, sys
from datetime import date, timedelta
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm
from pydantic import BaseModel, Field

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from common.claude import Trace, ask_structured  # noqa: E402
from common.web_research import keyword_search, research  # noqa: E402
import crm_mcp_server as crm  # noqa: E402

D = lambda name: json.loads((HERE / "data" / f"{name}.json").read_text())
PLAYBOOK = D("playbook")
PAINS = PLAYBOOK["pains"]
SKILL = (HERE / "skill/proposal-writer/SKILL.md").read_text()
SKILL_BODY = SKILL.split("---", 2)[2].strip()
REP = {"name": "Jamie Rivera", "title": "Enterprise Account Executive", "email": "jamie.rivera@voxly.example"}
TODAY = date(2026, 11, 24)
SECTION_ORDER = ["exec_summary", "what_we_heard", "pains_solutions_table", "roi", "timeline", "pricing", "next_steps"]


# ---------- schemas ----------
class Finding(BaseModel):
    type: str = Field(description="news | job | tech")
    title: str
    url: str
    date: str
    summary: str
    about_this_company: bool = Field(description="false if the result is about a different company")

class AccountResearch(BaseModel):
    company: str
    findings: list[Finding]

class Evidence(BaseModel):
    quote: str
    source: str = Field(description="crm_note | news | job | tech")
    url: str

class MappedPain(BaseModel):
    pain_id: str = Field(description="a key from the playbook's pains")
    score: float
    evidence: list[Evidence]
    offer: str

class PainMap(BaseModel):
    account: str
    pains: list[MappedPain] = Field(description="top three, strongest first")

class PainRow(BaseModel):
    pain: str
    evidence: str
    solution: str
    outcome: str

class ProposalDraft(BaseModel):
    exec_summary: str
    rows: list[PainRow]
    next_steps: list[str]


# ---------- offline stand-ins (real rules over the same inputs) ----------
def offline_research(company: str, hits: list[dict]) -> AccountResearch:
    return AccountResearch(company=company, findings=[
        Finding(type=h["type"], title=h["title"], url=h["url"], date=h["date"],
                summary=h["text"].split(". ")[0].rstrip(".") + ".",
                about_this_company=company.lower() in (h["title"] + " " + h["text"]).lower())
        for h in hits])

def evidence_items(acct: dict, res: AccountResearch) -> list[dict]:
    items = [{"text": n, "source": "crm_note", "url": f"crm://{acct['account_id']}/notes"} for n in acct["notes"]]
    items += [{"text": f.title + ". " + next(h["text"] for h in RAW_HITS[acct["name"]] if h["url"] == f.url),
               "source": f.type, "url": f.url} for f in res.findings if f.about_this_company]
    return items

def offline_pain_map(acct: dict, res: AccountResearch) -> PainMap:
    w = PLAYBOOK["source_weight"]
    out = []
    for pid, p in PAINS.items():
        ev, score = [], 0.0
        for it in evidence_items(acct, res):
            low = it["text"].lower()
            if any(t in low for t in p["triggers"]):
                # quote the sentence with the most trigger phrases (first one wins a tie)
                sents = re.split(r"(?<=\.)\s+", it["text"])
                sentence = max(sents, key=lambda x: sum(t in x.lower() for t in p["triggers"]))
                ev.append(Evidence(quote=sentence.strip(), source=it["source"], url=it["url"]))
                score += w[it["source"]]
        if ev:
            out.append(MappedPain(pain_id=pid, score=round(score, 1), evidence=ev, offer=p["offer"]))
    out.sort(key=lambda m: (-m.score, -len(m.evidence)))
    return PainMap(account=acct["name"], pains=out[:3])

def offline_draft(acct, pmap: PainMap, roi: dict, contacts: list[dict]) -> ProposalDraft:
    top = pmap.pains[0]
    champ = next((c for c in contacts if c["role"] == "champion"), contacts[0])
    buyer = next((c for c in contacts if c["role"] == "economic buyer"), contacts[0])
    offers = list(dict.fromkeys(m.offer for m in pmap.pains))  # strongest pain first
    offer_txt = offers[0] if len(offers) == 1 else ", ".join(offers[:-1]) + " and " + offers[-1]
    summary = (f"The biggest issue we found at {acct['name']}: {PAINS[top.pain_id]['label'][0].lower() + PAINS[top.pain_id]['label'][1:]}. "
               f"{'From our conversations' if top.evidence[0].source == 'crm_note' else 'On the public record'}: "
               f"\"{top.evidence[0].quote}\" "
               f"We propose {offer_txt} for {acct['contact_center_agents']} agents, rolled out in "
               f"{sum(w for _, w in PLAYBOOK['timeline'])} weeks. Our model shows about ${roi['total']:,.0f} of "
               f"annual value and payback in about {roi['payback_months']:.0f} months at planning prices.")
    rows = [PainRow(pain=PAINS[m.pain_id]["label"], evidence=m.evidence[0].quote,
                    solution=f"{m.offer}: {PAINS[m.pain_id]['solution']}", outcome=PAINS[m.pain_id]["outcome"])
            for m in pmap.pains]
    steps = [f"{(TODAY + timedelta(days=7)).strftime('%b %d')}: first-call workshop with {champ['name']} ({champ['title']})",
             f"{(TODAY + timedelta(days=14)).strftime('%b %d')}: confirm ROI inputs with {buyer['name']} ({buyer['title']})",
             f"{(TODAY + timedelta(days=21)).strftime('%b %d')}: pilot scope and deal-desk pricing"]
    return ProposalDraft(exec_summary=summary, rows=rows, next_steps=steps)


# ---------- ROI (code, never the model) ----------
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}

def roi_for(acct: dict, pmap: PainMap) -> dict:
    a = PLAYBOOK["roi_assumptions"]; lines = []
    for m in pmap.pains:
        if m.pain_id == "high_abandon":
            v = acct["calls_per_month"] * 12 * acct["abandon_rate"] * a["abandon_reduction"] * acct["value_per_answered_call_usd"]
            basis = (f"{acct['calls_per_month']:,} calls/mo x 12 x {acct['abandon_rate']:.0%} abandoned x "
                     f"{a['abandon_reduction']:.0%} recovered x ${acct['value_per_answered_call_usd']}")
        elif m.pain_id == "agent_ramp":
            v = acct["new_agent_hires_per_year"] * a["ramp_days_saved"] * a["loaded_agent_cost_per_day_usd"]
            basis = f"{acct['new_agent_hires_per_year']} hires/yr x {a['ramp_days_saved']} days x ${a['loaded_agent_cost_per_day_usd']}/day"
        elif m.pain_id == "compliance_recording":
            v = a["audit_prep_hours_saved"] * a["compliance_hourly_cost_usd"]
            basis = f"{a['audit_prep_hours_saved']} audit-prep hours x ${a['compliance_hourly_cost_usd']}/h"
        elif m.pain_id == "legacy_pbx_eol":
            v = acct["pbx_maintenance_usd_per_year"]
            basis = "PBX maintenance retired (CRM)"
        elif m.pain_id == "multi_site":
            n = 1
            for e in m.evidence:
                if mm := re.search(r"(\d+|" + "|".join(WORDNUM) + r") (?:new )?(sites|branches|clinics)", e.quote, re.I):
                    n = int(mm[1]) if mm[1].isdigit() else WORDNUM[mm[1].lower()]
                    break
            v = n * a["site_setup_cost_avoided_usd"]
            basis = f"{n} new {mm[2] if mm else 'site'} x ${a['site_setup_cost_avoided_usd']:,} set-up avoided"
        else:  # crm_fragmentation
            v = acct["calls_per_month"] * 12 * a["seconds_saved_per_call"] / 3600 * a["agent_hourly_cost_usd"]
            basis = f"{acct['calls_per_month']:,} calls/mo x 12 x {a['seconds_saved_per_call']}s x ${a['agent_hourly_cost_usd']}/h"
        lines.append({"pain_id": m.pain_id, "offer": m.offer, "annual_value_usd": round(v), "basis": basis})
    total = sum(l["annual_value_usd"] for l in lines)
    cost = acct["contact_center_agents"] * PLAYBOOK["planning_price_per_seat_month_usd"] * 12
    return {"lines": lines, "total": total, "annual_cost_planning_usd": cost,
            "payback_months": round(cost / (total / 12), 1) if total else None}


# ---------- Word proposal ----------
BRAND = RGBColor.from_string(PLAYBOOK["brand_color"])

def shade(cell, hex_fill):
    pr = cell._tc.get_or_add_tcPr(); s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), hex_fill); pr.append(s)

def cell_text(cell, text, bold=False, color=None, size=10):
    cell.text = ""; r = cell.paragraphs[0].add_run(text); r.bold = bold; r.font.size = Pt(size)
    if color: r.font.color.rgb = color

def table(doc, header, rows, widths):
    t = doc.add_table(rows=1, cols=len(header)); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.style = "Table Grid"
    for i, h in enumerate(header):
        cell_text(t.rows[0].cells[i], h, bold=True, color=RGBColor(255, 255, 255)); shade(t.rows[0].cells[i], PLAYBOOK["brand_color"])
    for n, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cell_text(cells[i], str(v), bold=(i == 0))
            if n % 2: shade(cells[i], PLAYBOOK["accent_color"])
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
    return t

def heading(doc, text):
    p = doc.add_paragraph(); r = p.add_run(text); r.bold = True; r.font.size = Pt(15); r.font.color.rgb = BRAND
    p.paragraph_format.space_before = Pt(14); p.paragraph_format.space_after = Pt(4)

def page_field(par):
    """Insert a live PAGE number field (begin / instruction / end)."""
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        r = par.add_run(); r.font.size = Pt(8)
        if kind:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = text
        r._r.append(el)

def render_proposal(path, acct, contacts, deal, pmap, draft, roi):
    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
    sec = doc.sections[0]; sec.left_margin = sec.right_margin = Cm(2.2)
    fp = sec.footer.paragraphs[0]; fp.text = f"Voxly  |  Confidential  |  Proposal for {acct['name']}  |  Page "
    page_field(fp); fp.runs[0].font.size = Pt(8)
    # cover
    band = doc.add_table(rows=1, cols=1); shade(band.rows[0].cells[0], PLAYBOOK["brand_color"])
    cell_text(band.rows[0].cells[0], "VOXLY", bold=True, color=RGBColor(255, 255, 255), size=20)
    for _ in range(4): doc.add_paragraph()
    t = doc.add_paragraph(); r = t.add_run(f"Proposal for {acct['name']}"); r.bold = True; r.font.size = Pt(28); r.font.color.rgb = BRAND
    s = doc.add_paragraph(); r = s.add_run(deal["name"] if deal else "Customer communications"); r.font.size = Pt(16)
    doc.add_paragraph()
    buyer = next((c for c in contacts if c["role"] == "economic buyer"), contacts[0])
    for k, v in [("Prepared for", f"{buyer['name']}, {buyer['title']}"), ("Prepared by", f"{REP['name']}, {REP['title']}"),
                 ("Date", TODAY.strftime("%B %d, %Y")), ("Reference", deal["deal_id"] if deal else "-")]:
        p = doc.add_paragraph(); a = p.add_run(f"{k}:  "); a.bold = True; p.add_run(v)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    # sections, fixed order (the Skill's contract)
    heading(doc, "1. Executive summary"); doc.add_paragraph(draft.exec_summary)
    heading(doc, "2. What we heard")
    for m in pmap.pains:
        p = doc.add_paragraph(style="List Bullet"); r = p.add_run(PAINS[m.pain_id]["label"] + ". "); r.bold = True
        e = m.evidence[0]; p.add_run(f"“{e.quote}” ")
        src = p.add_run(f"({e.source.replace('_', ' ')}: {e.url})"); src.font.size = Pt(8); src.font.color.rgb = RGBColor(110, 110, 110)
    heading(doc, "3. Pains and solutions")
    table(doc, ["Pain", "Evidence", "Voxly solution", "Expected outcome"],
          [[r.pain, r.evidence, r.solution, r.outcome] for r in draft.rows], [3.6, 5.0, 4.4, 3.6])
    heading(doc, "4. Return on investment")
    table(doc, ["Offer", "How we calculated it", "Annual value"],
          [[l["offer"], l["basis"], f"${l['annual_value_usd']:,}"] for l in roi["lines"]]
          + [["Total", "", f"${roi['total']:,}"]], [4.0, 9.2, 3.4])
    doc.add_paragraph(f"Planning cost: {acct['contact_center_agents']} seats x ${PLAYBOOK['planning_price_per_seat_month_usd']}/seat/month "
                      f"= ${roi['annual_cost_planning_usd']:,} a year. Payback: about {roi['payback_months']} months. "
                      "Inputs come from your CRM record and our playbook; we will confirm them with you.").runs[0].font.size = Pt(9)
    heading(doc, "5. Timeline")
    wk = 0; rows = []
    for name, weeks in PLAYBOOK["timeline"]:
        rows.append([name, f"Weeks {wk + 1}-{wk + weeks}"]); wk += weeks
    table(doc, ["Phase", "When"], rows, [10.0, 6.6])
    heading(doc, "6. Investment")
    p = doc.add_paragraph(); r = p.add_run("[Pricing to be confirmed by the Voxly deal desk]"); r.bold = True; r.font.color.rgb = RGBColor(170, 60, 40)
    doc.add_paragraph(f"Scope: {acct['contact_center_agents']} contact-center seats, offers: {', '.join(sorted({m.offer for m in pmap.pains}))}.")
    heading(doc, "7. Next steps")
    for s in draft.next_steps:
        doc.add_paragraph(s, style="List Number")
    doc.save(path)

def render_agenda(path, acct, contacts, deal, pmap):
    lines = [f"# First call: {acct['name']}", "",
             f"**Deal:** {deal['name']} ({deal['stage']}, ${deal['amount_usd']:,})  ", f"**Voxly:** {REP['name']}, {REP['title']}", "",
             "## Attendees"] + [f"- {c['name']}, {c['title']} ({c['role']})" for c in contacts] + [
             "", "## Objectives (45 minutes)",
             f"1. Confirm the top pain: {PAINS[pmap.pains[0].pain_id]['label'][0].lower() + PAINS[pmap.pains[0].pain_id]['label'][1:]}.",
             "2. Agree the ROI inputs (calls, abandon rate, hires, current costs).",
             "3. Agree a pilot scope and who signs off.", "", "## Discovery questions"]
    for m in pmap.pains:
        lines.append(f"- **{PAINS[m.pain_id]['label']}** - {PAINS[m.pain_id]['discovery_q']}  ")
        lines.append(f"  _Why we ask:_ \"{m.evidence[0].quote}\" ({m.evidence[0].source.replace('_', ' ')})")
        if len(m.evidence) == 1:
            lines.append("  _Thin evidence: one source only. Ask before we build on it._")
    lines += ["", "## Proposed next step", f"- {deal['next_step']}, then a pilot plan within two weeks."]
    path.write_text("\n".join(lines) + "\n")


RAW_HITS: dict[str, list[dict]] = {}

def main():
    tr = Trace("10", "Account research to proposal", HERE / "outputs")
    tr.arch([
        {"label": "CRM", "kind": "data", "note": "via MCP server"},
        {"label": "Web search", "kind": "system", "note": "news, hiring, tech stack"},
        {"label": "Proposal Skill", "kind": "ai", "note": "pains -> offers, playbook"},
        {"label": "ROI calculator", "kind": "code", "note": "numbers from code only"},
        {"label": "Word proposal + agenda", "kind": "system", "note": "filed per territory"},
        {"label": "Rep edits and sends", "kind": "human", "note": "final say"},
        {"label": "Win/loss log", "kind": "data", "note": "which sections win"},
    ])
    tr.story(
        situation="An enterprise UCaaS sales team. Reps spend most of a day researching each account and building a proposal from scratch, and no two proposals look alike, so nobody can tell which parts actually win deals.",
        constraints="CRM access is read-only and goes through one MCP server, so IT can audit it. Every pain must cite a source the rep can check. ROI numbers come from a calculator, never from the model. The rep edits and sends; nothing goes to a buyer automatically.",
        replay="Reuse: 'Skill holds the playbook, MCP holds the data, code holds the numbers' fits any repeatable document: QBRs, renewal briefs, RFP answers. Next time: weight the pain scoring with the win/loss log, and add a 'thin evidence' check that blocks a pain with a single tech-stack source.",
    )

    # Step 1: CRM through MCP --------------------------------------------------
    tools = asyncio.run(crm.mcp.list_tools())
    accounts = crm.list_accounts()
    data = {}
    for a in accounts:
        acct = crm.get_account(a["account_id"])
        data[acct["name"]] = {"acct": acct, "contacts": crm.list_contacts(a["account_id"]),
                              "deal": (crm.list_open_deals(a["account_id"]) or [None])[0]}
    tr.step("Pull the account, contacts and open deals from the CRM", kind="io",
            what=f"The CRM MCP server exposes {len(tools)} read-only tools; the pipeline calls them for {len(accounts)} fictional accounts.",
            code=("mcp = MCPServer('voxly-crm')   # crm_mcp_server.py\n"
                  "@mcp.tool()\n"
                  "def list_open_deals(account_id: str) -> list[dict]: ...\n\n"
                  "acct = crm.get_account(id); contacts = crm.list_contacts(id)"),
            output="MCP tools: " + ", ".join(t.name for t in tools) + "\n\n" + "\n".join(
                f"{n} ({v['acct']['territory']}, {v['acct']['industry']}): {v['acct']['contact_center_agents']} agents, "
                f"{len(v['contacts'])} contacts, deal {v['deal']['deal_id']} {v['deal']['stage']} ${v['deal']['amount_usd']:,}"
                for n, v in data.items()))

    # Step 2: research -----------------------------------------------------------
    index = D("search_index")
    researched = {}
    for name in data:
        r = research(name, [f"{name} news", f"{name} hiring jobs", f"{name} tech stack"],
                     offline_search=lambda q: keyword_search(index, q, k=4))
        RAW_HITS[name] = r["hits"]
        researched[name] = ask_structured(
            system="Turn these search results into findings. Mark results about other companies.",
            content=f"Company: {name}\n\nModel notes:\n{r['text']}\n\nResults:\n{json.dumps(r['hits'], indent=1)}",
            schema=AccountResearch, offline=lambda name=name, h=r["hits"]: offline_research(name, h))
    out_lines = []
    for name, res in researched.items():
        keep = [f for f in res.findings if f.about_this_company]
        drop = [f for f in res.findings if not f.about_this_company]
        out_lines.append(f"{name}: {len(keep)} findings kept, {len(drop)} dropped")
        out_lines += [f"  [{f.type}] {f.date} {f.title}" for f in keep]
        out_lines += [f"  dropped (other company): {f.title}" for f in drop]
    tr.step("Research news, hiring and tech stack with web search", kind="ai",
            what="Three searches per account through the web search tool; results about look-alike companies are dropped.",
            code=("tools = [{'type': 'web_search_20260209', 'name': 'web_search',\n"
                  "          'max_uses': 5}]\n"
                  "resp = client.messages.create(model=MODEL, tools=tools, ...)\n"
                  "research = ask_structured(..., schema=AccountResearch)"),
            output="\n".join(out_lines))

    # Step 3: pains -> offers with the Skill ------------------------------------
    maps = {}
    for name, v in data.items():
        maps[name] = ask_structured(
            system=SKILL_BODY + "\n\nPlaybook:\n" + json.dumps(PLAYBOOK["pains"]) + "\nSource weights: " + json.dumps(PLAYBOOK["source_weight"]),
            content=f"CRM record:\n{json.dumps(v['acct'])}\n\nResearch:\n{researched[name].model_dump_json()}\n\nDo Step 1 of the Skill.",
            schema=PainMap, offline=lambda v=v, name=name: offline_pain_map(v["acct"], researched[name]))
    tr.step("Map their pains to your offers with the sales playbook", kind="ai",
            what="The proposal Skill (SKILL.md) is the system prompt; it scores each playbook pain by cited evidence and keeps the top three.",
            code=("skill = Path('skill/proposal-writer/SKILL.md').read_text()\n"
                  "pmap = ask_structured(system=skill + playbook,\n"
                  "                      content=crm_record + research,\n"
                  "                      schema=PainMap)"),
            output="\n".join(f"{n}:\n" + "\n".join(
                f"  {m.pain_id:<21} score {m.score:<4} -> {m.offer:<26} e.g. \"{m.evidence[0].quote[:60]}\"" for m in pm.pains)
                for n, pm in maps.items()))

    # Step 4: proposal + agenda --------------------------------------------------
    rois, made = {}, []
    for name, v in data.items():
        rois[name] = roi_for(v["acct"], maps[name])
        draft = ask_structured(
            system=SKILL_BODY, schema=ProposalDraft,
            content=(f"Do Step 2 of the Skill.\nCRM: {json.dumps(v['acct'])}\nContacts: {json.dumps(v['contacts'])}\n"
                     f"Pain map: {maps[name].model_dump_json()}\nROI (use these numbers only): {json.dumps(rois[name])}"),
            offline=lambda v=v, name=name: offline_draft(v["acct"], maps[name], rois[name], v["contacts"]))
        folder = HERE / "outputs/territories" / v["acct"]["territory"] / re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        folder.mkdir(parents=True, exist_ok=True)
        render_proposal(folder / "proposal.docx", v["acct"], v["contacts"], v["deal"], maps[name], draft, rois[name])
        render_agenda(folder / "first_call_agenda.md", v["acct"], v["contacts"], v["deal"], maps[name])
        made.append((name, folder, draft))
    n0, f0, d0 = made[0]
    tr.step("Generate a branded proposal and a first-call agenda", kind="ai",
            what="Claude drafts the words; code computes the ROI and renders the same seven sections for every account, filed by territory.",
            code=("roi = roi_for(acct, pmap)          # code, never the model\n"
                  "draft = ask_structured(system=skill, content=pmap + roi,\n"
                  "                       schema=ProposalDraft)\n"
                  "render_proposal(folder / 'proposal.docx', ...)\n"
                  "render_agenda(folder / 'first_call_agenda.md', ...)"),
            output="\n".join(f"{f.relative_to(HERE)}/proposal.docx  ROI ${rois[n]['total']:,}/yr, payback {rois[n]['payback_months']} mo"
                             for n, f, _ in made)
            + f"\n\nExecutive summary ({n0}):\n{d0.exec_summary}\n\nROI lines ({n0}):\n"
            + "\n".join(f"  {l['offer']:<26} ${l['annual_value_usd']:>9,}  {l['basis']}" for l in rois[n0]["lines"]))

    # Step 5: rep edits and sends; which sections win -----------------------------
    log, edits = D("win_loss_log"), D("rep_edits")
    secs = sorted({s for p in log for s in p["sections"]})
    rates = {}
    for s in secs:
        inc = [p for p in log if s in p["sections"]]; exc = [p for p in log if s not in p["sections"]]
        if len(inc) >= 3 and len(exc) >= 3:
            wr = lambda g: sum(p["outcome"] == "won" for p in g) / len(g)
            rates[s] = {"win_with": round(wr(inc), 2), "win_without": round(wr(exc), 2),
                        "lift_pts": round(100 * (wr(inc) - wr(exc))), "n_with": len(inc), "n_without": len(exc)}
    by_t = {}
    for t in ("freeform", "skill"):
        g = [p for p in log if p["template"] == t]
        by_t[t] = {"proposals": len(g), "hours": round(sum(p["hours_spent"] for p in g) / len(g), 1),
                   "meeting_rate": round(sum(p["meeting_booked"] for p in g) / len(g), 2),
                   "win_rate": round(sum(p["outcome"] == "won" for p in g) / len(g), 2)}
    keep = [s for s, r in rates.items() if r["lift_pts"] >= 10]
    drop = [s for s, r in rates.items() if r["lift_pts"] <= -10]
    add_to_skill = [s for s in keep if s not in SECTION_ORDER]
    (HERE / "outputs/section_win_rates.json").write_text(json.dumps(
        {"by_section": rates, "by_template": by_t, "keep": keep, "drop": drop, "add_to_skill": add_to_skill,
         "rep_edits_this_run": {k: v for k, v in edits.items() if k != "note"}}, indent=2))
    edit_min = [v["minutes"] for k, v in edits.items() if k != "note"]
    tr.step("Rep edits and sends; track which sections win", kind="human",
            what=f"The rep edited each draft ({', '.join(f'{m} min' for m in edit_min)}) and sent it. A simulated win/loss log of {len(log)} past proposals shows which sections move the win rate.",
            code=("for s in sections:\n"
                  "    lift = win_rate(with s) - win_rate(without s)\n"
                  "keep = [s for s in sections if lift[s] >= 10]   # points\n"
                  "drop = [s for s in sections if lift[s] <= -10]"),
            output="\n".join(f"{s:<22} win {r['win_with']:.0%} with / {r['win_without']:.0%} without  "
                             f"({r['lift_pts']:+d} pts, n={r['n_with']}/{r['n_without']})" for s, r in
                             sorted(rates.items(), key=lambda kv: -kv[1]["lift_pts"]))
            + "\n\n" + "\n".join(f"{t:<9} {v['proposals']} proposals  {v['hours']} h each  meetings {v['meeting_rate']:.0%}  "
                                 f"wins {v['win_rate']:.0%}" for t, v in by_t.items())
            + f"\n\nKeep: {', '.join(keep) or '-'}   Drop: {', '.join(drop) or '-'}"
            + f"\nSkill update: add {', '.join(add_to_skill) or 'nothing'} (wins, not yet a Skill section)")

    # Step 6: pains vs the rep's own read ------------------------------------------
    key = D("answer_key")
    tp = sum(len(set(key[n]) & {m.pain_id for m in maps[n].pains}) for n in key)
    total = sum(len(v) for v in key.values())
    detail = {n: {"agent": [m.pain_id for m in maps[n].pains], "rep": key[n],
                  "missed": sorted(set(key[n]) - {m.pain_id for m in maps[n].pains}),
                  "extra": sorted({m.pain_id for m in maps[n].pains} - set(key[n]))} for n in key}
    tr.step("Check the pain mapping against the rep's own read", kind="check",
            what="Before seeing the output, the rep wrote down each account's top three pains; we score the Skill's picks against them.",
            code=("hits = len(set(rep_pains) & set(agent_pains))\n"
                  "match = sum(hits) / sum(len(rep_pains))"),
            output=f"pain_match: {tp}/{total} ({tp / total:.0%})\n\n" + "\n".join(
                f"{n}:\n  Skill: {', '.join(v['agent'])}\n  Rep:   {', '.join(v['rep'])}\n"
                f"  missed: {', '.join(v['missed']) or '-'}   extra: {', '.join(v['extra']) or '-'}" for n, v in detail.items()))

    f, s = by_t["freeform"], by_t["skill"]
    tr.metrics(
        hours_per_proposal=f"{f['hours']} -> {s['hours']} (log); this run: {sum(edit_min) / len(edit_min):.0f} min of rep edits",
        meetings_booked=f"{f['meeting_rate']:.0%} -> {s['meeting_rate']:.0%} of proposals",
        win_rate=f"{f['win_rate']:.0%} -> {s['win_rate']:.0%}",
        pain_match_vs_rep=f"{tp}/{total} ({tp / total:.0%})",
        proposals_generated=f"{len(made)} (same {len(SECTION_ORDER)} sections, same order)",
        top_section_by_lift=max(rates, key=lambda k: rates[k]["lift_pts"]),
    )
    tr.save()


if __name__ == "__main__":
    main()
