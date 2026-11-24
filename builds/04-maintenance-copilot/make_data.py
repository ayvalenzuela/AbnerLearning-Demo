"""Generate synthetic manuals, SOPs, CMMS work-order history, sensor/alarm data and past test incidents.

The machines (a filler, a capper and a labeler on a bottling plant's two lines) and every record are fictional.
"""
import csv, json, random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(4)
HERE = Path(__file__).parent
DATA = HERE / "data"
(DATA / "manuals").mkdir(parents=True, exist_ok=True)
NOW = datetime(2026, 11, 24, 6, 10)

# machine -> fault code -> (title, [(cause_id, cause, check/fix steps, sensor sign or "")])
MANUAL = {
    "F-200": {"name": "Rotary filler F-200", "faults": {
        "E14": ("Low fill weight", [
            ("F200-E14-C1", "Product supply pressure low", "Check header gauge reads 2.0-2.5 bar. Inspect supply pump strainer.", "supply_pressure_bar below 2.0"),
            ("F200-E14-C2", "Clogged nozzle screen", "Lock out. Remove nozzle, clean screen in warm caustic, refit.", ""),
            ("F200-E14-C3", "Fill valve seat wear", "Lock out. Inspect valve seat for scoring; replace seat kit FK-14.", ""),
            ("F200-E14-C4", "Load cell calibration drift", "Run calibration with 500 g test weight from the HMI service menu.", "loadcell_zero_g above 5"),
        ]),
        "E22": ("Bowl level high", [
            ("F200-E22-C1", "Level probe fouled", "Clean level probe tip; verify reading against sight glass.", ""),
            ("F200-E22-C2", "Inlet valve stuck open", "Cycle inlet valve from HMI; replace actuator if it does not close.", "inlet_valve_pct above 90"),
        ]),
    }},
    "C-40": {"name": "Capper C-40", "faults": {
        "E31": ("Cap torque low", [
            ("C40-E31-C1", "Clutch slip from worn magnets", "Measure static torque with gauge; replace clutch magnet set.", "torque_nm below 1.6"),
            ("C40-E31-C2", "Chuck insert worn", "Inspect rubber chuck inserts; replace if glazed.", ""),
            ("C40-E31-C3", "Wrong cap lot (liner thickness)", "Check cap lot against spec sheet; quarantine lot if out of spec.", ""),
        ]),
        "E35": ("Cap feed jam", [
            ("C40-E35-C1", "Cap chute misaligned", "Realign chute to the chuck turret with gauge block CG-2.", ""),
            ("C40-E35-C2", "Sorter bowl speed too high", "Reduce sorter speed to 70 percent and observe for 10 minutes.", "sorter_speed_pct above 85"),
        ]),
    }},
    "L-12": {"name": "Labeler L-12", "faults": {
        "E41": ("Label skew", [
            ("L12-E41-C1", "Vacuum drum ports blocked", "Clean drum ports with brush; check vacuum reads above 0.6 bar.", "vacuum_bar below 0.6"),
            ("L12-E41-C2", "Bottle starwheel timing off", "Re-time starwheel with timing pin; verify at slow jog.", ""),
            ("L12-E41-C3", "Glue temperature low", "Check glue roller temperature setpoint 165 C.", "glue_temp_c below 150"),
        ]),
    }},
}
SOPS = [
    ("SOP-LOTO-01", "Lockout/tagout for product-contact parts",
     "Stop the machine from the HMI. Isolate electrical and pneumatic energy, apply personal lock and tag. "
     "Bleed residual air. Verify zero energy by attempting a start. Remove locks only after a sanitation check."),
    ("SOP-SAN-03", "Sanitation after opening product-contact parts",
     "After any nozzle, valve or bowl work: CIP rinse, sanitize with approved chemical, swab test before restart. "
     "Record the swab result on the work order."),
]

