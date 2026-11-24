"""Generate a synthetic CRM (3 fictional accounts), a local 'search index' of fictional news, job posts and
tech-stack pages, the sales playbook, the rep's hand-labelled answer key, and a simulated win/loss log.
Every company, person and URL here is made up."""
import json, random
from pathlib import Path

random.seed(10)
d = Path("data"); d.mkdir(exist_ok=True)

crm = {"accounts": [
    {"account_id": "ACC-101", "name": "Halvorsen Freight Group", "industry": "Logistics", "territory": "Central",
     "hq": "Kansas City, MO", "employees": 2400, "contact_center_agents": 180, "calls_per_month": 42000,
     "abandon_rate": 0.11, "value_per_answered_call_usd": 38, "new_agent_hires_per_year": 70,
     "pbx_maintenance_usd_per_year": 96000, "current_provider": "on-prem PBX + a hosted IVR",
     "contract_end": "2027-06-30",
     "notes": ["VP Ops said customers complain about hold times in peak season.",
               "Phone contract with the current vendor ends June 2027.",
               "Integrating the depots of a newly acquired courier is the top IT project this year."]},
    {"account_id": "ACC-102", "name": "Meridian Health Partners", "industry": "Healthcare", "territory": "East",
     "hq": "Richmond, VA", "employees": 5800, "contact_center_agents": 320, "calls_per_month": 95000,
     "abandon_rate": 0.09, "value_per_answered_call_usd": 22, "new_agent_hires_per_year": 90,
     "pbx_maintenance_usd_per_year": 140000, "current_provider": "hosted contact center, contract ends 2027",
     "contract_end": "2027-03-31",
     "notes": ["Compliance flagged call recording retention gaps in the last HIPAA audit.",
               "Patient access center agents swivel between the scheduling system and a homegrown CRM."]},
    {"account_id": "ACC-103", "name": "Quarry Lane Credit Union", "industry": "Financial services",
     "territory": "West", "hq": "Boise, ID", "employees": 900, "contact_center_agents": 60,
     "calls_per_month": 18000, "abandon_rate": 0.05, "value_per_answered_call_usd": 30,
     "new_agent_hires_per_year": 12, "pbx_maintenance_usd_per_year": 54000,
     "current_provider": "on-prem PBX (end of support 2027)", "contract_end": "2027-01-31",
     "notes": ["IT says the on-prem PBX reaches end of support in 2027.",
               "Member services wants one phone system across branches after the merger.",
               "PCI audit asks for call recording with pause-and-resume for card numbers."]},
],
"contacts": [
    {"account_id": "ACC-101", "name": "Dana Whitfield", "title": "VP Operations", "role": "economic buyer", "last_touch": "2026-11-12"},
    {"account_id": "ACC-101", "name": "Luis Moreno", "title": "Director, Customer Service", "role": "champion", "last_touch": "2026-11-18"},
    {"account_id": "ACC-101", "name": "Kira Jensen", "title": "IT Infrastructure Manager", "role": "technical evaluator", "last_touch": "2026-10-30"},
    {"account_id": "ACC-102", "name": "Dr. Alan Pierce", "title": "Chief Operating Officer", "role": "economic buyer", "last_touch": "2026-10-21"},
    {"account_id": "ACC-102", "name": "Renee Takahashi", "title": "Director, Patient Access", "role": "champion", "last_touch": "2026-11-19"},
    {"account_id": "ACC-102", "name": "Omar Haddad", "title": "Compliance Officer", "role": "influencer", "last_touch": "2026-11-05"},
    {"account_id": "ACC-102", "name": "Beth Lin", "title": "Procurement Lead", "role": "procurement", "last_touch": "2026-09-14"},
    {"account_id": "ACC-103", "name": "Greg Sandoval", "title": "CIO", "role": "economic buyer", "last_touch": "2026-11-10"},
    {"account_id": "ACC-103", "name": "Tess Albright", "title": "VP Member Experience", "role": "champion", "last_touch": "2026-11-20"},
],
"deals": [
    {"account_id": "ACC-101", "deal_id": "D-7781", "name": "Contact center modernisation", "stage": "Discovery",
     "amount_usd": 410000, "close_date": "2027-03-31", "next_step": "First-call workshop with VP Ops"},
    {"account_id": "ACC-102", "deal_id": "D-7802", "name": "Patient access platform", "stage": "Qualification",
     "amount_usd": 780000, "close_date": "2027-02-28", "next_step": "Proposal to COO"},
    {"account_id": "ACC-103", "deal_id": "D-7815", "name": "Cloud phone migration", "stage": "Discovery",
     "amount_usd": 160000, "close_date": "2027-01-15", "next_step": "Present migration plan to CIO"},
]}

