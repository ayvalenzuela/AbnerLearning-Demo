"""Generate synthetic payer policies, prior-auth requests and a hand-labelled answer key.

Everything here is fictional: the payers, patients, clinicians and notes are made up.
CPT codes are the public procedure codes; no real PHI is used.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
(DATA / "policies").mkdir(parents=True, exist_ok=True)

PROCEDURES = {
    "72148": "Lumbar spine MRI without contrast",
    "27447": "Total knee arthroplasty (knee replacement)",
    "95810": "Attended polysomnography (in-lab sleep study)",
    "43644": "Laparoscopic gastric bypass (bariatric surgery)",
}

# Each criterion: (text shown in the policy, offline test used only by the rule-based stand-in).
# Test types: weeks (duration >= min, months converted), value (number after a label vs a bound), any (term present).
W = lambda terms, n: {"type": "weeks", "terms": terms, "min": n}
V = lambda label, op, n: {"type": "value", "label": label, "op": op, "bound": n}
A = lambda terms: {"type": "any", "terms": terms}

PAIN = ["back pain"]
CONS = ["physical therapy", "nsaid", "conservative"]
NEURO = A(["radiculopathy", "straight leg raise", "diminished", "weakness", "numbness"])
TKA_TX = ["physical therapy", "injection", "nsaid"]
ADL = A(["difficulty", "unable to", "limits"])
SNORE = A(["witnessed apnea", "snoring", "apneic episodes"])
HST = A(["home sleep test was non-diagnostic", "not a candidate for home", "copd", "heart failure"])
WLOSS = ["weight management program", "weight loss program"]
PSYCH = A(["psychological evaluation", "psych eval"])
NUTR = A(["dietitian", "nutrition consult"])

POLICIES = {
    "RHP": {
        "name": "Ridgeway Health Plan",
        "72148": [("Low back pain persisting for at least 6 weeks.", W(PAIN, 6)),
                  ("At least 6 weeks of conservative therapy (physical therapy or NSAIDs).", W(CONS, 6)),
                  ("Neurological deficit or radiculopathy documented on exam.", NEURO)],
        "27447": [("Radiographic advanced osteoarthritis, Kellgren-Lawrence grade 3 or 4.", V("kellgren-lawrence grade", ">=", 3)),
                  ("At least 12 weeks of non-surgical treatment.", W(TKA_TX, 12)),
                  ("Functional limitation in activities of daily living.", ADL),
                  ("Body mass index below 40.", V("bmi", "<", 40))],
        "95810": [("Epworth Sleepiness Scale score of 10 or higher.", V("epworth", ">=", 10)),
                  ("Witnessed apneas or loud habitual snoring.", SNORE),
                  ("Home sleep apnea test is non-diagnostic or clinically inappropriate.", HST)],
        "43644": [("Body mass index of 40 or higher.", V("bmi", ">=", 40)),
                  ("Supervised weight management program for at least 6 months.", W(WLOSS, 26)),
                  ("Pre-operative psychological evaluation completed.", PSYCH),
                  ("Nutrition consult with a registered dietitian.", NUTR)],
    },
    "CMM": {
        "name": "Cascade Mutual",
        "72148": [("Low back pain persisting for at least 4 weeks.", W(PAIN, 4)),
                  ("At least 4 weeks of supervised physical therapy.", W(["physical therapy"], 4)),
                  ("Neurological deficit or radiculopathy documented on exam.", NEURO),
                  ("Plain radiographs (X-ray) of the lumbar spine completed.", A(["x-ray", "radiograph"]))],
        "27447": [("Radiographic advanced osteoarthritis, Kellgren-Lawrence grade 3 or 4.", V("kellgren-lawrence grade", ">=", 3)),
                  ("At least 12 weeks of non-surgical treatment.", W(TKA_TX, 12)),
                  ("Body mass index below 40.", V("bmi", "<", 40))],
        "95810": [("Epworth Sleepiness Scale score of 12 or higher.", V("epworth", ">=", 12)),
                  ("Witnessed apneas or loud habitual snoring.", SNORE),
                  ("Home sleep apnea test is non-diagnostic or clinically inappropriate.", HST)],
        "43644": [("Body mass index of 40 or higher.", V("bmi", ">=", 40)),
                  ("Supervised weight management program for at least 6 months.", W(WLOSS, 26)),
                  ("Pre-operative psychological evaluation completed.", PSYCH)],
    },
    "LCA": {
        "name": "Lakeshore Care Alliance",
        "72148": [("Low back pain persisting for at least 6 weeks.", W(PAIN, 6)),
                  ("At least 6 weeks of conservative therapy (physical therapy or NSAIDs).", W(CONS, 6)),
                  ("Neurological deficit or radiculopathy documented on exam.", NEURO)],
        "27447": [("Radiographic advanced osteoarthritis, Kellgren-Lawrence grade 3 or 4.", V("kellgren-lawrence grade", ">=", 3)),
                  ("At least 12 weeks of non-surgical treatment.", W(TKA_TX, 12)),
                  ("Functional limitation in activities of daily living.", ADL),
                  ("Body mass index below 40.", V("bmi", "<", 40)),
                  ("Documented tobacco-free status (non-smoker or quit at least 4 weeks prior).",
                   A(["non-smoker", "never smoker", "quit smoking", "does not smoke"]))],
        "95810": [("Epworth Sleepiness Scale score of 10 or higher.", V("epworth", ">=", 10)),
                  ("Witnessed apneas or loud habitual snoring.", SNORE)],
        "43644": [("Body mass index of 40 or higher.", V("bmi", ">=", 40)),
                  ("Supervised weight management program for at least 6 months.", W(WLOSS, 26)),
                  ("Pre-operative psychological evaluation completed.", PSYCH),
                  ("Nutrition consult with a registered dietitian.", NUTR)],
    },
}

GENERAL = [
    ("1.1", "Eligibility and member verification",
     "Verify active coverage on the date of service. Requests for members with lapsed coverage are returned without review."),
    ("1.2", "Submission requirements",
     "Each request must include the ordering clinician, CPT code, ICD-10 diagnosis, and chart notes supporting every criterion. "
     "Incomplete requests are denied and must be resubmitted."),
    ("1.3", "Turnaround and appeals",
     "Standard requests are decided within 14 calendar days. Denials may be appealed within 60 days with additional documentation."),
]

offline_tests = {}
for code, p in POLICIES.items():
    lines = [f"# {p['name']} - Medical Policy Manual (fictional)", ""]
    for num, title, body in GENERAL:
        lines += [f"## Section {num} - {title}", body, ""]
    for i, (cpt, proc) in enumerate(PROCEDURES.items(), start=1):
        lines += [f"## Section 4.{i} - {proc} (CPT {cpt})",
                  f"{p['name']} considers {proc.lower()} medically necessary when ALL of the following are documented:"]
        for j, (text, test) in enumerate(p[cpt], start=1):
            cid = f"{code}-{cpt}-{j}"
            lines.append(f"- [{cid}] {text}")
            offline_tests[cid] = test
        lines.append("")
    (DATA / "policies" / f"{code}.md").write_text("\n".join(lines))

# Six fictional requests. Notes are written the way clinicians write, so some evidence is phrased
# in ways a keyword rule misses (REQ-104: "stops breathing" rather than "witnessed apnea").
REQUESTS = [
    {"request_id": "REQ-101", "payer": "RHP", "cpt": "72148", "patient": "Patient A (fictional, 52F)",
     "diagnosis": "M54.16 Radiculopathy, lumbar region", "clinician": "Dr. Lena Ortiz (fictional)",
     "notes": [
         {"title": "PCP visit 2026-08-04", "text": "Patient reports low back pain for 9 weeks radiating to the left leg. "
          "Started naproxen (NSAID) and referred to physical therapy."},
         {"title": "PT discharge summary 2026-09-22", "text": "Completed 7 weeks of physical therapy with minimal relief. "
          "Pain still 7/10 with sitting."},
         {"title": "Spine clinic 2026-10-01", "text": "Exam shows positive straight leg raise on the left and diminished left ankle reflex. "
          "Concern for L5-S1 disc herniation; MRI requested."}]},
    {"request_id": "REQ-102", "payer": "CMM", "cpt": "72148", "patient": "Patient B (fictional, 44M)",
     "diagnosis": "M54.50 Low back pain, unspecified", "clinician": "Dr. Sam Whitfield (fictional)",
     "notes": [
         {"title": "Urgent care 2026-09-02", "text": "Acute low back pain after lifting, present for 5 weeks. "
          "Lumbar x-ray shows mild degenerative change, no fracture."},
         {"title": "PT progress note 2026-10-03", "text": "Patient has attended 3 weeks of physical therapy, two visits per week."},
         {"title": "Ortho visit 2026-10-06", "text": "Numbness over the right lateral foot and mild weakness of great toe extension."}]},
    {"request_id": "REQ-103", "payer": "LCA", "cpt": "27447", "patient": "Patient C (fictional, 67F)",
     "diagnosis": "M17.11 Primary osteoarthritis, right knee", "clinician": "Dr. Priya Raman (fictional)",
     "notes": [
         {"title": "Ortho consult 2026-07-15", "text": "Standing films: Kellgren-Lawrence grade 4 changes, right knee, bone-on-bone medial compartment. "
          "BMI 33.8."},
         {"title": "Ortho follow-up 2026-10-20", "text": "Has tried 16 weeks of physical therapy, two steroid injection treatments and daily NSAID use. "
          "Has difficulty climbing stairs and is unable to walk more than one block."}]},
    {"request_id": "REQ-104", "payer": "RHP", "cpt": "95810", "patient": "Patient D (fictional, 58M)",
     "diagnosis": "G47.33 Obstructive sleep apnea (suspected)", "clinician": "Dr. Omar Haddad (fictional)",
     "notes": [
         {"title": "Sleep clinic intake 2026-09-12", "text": "Epworth Sleepiness Scale 15. Bed partner reports he stops breathing during sleep several times a night."},
         {"title": "Cardiology note 2026-08-30", "text": "History of congestive heart failure, EF 35 percent. Home testing not advised."}]},
    {"request_id": "REQ-105", "payer": "CMM", "cpt": "95810", "patient": "Patient E (fictional, 39F)",
     "diagnosis": "R06.83 Snoring", "clinician": "Dr. Grace Lin (fictional)",
     "notes": [
         {"title": "PCP visit 2026-10-02", "text": "Loud snoring for years, daytime fatigue. Epworth score 11."},
         {"title": "Sleep medicine 2026-10-18", "text": "Home sleep test was non-diagnostic due to poor signal quality."}]},
    {"request_id": "REQ-106", "payer": "LCA", "cpt": "43644", "patient": "Patient F (fictional, 46F)",
     "diagnosis": "E66.01 Morbid obesity due to excess calories", "clinician": "Dr. Ben Adeyemi (fictional)",
     "notes": [
         {"title": "Bariatric intake 2026-04-10", "text": "BMI 43.1. Enrolled in a supervised weight management program."},
         {"title": "Bariatric follow-up 2026-10-15", "text": "Completed 7 months in the weight management program with monthly visits. "
          "Psychological evaluation completed 2026-09-30, cleared for surgery."},
         {"title": "Dietitian note 2026-10-01", "text": "Nutrition consult completed with registered dietitian; post-op diet reviewed."}]},
]
(DATA / "requests.json").write_text(json.dumps(REQUESTS, indent=2))
(DATA / "offline_rules.json").write_text(json.dumps(offline_tests, indent=2))

# Hand-labelled answer key: what an experienced prior-auth nurse decided for each criterion.
KEY = {
    "REQ-101": {"RHP-72148-1": "MET", "RHP-72148-2": "MET", "RHP-72148-3": "MET"},
    "REQ-102": {"CMM-72148-1": "MET", "CMM-72148-2": "NOT MET", "CMM-72148-3": "MET", "CMM-72148-4": "MET"},
    "REQ-103": {"LCA-27447-1": "MET", "LCA-27447-2": "MET", "LCA-27447-3": "MET", "LCA-27447-4": "MET",
                "LCA-27447-5": "MISSING"},
    "REQ-104": {"RHP-95810-1": "MET", "RHP-95810-2": "MET", "RHP-95810-3": "MET"},
    "REQ-105": {"CMM-95810-1": "NOT MET", "CMM-95810-2": "MET", "CMM-95810-3": "MET"},
    "REQ-106": {"LCA-43644-1": "MET", "LCA-43644-2": "MET", "LCA-43644-3": "MET", "LCA-43644-4": "MET"},
}
(DATA / "answer_key.json").write_text(json.dumps(KEY, indent=2))

# What staff added to letters during review (simulated). Status corrections come from the answer key.
STAFF_LETTER_EDITS = {
    "REQ-101": "Imaging will guide a possible epidural steroid injection versus surgical referral.",
    "REQ-104": "- Witnessed apneas or loud habitual snoring. Chart (Sleep clinic intake 2026-09-12): \"Bed partner reports he stops breathing during sleep several times a night.\"",
    "REQ-106": "The patient has a confirmed surgery date pending authorization.",
}
(DATA / "staff_letter_edits.json").write_text(json.dumps(STAFF_LETTER_EDITS, indent=2))

# Baseline from a (synthetic) time study of the manual process.
(DATA / "baseline.json").write_text(json.dumps({
    "manual_hours_per_request": 2.4,
    "review_minutes_base": 12,
    "review_minutes_per_edit": 4,
}, indent=2))

print(f"Wrote 3 payer policies, {len(REQUESTS)} requests, {len(offline_tests)} criteria, answer key -> {DATA}")
