"""Generate 8 synthetic first-notice-of-loss (FNOL) packets: a typed police report (PNG + PDF, plus the
OCR text layer a scanner would produce), a damage photo, and an adjuster's phone note. Also policies,
prior claims, and a hand-labelled answer key. All people, vehicles and policies are fictional."""
import json, random
from datetime import date, timedelta
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

random.seed(9)
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # no I, O, Q
TRANSLIT = {**{str(d): d for d in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))),
            "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def vin_check_digit(vin: str) -> str:
    r = sum(TRANSLIT[c] * w for c, w in zip(vin, WEIGHTS)) % 11
    return "X" if r == 10 else str(r)


def make_vin() -> str:
    v = list(random.choice(VIN_CHARS) for _ in range(17))
    v[9] = random.choice("NPRS")  # model-year code
    v[8] = vin_check_digit("".join(v))
    return "".join(v)


LOSS = date(2026, 11, 16)
CARS = [("2021", "Toyota", "Corolla", 19500), ("2017", "Honda", "Civic", 12500), ("2022", "Ford", "Escape", 26000),
        ("2019", "Subaru", "Outback", 21000), ("2020", "Hyundai", "Elantra", 16000), ("2018", "Mazda", "CX-5", 18500),
        ("2023", "Kia", "Telluride", 41000), ("2016", "Chevrolet", "Malibu", 11000)]
PEOPLE = ["Jordan Reyes", "Priya Natarajan", "Marcus Webb", "Hannah Kowalski", "Diego Alvarez", "Aisha Coleman",
          "Tom Lindqvist", "Grace Okafor"]
PLACES = ["Elm St & 4th Ave, Riverton", "I-35 mile 112 southbound", "Lakeview Mall parking lot, Riverton",
          "Hwy 9 at Miller Rd, Ashford", "Oak Blvd & Pine St, Riverton", "Grand Ave near Kroll Park, Ashford",
          "Route 30 at Cedar Creek bridge", "Maple Dr driveway, 1180 Maple Dr, Ashford"]
# scenario per claim: severity, estimate, and what goes wrong (the answer key records the truth)
SCEN = [
    {"sev": "minor", "amount": 2400},
    {"sev": "moderate", "amount": 11800},                     # amount ~94% of an old car's value
    {"sev": "minor", "amount": 1900, "ocr_vin_error": True},  # scanner misreads one VIN character
    {"sev": "moderate", "amount": 6200, "date_conflict": True},  # caller gives the wrong day
    {"sev": "moderate", "amount": 5400, "new_policy": True},  # loss 12 days after the policy started
    {"sev": "minor", "amount": 2100, "dup_vin": True},        # same VIN claimed 4 months ago
    {"sev": "severe", "amount": 14000, "injuries": True},
    {"sev": "minor", "amount": None, "lapsed": True},         # caller gave no amount; policy lapsed
]
DAMAGE_FRAC = {"minor": (0.015, 0.03), "moderate": (0.06, 0.10), "severe": (0.18, 0.26)}

root = Path("data"); pk = root / "packets"; pk.mkdir(parents=True, exist_ok=True)
try:
    FONT = ImageFont.truetype("DejaVuSansMono.ttf", 18); BIG = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
except OSError:
    FONT = BIG = ImageFont.load_default()

