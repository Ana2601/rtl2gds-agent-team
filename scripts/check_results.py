"""Fail unless the team reached a real sign-off."""
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "results"
rep = json.loads((R / "report.json").read_text())
so = rep["signoff"] or {}
checks = {
    "signed off": bool(so),
    "setup WNS >= 0": (so.get("setup_ws") or -1) >= 0,
    "hold WNS >= 0": (so.get("hold_ws") or -1) >= 0,
    "0 DRC": so.get("drc") == 0,
    "0 antenna": so.get("antenna") == 0,
    "final RTL verified": bool(rep.get("verification")) and rep["verification"].get("latency") == so.get("latency"),
    "GDS written": (R.parent / so.get("artefacts", {}).get("gds", "missing")).exists(),
    "timing drove at least one RTL change": any(m["kind"] == "pipeline" for m in rep["messages"]),
}
for k, v in checks.items():
    print(f"{'ok  ' if v else 'FAIL'} {k}")
sys.exit(0 if all(checks.values()) else 1)
