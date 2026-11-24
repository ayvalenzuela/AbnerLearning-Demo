"""MCP server for the plant's CMMS (computerized maintenance management system).

Exposes two tools to any MCP client (Claude Desktop, Claude Code, the Agent SDK, or Teams via an agent):
  get_work_order_history(machine_id, fault_code)  - read past work orders and their fixes
  create_work_order(...)                          - log a new work order with the confirmed fix

Backed by a local SQLite file so the demo runs anywhere. In production the same two tools wrap the
CMMS vendor's REST API (Maximo, Fiix, UpKeep, ...), with the plant's service account.

Run as a stdio server:   python cmms_mcp_server.py
Register in Claude Code: claude mcp add cmms -- python /path/to/cmms_mcp_server.py
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

try:  # mcp >= 2.0 renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

HERE = Path(__file__).parent
DB_PATH = Path(os.environ.get("CMMS_DB", HERE / "outputs" / "cmms.db"))

mcp = _Server("cmms", instructions="Plant CMMS: read work-order history and log new work orders.")

COLUMNS = ["wo_id", "machine_id", "line", "fault_code", "opened", "symptom", "root_cause_id", "root_cause",
           "fix_steps", "parts", "minutes_down", "first_time_fix", "technician"]


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(f"CREATE TABLE IF NOT EXISTS work_orders ({', '.join(c_ + ' TEXT' for c_ in COLUMNS)})")
    return c


def reset_db(seed_file: Path) -> int:
    """Load the seed history (demo only)."""
    rows = json.loads(Path(seed_file).read_text())
    with _conn() as c:
        c.execute("DELETE FROM work_orders")
        for r in rows:
            c.execute(f"INSERT INTO work_orders VALUES ({','.join('?' * len(COLUMNS))})",
                      [json.dumps(r[k]) if k == "parts" else str(r[k]) for k in COLUMNS])
    return len(rows)


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["parts"] = json.loads(d["parts"])
    d["minutes_down"] = int(d["minutes_down"])
    d["first_time_fix"] = d["first_time_fix"] == "True"
    return d


@mcp.tool()
def get_work_order_history(machine_id: str, fault_code: str, limit: int = 20) -> list[dict]:
    """Past work orders for a machine model and fault code, newest first, including the confirmed root cause and fix."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM work_orders WHERE machine_id = ? AND fault_code = ? ORDER BY opened DESC LIMIT ?",
                         (machine_id, fault_code, limit)).fetchall()
    return [_row(r) for r in rows]


@mcp.tool()
def create_work_order(machine_id: str, line: str, fault_code: str, symptom: str, root_cause: str,
                      fix_steps: str, minutes_down: int, first_time_fix: bool, technician: str,
                      root_cause_id: str = "", parts: list[str] | None = None, opened: str = "") -> dict:
    """Log a completed repair: what the technician saw, the confirmed root cause and the fix that worked."""
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
        wo = {"wo_id": f"WO-{24001 + n}", "machine_id": machine_id, "line": line, "fault_code": fault_code,
              "opened": opened or datetime.now().isoformat(timespec="minutes"), "symptom": symptom,
              "root_cause_id": root_cause_id or f"{machine_id}-{fault_code}-NEW", "root_cause": root_cause,
              "fix_steps": fix_steps, "parts": parts or [], "minutes_down": minutes_down,
              "first_time_fix": first_time_fix, "technician": technician}
        c.execute(f"INSERT INTO work_orders VALUES ({','.join('?' * len(COLUMNS))})",
                  [json.dumps(wo[k]) if k == "parts" else str(wo[k]) for k in COLUMNS])
    return {"created": wo["wo_id"], **wo}


if __name__ == "__main__":
    mcp.run()
