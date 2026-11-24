# Build 02 · Healthcare — Prior-auth packet assistant

**Pattern:** RAG + human review · **Claude features:** citations on document blocks, structured output (JSON schema)

## 1 · Situation
A specialty clinic's prior-auth team spends about 2.4 hours per request matching each payer's rules to chart notes.
Packets that go out with a gap come back denied weeks later, and the patient waits.

## 2 · Constraints
- Chart notes are PHI. In production everything runs under a BAA (Claude API with zero data retention, the EHR and the vector store inside the clinic's tenant). This demo uses fully fictional patients only.
- Every claim in a packet must point to a chart sentence, so the mapping step uses Claude's citations feature and the pipeline rejects any MET claim without a citation.
- Staff, not the model, decide and submit. Every staff edit is saved as eval data.

## 3 · Architecture
```
Payer policy docs -> chunk by section -> embeddings + pgvector (TF-IDF stand-in here)
   -> retrieve this payer's criteria for the CPT code
EHR chart notes  -> Claude with citations (criterion -> cited chart sentence)
   -> gap check + medical necessity letter (structured output)
   -> staff review screen -> submit or hold; edits -> eval_set.jsonl
```
Production swaps `common/retrieval.py` (TF-IDF + cosine similarity in pure Python) for a real embedding model and
pgvector (`ORDER BY embedding <=> $query LIMIT 3` with a `WHERE payer = $1` filter). The interface is the same.

## 4 · Demo — run it yourself
```bash
pip install -r ../../requirements.txt
python make_data.py      # 3 fictional payers, 4 procedures, 6 requests, a nurse's answer key
python pipeline.py       # runs all 6 steps, writes outputs/
```
With no API key it runs in **OFFLINE mode**: a rule-based stand-in returns the same cited-block shape and schema, clearly labelled.
Set `ANTHROPIC_API_KEY` to run the identical pipeline against Claude (`common/citations.py` sends each chart note as a
document block with `"citations": {"enabled": True}`).

| Step | What happens | Code / output |
|---|---|---|
| 1 | Load payer policies, chunk by section, embed | `build_index()`, `common/retrieval.py` |
| 2 | Retrieve this payer's criteria for the procedure (metadata filter on payer) | `pipeline.py` |
| 3 | Claude maps chart evidence to each criterion, with citations | `common/citations.py` |
| 4 | Flag missing evidence and draft the medical necessity letter | `outputs/packets/*.json` |
| 5 | Staff review and submit; every edit becomes eval data | `outputs/eval_set.jsonl` |
| 6 | Score against a prior-auth nurse's hand labels | `data/answer_key.json` |

## 5 · Results (offline run on synthetic data)
- Hours per request: **2.4 → 0.24** (staff review time, simulated: 12 min base + 4 min per edit)
- First-pass approvals: **50%** of requests were complete as received; after the gap check, **3 of 3** submitted packets were complete
- Denials avoided: **3** incomplete packets held for documents before submission
- Criterion agreement with the nurse: **95%** (21 of 22), gap recall **3 of 3**, every MET claim cited
- Staff edit rate: **14%** (4 of 28 fields). The one wrong call: the chart said "stops breathing during sleep", which the offline rule missed; staff corrected it and the case went into the eval set.

## 6 · Replay
Reuse retrieve-the-rules, map-evidence-with-citations, human-submits for any rules-versus-records check: claims, underwriting, audits.
Next time I'd capture staff edits from day one, so the eval set grows with real cases and every prompt change is tested against it.
