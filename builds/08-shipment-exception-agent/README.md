# Build 08 · Logistics — Shipment exception agent

**Pattern:** Event-driven agent · **Claude features:** tool use (agent loop on the Messages API), parallel tool calls, structured output (JSON schema)

## 1 · Situation
A regional 3PL runs about 400 loads a day. Dispatchers learn a load is late when the customer calls, then dig through four systems for the cause and type the same apology email by hand.

## 2 · Constraints
- The agent may not move freight on its own. Every reroute, rebook or new dock appointment needs a dispatcher's click.
- Customer emails must match each account's agreed tone (formal, friendly or terse) and use only facts from the record.
- The agent should wake only when a promise is at risk. Plain code watches the event stream, so most events cost nothing.

## 3 · Architecture
```
TMS + GPS webhooks -> ETA watcher (code, wakes agent on risk only)
   -> Exception agent (tool loop: weather, traffic, carrier, dock; then price one fix)
   -> Tone-matched customer update -> Dispatcher one-click approval -> ops log + dashboard
```
In production the four lookups and the email send sit behind MCP servers for the TMS and mail system; here they are Python functions over synthetic feeds, with the same tool schemas.

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 25 shipments, 63 GPS/TMS events, tool feeds, answer key
python pipeline.py       # runs all 6 steps, writes outputs/
open outputs/ops_dashboard.html
```
With no API key it runs in **OFFLINE mode**: a rule-based policy picks the tool calls, and the same tool functions run on the same data. Set `ANTHROPIC_API_KEY` to let Claude drive the tool loop (`common/agent_loop_events.py`).

| Step | What happens | Code |
|---|---|---|
| 1 | Replay events in time order; recompute ETA; wake the agent only when ETA or dock appointment passes the promised window | `on_event()` in `pipeline.py` |
| 2 | Agent checks weather, traffic, carrier and dock in one parallel tool turn; the biggest explained delay is the cause | `common/agent_loop_events.py` |
| 3 | Agent prices one fix (reroute, rebook or reset the appointment) and checks it against the window | `quote_*` tools |
| 4 | Customer update drafted in the account's tone profile, only for shipments that are still late | `data/tone_profiles.json` |
| 5 | Dispatcher approves in one click (simulated); outcome logged | `outputs/ops_log.json`, `outputs/ops_dashboard.html` |
| 6 | Causes and warning time scored against ops leads' hand-labelled answer key | `data/answer_key.json` |

## 5 · Results (offline run on synthetic data)
- Exceptions caught before the promised window: **9 of 9** (1 extra wake-up was a fuel stop; the agent found no cause and took no action)
- Warning time: **61 minutes after the window (customer calls) → 323 minutes before it** (median)
- Cause accuracy against the answer key: **9 of 10 (90%)**. The miss: a storm closed lanes, so the traffic feed showed the bigger delay and the agent blamed traffic instead of weather.
- Windows saved by the fix itself: **3 of 9**; the other 6 customers got a proactive update before the window closed
- Customer tickets: **9 → 0**; dispatcher time: **4.2 hours → 0.25 hours** (old-way minutes are dispatcher estimates in `data/baseline.json`)

## 6 · Replay
Reuse: "watch a stream, wake an agent on a signal, a person approves" fits any SLA desk: field service, claims, IT incidents.
Next time I'd link traffic incidents to their cause (a storm-closed lane is a weather problem), and feed each dispatcher's edits back into the tone profiles.
