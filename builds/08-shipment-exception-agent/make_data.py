"""Generate a synthetic day of freight: 25 shipments, ~60 GPS/TMS events, and the lookup data
behind the agent's tools (weather, traffic, carrier status, dock schedules). No real companies."""
import json, random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(8)
T0 = datetime(2026, 11, 24, 5, 0)
iso = lambda m: (T0 + timedelta(minutes=round(m))).isoformat(timespec="minutes")

ACCOUNTS = {
    "Cedar Grove Grocers":       {"tone": "friendly", "contact": "Maya Brooks"},
    "Halden Medical Supply":     {"tone": "formal",   "contact": "Dr. Ellen Whitcombe"},
    "Northpine Hardware":        {"tone": "terse",    "contact": "Raj Patel"},
    "Orbit Home Goods":          {"tone": "friendly", "contact": "Sam Ortega"},
    "Ridgeway Auto Parts":       {"tone": "terse",    "contact": "Lena Fox"},
    "Silverline Pharma Distribution": {"tone": "formal", "contact": "Mr. Victor Hale"},
}
TONES = {
    "formal":   {"greeting": "Dear {contact},", "signoff": "Kind regards,\nOperations Desk, Tallgrass Logistics",
                 "max_sentences": 6, "style": "complete sentences, no contractions, apologise once"},
    "friendly": {"greeting": "Hi {first},", "signoff": "Thanks for bearing with us!\nThe Tallgrass ops team",
                 "max_sentences": 5, "style": "warm, plain words, contractions fine"},
    "terse":    {"greeting": "", "signoff": "-- Tallgrass Ops", "max_sentences": 3,
                 "style": "facts only: shipment, cause, new ETA, action"},
}
CARRIERS = ["Apex Freight", "BlueRiver Carriers", "Summit Haul", "Keystone Express"]
LANES = [  # (region the truck crosses, highway corridor, destination DC)
    ("Front Range", "I-25 N", "DC-Denver"), ("Great Plains", "I-80 E", "DC-Omaha"),
    ("Ozarks", "I-44 W", "DC-Tulsa"), ("Twin Cities", "I-94 W", "DC-Minneapolis"),
    ("Lake Michigan", "I-90 E", "DC-Chicago"), ("Ohio Valley", "I-70 E", "DC-Columbus"),
    ("Gulf Coast", "I-10 W", "DC-Houston"), ("Cascades", "I-5 N", "DC-Portland"),
    ("Mojave", "I-15 S", "DC-Las Vegas"), ("Appalachia", "I-81 N", "DC-Roanoke"),
]
# Planned story for the exceptions (the hand-labelled answer key below records the truth).
# Each exception sits on its own lane, so one lane's storm can't leak into another shipment's story.
PLAN = {3: "weather", 7: "weather", 11: "weather_traffic", 5: "traffic", 14: "traffic",
        9: "carrier", 18: "carrier", 12: "dock", 20: "dock", 16: "fuel_stop", 23: "near_miss"}

shipments, events, key = [], [], {}
weather = {r: {"condition": random.choice(["clear", "overcast", "light rain"]), "severity": 0, "est_delay_min": 0}
           for r, _, _ in LANES}
for r in weather:
    if weather[r]["condition"] == "light rain":
        weather[r].update(severity=1, est_delay_min=10)
traffic = {c: {"incident": "none", "incident_type": "none", "est_delay_min": random.choice([0, 5, 10]),
               "alt_route": None, "alt_saving_min": 0} for _, c, _ in LANES}
carrier_status, docks = {}, {}
for _, _, dc in LANES:  # open receiving slots every 30 min, 07:00-22:00, about half already booked
    slots = [m for m in range(120, 1020, 30) if random.random() < 0.5]
    docks[dc] = {"congestion": "normal", "moved": {}, "open_slots": [iso(m) for m in slots]}