policies, history, key, meta = [], [], {}, []
for i, sc in enumerate(SCEN):
    cid = f"CLM-{5001 + i}"
    year, make, model, value = CARS[i]
    vin, name, place = make_vin(), PEOPLE[i], PLACES[i]
    pol = f"PA-{random.randint(100000, 999999)}"
    start = LOSS - timedelta(days=12 if sc.get("new_policy") else random.randint(120, 700))
    end = LOSS - timedelta(days=9) if sc.get("lapsed") else start + timedelta(days=365 * 2)
    policies.append({"policy_number": pol, "holder": name, "start": str(start), "end": str(end),
                     "status": "lapsed" if sc.get("lapsed") else "active", "coverages": ["liability", "collision"],
                     "deductible": 500, "vehicle": {"year": year, "make": make, "model": model, "vin": vin},
                     "vehicle_value_usd": value})
    if sc.get("dup_vin"):
        history.append({"claim_id": "CLM-4112", "vin": vin, "loss_date": str(LOSS - timedelta(days=121)),
                        "amount_usd": 2300, "status": "paid"})
    phone = f"555-01{random.randint(10, 99)}"
    report_no = f"RPD-26-{random.randint(10000, 99999)}"
    injuries = bool(sc.get("injuries"))
    fields = {"REPORT NO": report_no, "DATE OF INCIDENT": LOSS.strftime("%m/%d/%Y"),
              "LOCATION": place, "DRIVER NAME": name, "INSURANCE POLICY": pol,
              "VEHICLE": f"{year} {make} {model}", "VIN": vin, "INJURIES": "YES" if injuries else "NONE REPORTED"}
    narrative = ("Vehicle 1 was struck while " + random.choice(
        ["stopped at a red light", "merging", "parked", "turning left"]) + ". Driver cooperative.")

    # police report image (what the adjuster receives) and its PDF version
    img = Image.new("RGB", (900, 620), "white"); d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 880, 600], outline="black", width=2)
    d.text((40, 36), "RIVERTON POLICE DEPT - TRAFFIC COLLISION REPORT", font=BIG, fill="black")
    for n, (k, v) in enumerate(fields.items()):
        d.text((40, 100 + n * 48), f"{k + ':':<19}{v}", font=FONT, fill="black")
        d.line([40, 124 + n * 48, 860, 124 + n * 48], fill=(200, 200, 200))
    d.text((40, 500), "NARRATIVE: " + narrative, font=FONT, fill="black")
    d.text((40, 556), "Officer badge 4471 - synthetic document for a demo", font=FONT, fill=(120, 120, 120))
    cdir = pk / cid; cdir.mkdir(exist_ok=True)
    img.save(cdir / "police_report.png"); img.save(cdir / "police_report.pdf", "PDF", resolution=100)

    # OCR text layer, as a scanner would output it (with one realistic misread on claim 3)
    ocr = dict(fields)
    if sc.get("ocr_vin_error"):
        SWAP = {"5": "S", "8": "B", "0": "D", "2": "Z", "6": "G"}
        pos = next(p for p in range(10, 17) if vin[p] in SWAP)
        bad = vin[:pos] + SWAP[vin[pos]] + vin[pos + 1:]
        assert vin_check_digit(bad) != bad[8]
        ocr["VIN"] = bad
    (cdir / "police_report.txt").write_text("\n".join(f"{k}: {v}" for k, v in ocr.items()) + f"\nNARRATIVE: {narrative}\n")

    # damage photo: a simple car with a red damage area whose size sets the severity
    ph = Image.new("RGB", (640, 400), (225, 228, 232)); g = ImageDraw.Draw(ph)
    g.rounded_rectangle([70, 170, 570, 300], radius=40, fill=(70, 100, 140))
    g.polygon([(170, 170), (230, 100), (420, 100), (490, 170)], fill=(70, 100, 140))
    g.polygon([(190, 166), (240, 112), (320, 112), (320, 166)], fill=(190, 215, 235))
    g.polygon([(332, 166), (332, 112), (410, 112), (465, 166)], fill=(190, 215, 235))
    for x in (160, 470):
        g.ellipse([x - 42, 262, x + 42, 346], fill=(30, 30, 30)); g.ellipse([x - 18, 286, x + 18, 322], fill=(150, 150, 150))
    px = ph.get_flattened_data() if hasattr(ph, "get_flattened_data") else ph.getdata()
    body = sum(1 for p in px if p != (225, 228, 232))
    frac = random.uniform(*DAMAGE_FRAC[sc["sev"]])
    area = frac * body
    rx = (area / 3.1416 / 0.6) ** 0.5; ry = rx * 0.6
    cx, cy = random.choice([(200, 230), (440, 225), (320, 215)])
    g.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(205, 35, 40))
    ph.save(cdir / "damage_photo.png")

    # adjuster's phone note (free text, typed during the first call)
    said_date = (LOSS - timedelta(days=1)) if sc.get("date_conflict") else LOSS
    amt = f"Body shop guessed about ${sc['amount']:,}." if sc["amount"] else "No estimate yet."
    hurt = "Passenger has neck pain, went to urgent care." if injuries else "Nobody hurt."
    (cdir / "phone_note.txt").write_text(
        f"FNOL call {said_date.month}/{said_date.day + 1} 9:{random.randint(10, 59)}am. Caller {name}, policy {pol}. "
        f"Says it happened {said_date.month}/{said_date.day} at {place.split(',')[0]}. {narrative} {amt} {hurt} "
        f"Callback {phone}. Police report {report_no} filed.\n")

    truth_route = ("special_unit" if any(sc.get(k) for k in ("new_policy", "dup_vin")) or (sc["amount"] or 0) > 0.8 * value
                   else "adjuster" if sc["sev"] != "minor" or injuries or sc.get("lapsed") else "fast_track")
    key[cid] = {"policy_number": pol, "claimant_name": name, "phone": phone, "loss_date": str(LOSS),
                "loss_location": place, "police_report_number": report_no, "vin": vin, "vehicle_year": year,
                "vehicle_make": make, "vehicle_model": model, "injuries": "yes" if injuries else "no",
                "estimated_amount_usd": str(sc["amount"]) if sc["amount"] else None,
                "damage_severity": sc["sev"], "route": truth_route}
    meta.append({"claim_id": cid, "received_at": f"2026-11-17T{7 + i // 3:02d}:{(i * 17) % 60:02d}",
                 "files": ["police_report.png", "police_report.pdf", "police_report.txt", "damage_photo.png", "phone_note.txt"]})

# Answer key for the estimate on claim 8: the caller gave none, the adjuster gets it on the callback.
key["CLM-5008"]["estimated_amount_usd"] = "3100"
(root / "policies.json").write_text(json.dumps(policies, indent=2))
(root / "claims_history.json").write_text(json.dumps(history, indent=2))
(root / "answer_key.json").write_text(json.dumps(key, indent=2))
(root / "packets.json").write_text(json.dumps(meta, indent=2))
(root / "baseline.json").write_text(json.dumps({
    "manual_retype_minutes_per_claim": 32, "intake_clerks": 1, "clerk_day_starts": "2026-11-17T08:00",
    "review_minutes_per_field": 0.75, "review_overhead_minutes_per_claim": 1.0,
    "auto_acknowledgement_minutes": 5,
    "note": "Retype minutes are an adjuster-team estimate; review minutes are a planning assumption."}, indent=2))
print(f"wrote {len(meta)} claim packets to {pk}")