S = "https://news.example.org"; J = "https://jobs.example.org"; T = "https://stackwatch.example.org"
index = [
    {"type": "news", "url": f"{S}/halvorsen-acquires-prairie-line", "date": "2026-10-02", "title": "Halvorsen Freight Group acquires Prairie Line Couriers",
     "text": "Halvorsen Freight Group has acquired Prairie Line Couriers, adding 14 new sites across Nebraska and Iowa. The company plans to integrate dispatch and customer service by mid-2027."},
    {"type": "news", "url": f"{S}/halvorsen-q3-volume", "date": "2026-11-04", "title": "Halvorsen posts record Q3 volume",
     "text": "Halvorsen Freight Group shipped record volume in Q3, but customers reported long hold times and missed calls at its service desk during the September peak."},
    {"type": "job", "url": f"{J}/halvorsen-seasonal-agents", "date": "2026-11-10", "title": "Seasonal Customer Service Agent (60 openings) - Halvorsen Freight Group",
     "text": "Halvorsen Freight Group is hiring 60 seasonal customer service agents for peak. New agents must ramp within two weeks; high turnover in the role."},
    {"type": "tech", "url": f"{T}/halvorsen-freight-group", "date": "2026-08-15", "title": "Halvorsen Freight Group tech stack",
     "text": "Halvorsen Freight Group runs Northstar CRM for service cases and a legacy on-prem PBX at each depot."},
    {"type": "news", "url": f"{S}/halvorsen-marine-new-store", "date": "2026-11-01", "title": "Halvorsen Marine Supply opens new store",
     "text": "Halvorsen Marine Supply, a boating retailer, opened its fifth store and is hiring sales associates. Expansion continues in 2027."},
    {"type": "news", "url": f"{S}/meridian-new-clinics", "date": "2026-09-22", "title": "Meridian Health Partners to open three clinics",
     "text": "Meridian Health Partners announced three new clinics in 2027 as part of its expansion in central Virginia."},
    {"type": "news", "url": f"{S}/meridian-hold-times", "date": "2026-11-08", "title": "Patients report long waits on Meridian scheduling line",
     "text": "Patients say hold times on the Meridian Health Partners scheduling line often exceed 15 minutes, and many hang up; the abandon rate worries the board."},
    {"type": "job", "url": f"{J}/meridian-compliance-analyst", "date": "2026-10-28", "title": "Compliance Analyst, Call Recording - Meridian Health Partners",
     "text": "Meridian Health Partners seeks a compliance analyst to run HIPAA audit readiness for call recording retention and QA sampling."},
    {"type": "job", "url": f"{J}/meridian-patient-access-rep", "date": "2026-11-15", "title": "Patient Access Representative - Meridian Health Partners",
     "text": "Meridian Health Partners is hiring patient access representatives. Agents use the scheduling system and CRM side by side; screen pop integration is planned."},
    {"type": "tech", "url": f"{T}/meridian-health-partners", "date": "2026-07-30", "title": "Meridian Health Partners tech stack",
     "text": "Meridian Health Partners: hosted contact center, EHR scheduling module, homegrown CRM with no integration to telephony."},
    {"type": "news", "url": f"{S}/quarry-lane-foothill-merger", "date": "2026-10-12", "title": "Quarry Lane Credit Union completes merger with Foothill Federal",
     "text": "Quarry Lane Credit Union completed its merger with Foothill Federal, adding 9 branches. Members will move to one set of systems in 2027."},
    {"type": "news", "url": f"{S}/quarry-lane-pci", "date": "2026-11-02", "title": "Quarry Lane CU passes PCI audit with findings",
     "text": "Quarry Lane Credit Union passed its PCI audit with two findings, including call recording controls for card data. Compliance fixes are due by Q2."},
    {"type": "job", "url": f"{J}/quarry-lane-telecom-engineer", "date": "2026-11-09", "title": "IT Telecom Engineer - Quarry Lane Credit Union",
     "text": "Quarry Lane Credit Union is hiring a telecom engineer to migrate the legacy PBX to the cloud before end of support."},
    {"type": "tech", "url": f"{T}/quarry-lane-credit-union", "date": "2026-06-11", "title": "Quarry Lane Credit Union tech stack",
     "text": "Quarry Lane Credit Union uses Northstar CRM for members, an on-prem PBX, and a core banking platform. CRM integration with phones is listed as a 2027 project."},
]

