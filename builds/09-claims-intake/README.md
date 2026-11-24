# Build 09 · Insurance — Claims intake and extraction

**Pattern:** Vision + workflow · **Claude features:** vision (PDF document blocks + images), structured output with a confidence per field

## 1 · Situation
A regional auto insurer takes about 300 first notices of loss a week. Each arrives as photos, a police report and a phone note, and an adjuster retypes it all into the claims system before anyone triages it.

## 2 · Constraints
- Nothing reaches the claims system unless every field is confident or a person has checked it.
- Coverage and fraud rules stay in plain code, so auditors can read every rule.
- Claimant data stays inside the insurer's tenant. Every person, vehicle and policy here is fictional.

## 3 · Architecture
```
FNOL packet (police report PDF, damage photo, phone note) -> n8n webhook
   -> Claude vision: claims schema + confidence per field
   -> coverage + fraud rules (code) -> severity routing (fast-track / adjuster / special unit)
   -> IF any field < 0.80: human review queue, else: claims system API
```
`outputs/n8n_workflow.json` is the same flow as an n8n workflow (webhook, Code, HTTP Request to the Claude API, Code to parse the extraction, HTTP Request to the claims system's coverage and fraud rules check, IF on confidence, then create the claim with its route or send it to the review queue). Import it with n8n's "Import from file" and add an `x-api-key` header credential.

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 8 claim packets, policies, prior claims, answer key
python pipeline.py       # runs all 6 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**: the stand-in parses the police report's OCR text layer and the phone note with regular expressions, checks the VIN check digit, and measures the red damage area in the photo with Pillow. Set `ANTHROPIC_API_KEY` to send the PDF and photo to Claude instead (`common/vision_extract.py`).

| Step | What happens | Code |
|---|---|---|
| 1 | Gather the packet: police report (PNG + PDF), damage photo, phone note | `data/packets/` |
| 2 | Extract the claims schema with a confidence per field; conflicts and failed checks lower confidence | `ClaimExtraction` in `pipeline.py` |
| 3 | Coverage and fraud rules: policy active on loss date, VIN on policy, new policy, estimate vs value, duplicate VIN | `check_and_route()` |
| 4 | Route by severity: fast-track, adjuster or special investigations unit | `check_and_route()` |
| 5 | Fields under 0.80 go to a person; the claim is re-checked, then saved | `outputs/review_queue.json`, `outputs/claims_saved.json` |
| 6 | Field and routing accuracy scored against a supervisor's answer key | `data/answer_key.json` |

## 5 · Results (offline run on synthetic data)
- Intake time: **32 minutes of retyping → 0.7 minutes** of human review per claim on average
- Data accuracy: **98.1% straight from extraction → 100% saved**. Both wrong fields (a misread VIN character and a missing estimate) were caught by the confidence bar; 3 of 104 fields went to a person.
- Routing: **7 of 8 right before review → 8 of 8 after**. The bad VIN made one claim look like the wrong vehicle; review fixed it and it moved to fast-track.
- Time to first contact: **122 minutes → 6 minutes** on average (old way: one clerk retyping in arrival order; minutes are estimates in `data/baseline.json`)
- Routes: 2 fast-track, 3 adjuster, 3 special unit (new policy, duplicate VIN, estimate at 94% of vehicle value)

## 6 · Replay
Reuse: "extract with a confidence per field, check with plain rules, send only the doubtful fields to a person" fits any document intake: loan files, invoices, onboarding.
Next time I'd log reviewer edits per field and set a confidence bar per field instead of one bar for all.
