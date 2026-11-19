"""Write the dispatcher's AI prune (scores, gates, pick, hinge) into a round's gallery spec, then rebuild its gallery.

The builders leave scores empty on purpose (whoever builds a variant does not grade it); the prune lives in
prune_<round>.json beside this file, scored against the frozen CRITERIA.md after all five variants existed.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19
    python3 apply_prune.py rerun
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEDIA = Path("/home/bam/bam_ws/reports/media/traj-compare-layouts-2026-11-19")
GALLERY = Path("/home/bam/.claude-personal/skills/babble/scripts/gallery.py")


def apply(round_name: str) -> Path:
    prune = json.loads((HERE / f"prune_{round_name}.json").read_text())
    spec_path = MEDIA / round_name / "gallery-spec.json"
    spec = json.loads(spec_path.read_text())
    weights = {req["id"]: float(req["weight"]) for req in spec["requirements"]}
    for variant in spec["variants"]:
        scored = prune["variants"][variant["id"]]
        variant["scores"] = {fr: {"score": cell[0], "evidence": cell[1], "confidence": cell[2]} for fr, cell in scored["scores"].items()}
        variant["gateResults"] = {gate: {"pass": cell[0], "evidence": cell[1]} for gate, cell in scored["gates"].items()}
        total = sum(weights[fr] * variant["scores"][fr]["score"] / 5.0 for fr in weights)
        print(f"{round_name} {variant['id']} {variant['name']:<28} {total:5.1f}")
    spec["defaultId"] = prune["defaultId"]
    spec["defaultWhy"] = prune["defaultWhy"]
    spec["decisionHinge"] = prune["decisionHinge"]
    spec_path.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    out = MEDIA / round_name / "index.html"
    fresh = out.with_name("index.new.html")  # gallery.py refuses to overwrite; build beside, then replace
    fresh.unlink(missing_ok=True)
    subprocess.run([sys.executable, str(GALLERY), "build", "--spec", str(spec_path), "--output", str(fresh)], check=True)
    fresh.replace(out)
    subprocess.run([sys.executable, str(GALLERY), "check", "--input", str(out), "--strict"], check=True)
    return out


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(apply(name))