for i in range(25):
    sid = f"SHP-{2401 + i}"
    acct = list(ACCOUNTS)[i % len(ACCOUNTS)]
    region, corridor, dc = LANES[i % len(LANES)]
    carrier, truck = CARRIERS[i % 4], f"TRK-{310 + i}"
    depart = random.randint(0, 150)
    miles = random.randint(150, 360)
    slack = random.randint(55, 85)
    window_end = depart + miles / 50 * 60 + slack
    s = {"shipment_id": sid, "account": acct, "carrier": carrier, "truck": truck, "region": region,
         "corridor": corridor, "dest_dc": dc, "miles": miles, "departed": iso(depart),
         "promised_window": [iso(window_end - 120), iso(window_end)]}
    shipments.append(s)
    carrier_status[truck] = {"carrier": carrier, "status": "rolling", "note": "on schedule", "est_delay_min": 0}
    events.append({"ts": iso(depart), "source": "TMS", "type": "departed", "shipment_id": sid,
                   "miles_remaining": miles})
    v1 = random.uniform(49, 56)
    rem1 = miles - v1
    events.append({"ts": iso(depart + 60), "source": "GPS", "type": "ping", "shipment_id": sid,
                   "miles_remaining": round(rem1, 1), "speed_mph": round(v1)})
    story = PLAN.get(i)
    if story is None:
        continue
    t2 = depart + 105
    speed2 = {"weather": 21, "weather_traffic": 19, "traffic": 14, "carrier": 0, "fuel_stop": 15,
              "near_miss": 41, "dock": 52}[story]
    if story != "dock":
        rem2 = rem1 - speed2 * 0.75
        events.append({"ts": iso(t2), "source": "GPS", "type": "ping", "shipment_id": sid,
                       "miles_remaining": round(rem2, 1), "speed_mph": speed2})
    late = story not in ("fuel_stop", "near_miss")
    truth = {"weather": "weather", "weather_traffic": "weather", "traffic": "traffic", "carrier": "carrier",
             "dock": "dock", "fuel_stop": "none", "near_miss": "none"}[story]
    if story in ("weather", "weather_traffic"):
        weather[region] = {"condition": "heavy snow" if region == "Front Range" else "freezing rain",
                           "severity": 3, "est_delay_min": 55}
    if story == "weather_traffic":  # storm also closes lanes, so the traffic feed shows a big delay too
        traffic[corridor] = {"incident": "lane closures, chain law in effect", "incident_type": "weather",
                             "est_delay_min": 70, "alt_route": None, "alt_saving_min": 0}
    if story == "traffic":
        traffic[corridor] = {"incident": "multi-vehicle crash, 2 lanes blocked", "incident_type": "crash",
                             "est_delay_min": 65, "alt_route": f"{corridor} bypass via state route",
                             "alt_saving_min": random.choice([35, 50])}
    if story == "carrier":
        carrier_status[truck] = {"carrier": carrier, "status": "stopped",
                                 "note": random.choice(["tractor breakdown, awaiting road service",
                                                        "driver out of hours, no relay driver"]),
                                 "est_delay_min": 150}
        events.append({"ts": iso(t2 - 10), "source": "TMS", "type": "carrier_update", "shipment_id": sid,
                       "note": "carrier reports unit stopped"})
    if story == "fuel_stop":
        carrier_status[truck] = {"carrier": carrier, "status": "rolling",
                                 "note": "20-minute fuel stop, resumed at full speed", "est_delay_min": 5}
    if story == "dock":
        docks[dc]["congestion"] = "high: 3 doors down for repair"
        moved = window_end + random.choice([70, 85])
        docks[dc]["moved"][sid] = {"original": iso(window_end - 60), "new": iso(moved)}
        # congested dock: only a few doors free. One early slot opens up on the first dock DC only.
        free = ([window_end - 20] if i == 12 else []) + [moved + 30, moved + 90]
        docks[dc]["open_slots"] = [iso(m) for m in free]
        events.append({"ts": iso(depart + 80), "source": "TMS", "type": "appointment_moved",
                       "shipment_id": sid, "new_appointment": iso(moved)})
    if late:
        # old way: nobody notices until the customer calls, some time after the window closes
        key[sid] = {"late": True, "true_cause": truth, "customer_called_at": iso(window_end + random.randint(20, 80))}
    else:
        key[sid] = {"late": False, "true_cause": "none"}

events.sort(key=lambda e: e["ts"])
backup = {c: {"backup_carrier": CARRIERS[(j + 2) % 4], "ready_in_min": 35 + 10 * j, "cost_usd": 450 + 120 * j}
          for j, c in enumerate(CARRIERS)}

d = Path("data"); d.mkdir(exist_ok=True)
for name, obj in {"shipments": shipments, "events": events, "accounts": ACCOUNTS, "tone_profiles": TONES,
                  "weather": weather, "traffic": traffic, "carrier_status": carrier_status,
                  "backup_carriers": backup, "dock_schedules": docks, "answer_key": key,
                  "baseline": {"manual_minutes_per_exception": {"investigate": 12, "rebook_or_reroute": 8,
                                                                "write_customer_email": 8},
                               "review_minutes_per_agent_proposal": 1.5,
                               "note": "Old-way minutes are dispatcher estimates; customer call times are simulated."}
                  }.items():
    (d / f"{name}.json").write_text(json.dumps(obj, indent=2))
print(f"wrote {len(shipments)} shipments, {len(events)} events, {sum(v['late'] for v in key.values())} truly late")
