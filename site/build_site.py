"""Collect every build's outputs/trace.json into site/traces.json for the portfolio page."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/ayvalenzuela/AbnerLearning-Demo/tree/claude/serene-lovelace-zoo2ae/"
META = {
    "01": ("Telecom / UCaaS", "Workflow + batch", "Batch is cheaper for work that can wait, and a schema makes every score comparable."),
    "02": ("Healthcare", "RAG + human review", "RAG ties answers to the current policy, and citations let staff check fast. Health data needs a BAA-covered setup and a human who signs off."),
    "03": ("Legal", "Skill", "A Skill bottles expertise once, and Claude loads it only when the task needs it. Same move for any playbook: underwriting, procurement, HR policy."),
    "04": ("Manufacturing", "RAG + MCP", "RAG covers the documents and MCP covers the live system. Knowledge plus action is the core enterprise pattern."),
    "05": ("Property management", "Agent + approvals", "The next step depends on the message. Tools give it hands, and the approval step keeps money and safety decisions with people."),
    "06": ("Accounting", "Claude Code + AI step", "Code does the exact math and Claude handles messy judgment. Using AI only where rules break keeps it cheap, fast and auditable."),
    "07": ("E-commerce", "Batch + structured output", "Batch plus a schema turns Claude into a data factory. Automated checks let people review a sample instead of every row."),
    "08": ("Logistics", "Event-driven agent", "The agent wakes on a signal instead of waiting to be asked. That is the jump from assistant to operator."),
    "09": ("Insurance", "Vision + workflow", "Claude reads messy documents, and the workflow keeps every step fixed and auditable. Confidence decides where people step in."),
    "10": ("B2B sales", "Skill + MCP", "This is a seller's own job, automated. It is the easiest first build to demo, and every sales leader will want it."),
}
out = []
for d in sorted((ROOT / "builds").iterdir()):
    t = d / "outputs" / "trace.json"
    if not t.exists():
        print("missing", d.name); continue
    tr = json.loads(t.read_text())
    num = d.name[:2]
    ind, pat, why = META[num]
    tr.update(build=num, dir=f"builds/{d.name}", industry=ind, pattern=pat, why=why, repo=REPO + f"builds/{d.name}")
    if (ROOT / "site" / "videos" / f"build-{num}.mp4").exists():
        tr["video"] = f"videos/build-{num}.mp4"
    out.append(tr)
(ROOT / "site" / "traces.json").write_text(json.dumps(out, indent=1))
print(f"{len(out)} builds -> site/traces.json")
