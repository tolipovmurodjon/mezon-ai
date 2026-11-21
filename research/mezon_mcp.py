"""The five Mezon law tools as a tiny stdio MCP server (JSON-RPC 2.0, one message per line), so a frontier model in
the Claude Code CLI sits the tools exam with exactly the tools Qwen gets (mezon.tools.TOOLS + mezon.tools.call).

    claude -p --mcp-config <json with: python -X utf8 -m research.mezon_mcp> --strict-mcp-config ...

Runs only locally, against data/store/laws.sqlite. No network.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from mezon.decisions.store import DecisionStore
    class _LexOnly:  # cloud path: only public lex.uz texts may leave the machine (Boss's benchmark exception)
        def __init__(self, store):
            self.s = store

        def by_reg(self, reg):
            return [i for i in self.s.by_reg(reg) if str(i).startswith("lex:")]

        def get(self, did):
            d = self.s.get(did)
            return d if d and d.get("source") == "lex.uz" else None

    DEC = _LexOnly(DecisionStore())
except (ImportError, OSError, RuntimeError):  # no decision store on this machine
    DEC = None
from mezon import tools
from mezon.lawstore.store import LawStore

LAW = LawStore()
DEFS = [{"name": t["function"]["name"], "description": t["function"]["description"],
         "inputSchema": t["function"]["parameters"]} for t in tools.TOOLS]  # get_decision included: Boss approved public decision texts for benchmarks (21 Nov)


def reply(i, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": i, **({"error": error} if error else {"result": result})}
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        m = json.loads(line)
        meth, i = m.get("method"), m.get("id")
        if i is None:  # notifications need no answer
            continue
        if meth == "initialize":
            reply(i, {"protocolVersion": m.get("params", {}).get("protocolVersion", "2025-06-18"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "mezon", "version": "1.1"}})
        elif meth == "tools/list":
            reply(i, {"tools": DEFS})
        elif meth == "tools/call":
            p = m.get("params", {})
            res = tools.call(p.get("name", ""), p.get("arguments") or {}, LAW, DEC)
            reply(i, {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)[:4000]}],
                      "isError": "error" in res})
        elif meth == "ping":
            reply(i, {})
        else:
            reply(i, error={"code": -32601, "message": f"unknown method {meth}"})


if __name__ == "__main__":
    main()