playbook = {
    "seller": "Voxly", "brand_color": "1F4E79", "accent_color": "E8F0F8",
    "planning_price_per_seat_month_usd": 95,
    "pains": {
        "high_abandon": {"label": "Callers hang up before they reach anyone",
                         "triggers": ["hold time", "wait", "abandon", "missed call", "hang up"],
                         "offer": "Voxly Contact Center", "solution": "Queue callbacks, skills routing and live wallboards",
                         "outcome": "Cut abandoned calls by about 40%",
                         "discovery_q": "What happens to a caller who hangs up during peak today?"},
        "agent_ramp": {"label": "New agents take too long to ramp",
                       "triggers": ["hiring", "seasonal", "ramp", "turnover", "new agents"],
                       "offer": "Voxly Agent Assist", "solution": "Real-time AI prompts and after-call summaries",
                       "outcome": "New agents productive about 10 days sooner",
                       "discovery_q": "How long until a new agent handles calls alone, and who coaches them?"},
        "compliance_recording": {"label": "Call recording does not meet audit rules",
                                 "triggers": ["hipaa", "pci", "audit", "recording", "compliance"],
                                 "offer": "Voxly Compliance Recording", "solution": "Policy-based retention, pause-and-resume, QA sampling",
                                 "outcome": "Audit evidence on demand; about 400 prep hours saved a year",
                                 "discovery_q": "What did the last audit ask for that took the longest to produce?"},
        "legacy_pbx_eol": {"label": "Phone system is old and reaching end of support",
                           "triggers": ["end of support", "legacy pbx", "on-prem pbx", "legacy on-prem"],
                           "offer": "Voxly Cloud Phone", "solution": "Cloud phone system with number porting and staged cut-over",
                           "outcome": "Retire PBX maintenance and hardware refresh",
                           "discovery_q": "When does support end, and what is the hardware refresh quote?"},
        "multi_site": {"label": "New sites or a merger need one phone system",
                       "triggers": ["acquire", "acquisition", "merger", "new sites", "new clinics", "branches", "expansion"],
                       "offer": "Voxly Cloud Phone", "solution": "Site templates and one admin console for every location",
                       "outcome": "Bring a new site live in days, not weeks",
                       "discovery_q": "How many sites must move, and in what order?"},
        "crm_fragmentation": {"label": "Agents swivel between the phone and the CRM",
                              "triggers": ["swivel", "screen pop", "side by side", "no integration", "crm integration"],
                              "offer": "Voxly CRM Connect", "solution": "Screen pop, click-to-dial and auto-logged calls",
                              "outcome": "About 30 seconds saved per call",
                              "discovery_q": "How many screens does an agent touch on a typical call?"},
    },
    "source_weight": {"crm_note": 1.0, "news": 1.2, "job": 1.0, "tech": 0.8},
    "roi_assumptions": {"abandon_reduction": 0.4, "ramp_days_saved": 10, "loaded_agent_cost_per_day_usd": 280,
                        "audit_prep_hours_saved": 400, "compliance_hourly_cost_usd": 85,
                        "site_setup_cost_avoided_usd": 6500, "seconds_saved_per_call": 30,
                        "agent_hourly_cost_usd": 32},
    "timeline": [["Discovery workshop and design", 2], ["Pilot with one team", 4], ["Wave 1 roll-out", 6],
                 ["Remaining sites and hand-over", 6]],
}

# The rep's own read of each account's top three pains (answer key for step 6).
key = {"Halvorsen Freight Group": ["high_abandon", "agent_ramp", "multi_site"],
       "Meridian Health Partners": ["compliance_recording", "high_abandon", "crm_fragmentation"],
       "Quarry Lane Credit Union": ["legacy_pbx_eol", "multi_site", "compliance_recording"]}

# Simulated log of 80 past proposals: 40 freeform (before the Skill) and 40 from the Skill.
SECTIONS = ["exec_summary", "what_we_heard", "pains_solutions_table", "roi", "timeline", "pricing",
            "case_study", "company_overview"]
log = []
for i in range(80):
    skill = i >= 40
    # Skill proposals always carry the Skill's sections; some reps still paste in a case study or overview.
    extra = {"case_study": 0.5, "company_overview": 0.2}
    inc = {s: (random.random() < extra[s] if s in extra else True) if skill else random.random() < 0.55
           for s in SECTIONS}
    inc["pricing"] = True
    p_meet = 0.35 + 0.2 * inc["what_we_heard"] + 0.15 * inc["pains_solutions_table"] - 0.1 * inc["company_overview"]
    p_win = 0.12 + 0.18 * inc["roi"] + 0.12 * inc["pains_solutions_table"] + 0.06 * inc["case_study"] \
        + 0.05 * inc["timeline"] - 0.08 * inc["company_overview"]
    meeting = random.random() < p_meet
    log.append({"proposal_id": f"P-{3000 + i}", "template": "skill" if skill else "freeform",
                "sections": [s for s in SECTIONS if inc[s]],
                "hours_spent": round(random.uniform(0.6, 1.4) if skill else random.uniform(4.5, 8.0), 1),
                "meeting_booked": meeting, "outcome": "won" if meeting and random.random() < p_win / 0.6 else "lost"})

for name, obj in {"crm": crm, "search_index": index, "playbook": playbook, "answer_key": key,
                  "win_loss_log": log,
                  "rep_edits": {"note": "Simulated minutes the rep spent editing each generated proposal before sending.",
                                "Halvorsen Freight Group": {"minutes": 22, "edited": ["exec_summary"], "removed": []},
                                "Meridian Health Partners": {"minutes": 31, "edited": ["exec_summary", "timeline"], "removed": []},
                                "Quarry Lane Credit Union": {"minutes": 18, "edited": [], "removed": ["case_study"]}}}.items():
    (d / f"{name}.json").write_text(json.dumps(obj, indent=2))
print(f"wrote CRM ({len(crm['accounts'])} accounts), {len(index)} search docs, {len(log)} past proposals")
