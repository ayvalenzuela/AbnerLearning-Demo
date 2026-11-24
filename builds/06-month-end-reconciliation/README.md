# Build 06 · Accounting — Month-end reconciliation

**Pattern:** Claude Code + one AI step · **Claude features:** Claude Code (writes the pandas matcher), structured output, Message Batches API

## 1 · Situation
A 60-person company takes about 6 working days to close its books. Two or three of those days go to ticking bank lines against the ledger in spreadsheets, and odd items (a fee nobody booked, a vendor paid twice) turn up late or not at all.

## 2 · Constraints
- The numbers must be exact and auditable, so matching is plain pandas code that anyone can read. Claude never does the arithmetic.
- Claude sees only the lines the rules can't match (about 2% here), never the whole ledger.
- The controller approves every journal entry. Nothing posts automatically.
- The run has to prove itself: the bank-to-ledger difference must be fully explained, to the cent, or the job fails.

## 3 · Architecture
```
Bank export (CSV) + QuickBooks/NetSuite GL export
   -> pandas exact match (date + amount, one-to-one)
   -> near-match rules (date window, cents tolerance, difflib payee names)
   -> Claude: unmatched lines only -> explanation + suggested entry (JSON schema)
   -> exceptions report (Sheets-ready CSV + HTML) -> controller approves
   -> cron, nightly at 02:30
```

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # ~200 bank + ledger lines for Nov 2026 with 8 planted problems
python pipeline.py       # runs all 7 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**. A rule-based stand-in gets the same context the prompt contains (the line, nearby candidates on the other side, the vendor master) and returns the same `ExceptionNote` schema. For example, it spots a transposition when the two amounts use the same digits and differ by a multiple of 9.
Set `ANTHROPIC_API_KEY` to send the same items through the Message Batches API.

| Step | What happens | Code / output |
|---|---|---|
| 1 | Load the bank and ledger exports | `data/*.csv` |
| 2 | Exact match in pandas (same date and amount, one-to-one), written with Claude Code | `exact_match()` |
| 3 | Near-match rules: dates up to 5 days apart, amounts within $1, fuzzy payee names (difflib) | `near_match()`, `outputs/matched_lines.csv` |
| 4 | Only the unmatched lines go to Claude for an explanation and a suggested entry | `batch_structured(schema=ExceptionNote)` |
| 5 | Exceptions report for the controller, plus a check that every cent is accounted for | `outputs/exceptions_report.csv`, `.html` |
| 6 | Schedule it nightly | `outputs/schedule/crontab.txt`, `recon_job.json` |
| 7 | Score against the planted exceptions and the true line pairs | `data/planted_exceptions.json`, `data/true_pairs.json` |

## 5 · Results (offline run on synthetic data)
- Lines matched by code: **191 of 197** bank lines (167 exact, 24 near). All 191 pairs are correct against the true pairing.
- Lines sent to Claude: **9 of 391 (2.3%)**
- Exceptions found: **8 of 8** planted (3 bank fees, a duplicate payment, a transposed amount, 2 timing differences, an unknown vendor), with **0** false alarms
- Unexplained bank-to-ledger difference: **$0.00**
- Reconciliation time for this account: **19.0 h → 1.2 h** a month, saving about **17.8 hours**, or **3.2 → 0.2** working days of the close. This assumes 2.5 minutes per line and 20 minutes per exception by hand, versus 5 minutes to review each explained exception.

## 6 · Replay
"Rules do the bulk, the model explains the leftovers" fits any matching job: invoices to purchase orders, payouts to orders, claims to remittances.
Next time I'd turn the controller's decisions into new rules each month, so the pile sent to Claude keeps shrinking, and I'd write the report straight to the close workbook in Google Sheets.
