"""A small MCP server that exposes the (synthetic) CRM to Claude.

Run it for Claude Desktop / Claude Code:   python crm_mcp_server.py      (stdio transport)
The pipeline imports the same tool functions and calls them directly, so the demo needs no MCP client.
"""
import json
from pathlib import Path

try:  # mcp >= 2 renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

CRM_FILE = Path(__file__).parent / "data" / "crm.json"
mcp = _Server("voxly-crm", instructions="Read-only access to accounts, contacts and open deals in the CRM.")


def _crm() -> dict:
    return json.loads(CRM_FILE.read_text())


@mcp.tool()
def list_accounts(territory: str = "") -> list[dict]:
    """List accounts (id, name, territory, industry), optionally filtered by territory."""
    return [{k: a[k] for k in ("account_id", "name", "territory", "industry")} for a in _crm()["accounts"]
            if not territory or a["territory"].lower() == territory.lower()]


@mcp.tool()
def get_account(account_id: str) -> dict:
    """Full account record: size, contact-center stats, current provider, contract end and rep notes."""
    return next(a for a in _crm()["accounts"] if a["account_id"] == account_id)


@mcp.tool()
def list_contacts(account_id: str) -> list[dict]:
    """Contacts on the account with title, buying role and last touch date."""
    return [c for c in _crm()["contacts"] if c["account_id"] == account_id]


@mcp.tool()
def list_open_deals(account_id: str) -> list[dict]:
    """Open opportunities on the account: stage, amount, close date and next step."""
    return [d for d in _crm()["deals"] if d["account_id"] == account_id]


if __name__ == "__main__":
    mcp.run()