lines = []
for mid, m in MANUAL.items():
    md = [f"# {m['name']} ({mid}) - Service manual (fictional)", ""]
    for code, (title, causes) in m["faults"].items():
        md += [f"## {mid} / {code} - {title}", f"Alarm {code} on the {mid} means: {title.lower()}.",
               "Likely causes, in the order the manufacturer recommends checking them:"]
        for i, (cid, cause, steps, sign) in enumerate(causes, 1):
            md.append(f"{i}. [{cid}] {cause}. Steps: {steps}" + (f" Sensor sign: {sign}." if sign else ""))
        md.append("")
    (DATA / "manuals" / f"{mid}.md").write_text("\n".join(md))
(DATA / "manuals" / "SOPs.md").write_text("\n".join(
    f"## {sid} - {title}\n{body}\n" for sid, title, body in SOPS))

# CMMS work-order history (seed for the SQLite store behind the MCP server)
SYMPTOMS = {
    "F200-E14-C1": ["fill weights low across all nozzles, pump sounding rough", "all heads underfilling after product changeover"],
    "F200-E14-C2": ["fill weight low on a few nozzles, slow fill", "nozzle 6 slow to fill, weight low", "two nozzles underfilling after a long run"],
    "F200-E14-C3": ["one head underfilling intermittently, valve sounds hard"],
    "F200-E14-C4": ["weights read low but bottles look full, check-weigher disagrees"],
    "F200-E22-C1": ["bowl level alarm with level looking normal in sight glass"],
    "F200-E22-C2": ["bowl overfilling, inlet valve not closing"],
    "C40-E31-C1": ["caps loose on torque audit, all heads", "torque low on every head after a long shift"],
    "C40-E31-C2": ["one head leaving caps loose, chuck glazed"],
    "C40-E31-C3": ["caps loose on new cap lot only"],
    "C40-E35-C1": ["caps jamming at chute exit after changeover"],
    "C40-E35-C2": ["caps flipping in the chute, jams every few minutes"],
    "L12-E41-C1": ["labels skewed on the leading edge, vacuum low"],
    "L12-E41-C2": ["labels skewed and wrinkled at the overlap after a jam"],
    "L12-E41-C3": ["labels sliding, glue looks thin"],
}
CAUSE_TEXT = {cid: cause for m in MANUAL.values() for _, (_, cs) in m["faults"].items() for cid, cause, _, _ in cs}
STEPS = {cid: steps for m in MANUAL.values() for _, (_, cs) in m["faults"].items() for cid, _, steps, _ in cs}
TECHS = ["R. Alvarez", "K. Osei", "M. Novak", "S. Tanaka"]
weights = {"F200-E14-C2": 3, "F200-E14-C1": 1, "F200-E14-C3": 1, "C40-E31-C1": 3, "C40-E31-C2": 1, "C40-E35-C2": 2,
           "L12-E41-C1": 3, "L12-E41-C3": 1, "F200-E22-C1": 1, "C40-E35-C1": 1, "C40-E31-C3": 1, "F200-E14-C4": 1,
           "L12-E41-C2": 1, "F200-E22-C2": 1}
orders = []
for cid, n in weights.items():
    for _ in range(n):
        mid = {"F200": "F-200", "C40": "C-40", "L12": "L-12"}[cid.split("-")[0]]
        ftf = random.random() < 0.7
        orders.append({"machine_id": mid, "line": random.choice(["Line 1", "Line 2"]), "fault_code": cid.split("-")[1],
                       "opened": (NOW - timedelta(days=random.randint(10, 400), hours=random.randint(0, 23))).isoformat(timespec="minutes"),
                       "symptom": random.choice(SYMPTOMS[cid]), "root_cause_id": cid, "root_cause": CAUSE_TEXT[cid],
                       "fix_steps": STEPS[cid], "parts": [], "minutes_down": random.randint(35, 80) + (0 if ftf else 45),
                       "first_time_fix": ftf, "technician": random.choice(TECHS)})
# two repeat failures: same line, same fault, within 14 days of a fix that did not hold
for base_i in (0, 9):
    b = orders[base_i]
    rep = dict(b, opened=(datetime.fromisoformat(b["opened"]) + timedelta(days=6)).isoformat(timespec="minutes"),
               first_time_fix=False, minutes_down=b["minutes_down"] + 30, symptom=b["symptom"] + " (again)")
    orders.append(rep)
