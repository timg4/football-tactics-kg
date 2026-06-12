"""Capture PROFILE plans + runtimes of the pattern queries (LO6 material).

Writes generated/profiles/<pattern>.txt with the operator tree (db hits, rows)
for one representative match, plus a season-wide runtime summary.

Usage:  python -m src.patterns.profile
"""

import json
import time

from ..ingest import common
from .cypher import P2_EXCLUDED_PATTERNS, PATTERNS, REGAIN_OUTCOMES

OUT_DIR = common.REPO_ROOT / "generated" / "profiles"
SAMPLE_MATCH = 3754058  # first match of the season


def render(op, depth=0):
    args = op.get("args", {})
    line = (f"{'  ' * depth}{op['operatorType']:<40} "
            f"rows={args.get('Rows', '?'):<8} dbHits={args.get('DbHits', '?')}")
    return "\n".join([line] + [render(c, depth + 1)
                               for c in op.get("children", [])])


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver = common.get_driver()
    with driver.session() as s:
        for name, (query, defaults) in sorted(PATTERNS.items()):
            bind = {**defaults, "params": json.dumps(defaults, sort_keys=True),
                    "regainOutcomes": REGAIN_OUTCOMES,
                    "excludedPatterns": P2_EXCLUDED_PATTERNS}
            t0 = time.time()
            res = s.run("PROFILE " + query, mid=SAMPLE_MATCH, **bind)
            summary = res.consume()
            dt = time.time() - t0
            plan = summary.profile
            text = (f"// {name} on match {SAMPLE_MATCH}, params={bind['params']}\n"
                    f"// wall time: {dt:.2f}s\n\n" + render(plan))
            (OUT_DIR / f"{name.lower()}.txt").write_text(text, encoding="utf-8")
            print(f"{name}: {dt:.2f}s -> generated/profiles/{name.lower()}.txt")
    driver.close()


if __name__ == "__main__":
    main()
