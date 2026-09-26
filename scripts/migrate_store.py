#!/usr/bin/env python3
"""One-off: move reviews/evidence.jsonl into the evidence store evidence/, in the current S3 model.

S3's draft changed: records are never anonymous (a GitHub account, an AI agent, or both), and an agent
is `{tool, model, session}` rather than a label. Voyager's named results, which came from Zulip and no
GitHub account, become an agent's; agents given as labels ("Claude Code, Opus 5, session 0957…") are
parsed. Each record keeps its `migration.key`, so the sync still converts nothing twice; ids are
recomputed (no record refers to another yet).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_sync import STORE, ROOT, open_store  # noqa: E402
from evidence_core import records as rec  # noqa: E402


def convert(r: dict) -> dict:
    r = {k: v for k, v in r.items() if k != "id"}
    by = dict(r.get("by", {}))
    if isinstance(by.get("agent"), str):
        by["agent"] = rec.parse_agent(by["agent"])
    if (by.get("identity") or {}).get("kind") != "github":
        by.pop("identity", None)
    r["by"] = by
    return rec.with_id(r)


def main() -> int:
    old = ROOT / "reviews" / "evidence.jsonl"
    records = [json.loads(l) for l in old.read_text(encoding="utf-8").splitlines() if l.strip()]
    ids = {r["id"] for r in records}
    assert not any(r.get("target") in ids or set((r.get("links") or {}).values()) & ids for r in records), \
        "a record refers to another: its id would change"
    store = open_store(STORE)
    added = store.add([convert(r) for r in records])
    old.unlink()
    print(f"{len(added)} records moved to {STORE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