orders.sort(key=lambda o: o["opened"])
for i, o in enumerate(orders, 1):
    o["wo_id"] = f"WO-{24000 + i}"
(DATA / "cmms_seed.json").write_text(json.dumps(orders, indent=2))

# Live alarm and sensor snapshot for the plant this morning
alarms = [("2026-11-24T06:08", "F-200", "Line 2", "E14"), ("2026-11-23T22:41", "C-40", "Line 1", "E35")]
with open(DATA / "alarms.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["timestamp", "machine_id", "line", "code"]); w.writerows(alarms)
sensors = []
for minute in range(0, 30, 5):
    t = (NOW - timedelta(minutes=30 - minute)).isoformat(timespec="minutes")
    for line in ("Line 1", "Line 2"):
        sensors += [(t, "F-200", line, "supply_pressure_bar", round(random.uniform(2.1, 2.4), 2)),
                    (t, "F-200", line, "loadcell_zero_g", round(random.uniform(-1.5, 1.5), 1)),
                    (t, "F-200", line, "inlet_valve_pct", random.randint(30, 60))]
with open(DATA / "sensors.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["timestamp", "machine_id", "line", "tag", "value"]); w.writerows(sensors)

# Past incidents with a technician-confirmed root cause, held out of the seed history, for replay testing.
# Two of them were the new O-ring problem that the manual does not cover.
TESTS = [
    ("F-200", "Line 1", "E14", "nozzle 4 slow to fill and underweight", "F200-E14-C2", 40),
    ("F-200", "Line 2", "E14", "every head underfilling, pump noisy", "F200-E14-C1", 35),
    ("F-200", "Line 1", "E14", "nozzle 2 dripping after the fill, weight low", "NEW-ORING", 45),
    ("F-200", "Line 2", "E14", "product dripping from nozzle 7 after fill, underweight", "NEW-ORING", 45),
    ("C-40", "Line 1", "E31", "caps loose on all heads at torque audit", "C40-E31-C1", 50),
    ("C-40", "Line 2", "E31", "loose caps on new cap lot only", "C40-E31-C3", 30),
    ("L-12", "Line 1", "E41", "labels skewed at leading edge, vacuum reading low", "L12-E41-C1", 30),
    ("C-40", "Line 2", "E35", "caps flipping in chute and jamming", "C40-E35-C2", 25),
]
# Sensor readings recorded at the time of each past incident (where the historian had them)
SNAP = {1: {"supply_pressure_bar": 2.3}, 2: {"supply_pressure_bar": 1.7}, 5: {"torque_nm": 1.3}, 7: {"vacuum_bar": 0.45}}
(DATA / "test_incidents.json").write_text(json.dumps(
    [{"incident_id": f"INC-{i + 1:02d}", "machine_id": m, "line": l, "fault_code": c, "description": d,
      "confirmed_cause_id": cc, "repair_minutes": r, "sensors_at_incident": SNAP.get(i + 1, {})}
     for i, (m, l, c, d, cc, r) in enumerate(TESTS)], indent=2))

# What the technician found this morning (used to simulate the human step)
(DATA / "tech_finding.json").write_text(json.dumps({
    "tried_first": "F200-E14-C2",
    "root_cause_id": "NEW-ORING",
    "root_cause": "Nozzle valve O-ring swollen (EPDM O-rings attacked by the new peracetic sanitizer; FKM required)",
    "fix_steps": "Lock out per SOP-LOTO-01. Replace nozzle valve O-rings with FKM part OR-22-FKM on all heads. "
                 "Sanitize per SOP-SAN-03 and swab before restart.",
    "parts": ["OR-22-FKM x12"], "minutes_down": 95, "first_time_fix": False, "technician": "K. Osei"}, indent=2))

(DATA / "baseline.json").write_text(json.dumps({
    "manual_search_minutes": 30, "copilot_search_minutes": 5, "minutes_per_cause_checked": 20,
    "escalation_minutes_if_not_in_manual": 60}, indent=2))
print(f"Wrote {len(MANUAL)} manuals, {len(SOPS)} SOPs, {len(orders)} work orders, {len(TESTS)} test incidents -> {DATA}")
