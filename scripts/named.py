#!/usr/bin/env python3
"""The named results and notable definitions of Tau Ceti, as `named` records (S3) in the evidence
store: the declarations worth looking at first, since most of a library is API, glue and steps of
proofs.

  python3 scripts/named.py roadmaps <TauCetiRoadmap checkout> --dataset DIR
  python3 scripts/named.py voyager [<posts.json> ...] --dataset DIR

Two sources name them, besides anyone who names one with the "Name a result" form or a `Named:`
line on the bulk issue (evidence-store's intake records those):

- the roadmaps: each roadmap's generated STATUS.md lists its "Named results" and "Notable
  definitions and infrastructure", each a bold name, a sentence and links to the declarations.
  `roadmaps` records each as a `named` record by the roadmap reader, an agent acting through this
  repository's workflow (the "Follow Tau Ceti" workflow runs it daily), and withdraws the ones a
  roadmap no longer lists;
- Voyager, the bot that announces new results on the Lean Zulip: each bullet of a post is a bold
  link to a declaration's docs page, a sentence and the pull requests. Its announcements are kept
  in data/voyager.jsonl, since reading Zulip takes an account: `voyager` adds those of exports of
  its topic (the messages as the Zulip API returns them) to the file, and records each
  announcement whose declaration is in the dataset. An announcement often comes before the pin
  reaches its pull request: it is recorded when the pin moves past it (the "Follow Tau Ceti"
  workflow runs `voyager` whenever it moves the pin).

Each record is keyed by the declaration's S1 key in the dataset (the pinned commit's).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from evidence_core import Dataset
    from evidence_core import records as rec
    from evidence_core.store import Store
except ImportError:  # a checkout of evidence-core next to this repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence-core"))
    from evidence_core import Dataset
    from evidence_core import records as rec
    from evidence_core.store import Store

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "evidence"
ANNOUNCEMENTS = ROOT / "data" / "voyager.jsonl"
ROADMAP_READER = {"kind": "agent", "identity": {"kind": "github", "id": "github-actions[bot]"},
                  "agent": {"tool": "Tau Ceti roadmap reader"}}
VOYAGER = {"kind": "agent", "agent": {"tool": "Voyager"}}
DOCS_LINK = re.compile(r"\[`?([^\]`]+?)`?\]\((https://taucetiproject\.github\.io/TauCeti/docs/[^)\s]*?#([^)\s]+))\)")
STATUS_BULLET = re.compile(r"^- \*\*(.+?)\*\*\s*(?:—|-)\s*(.*)$")
POST_BULLET = re.compile(r"^- \*\*\[(.+?)\]\((https://[^)\s]+)\)\*\*[†*]*\s*(?:—|-)?\s*(.*)$")
SECTIONS = {"Named results": "result", "Notable definitions and infrastructure": "definition", "Notable definitions": "definition"}


def plain(text: str) -> str:
    """A sentence without its declaration links, pull request numbers or trailing clutter."""
    text = re.sub(r"\s*\(\[`?[^\]]+`?\]\([^)]+\)\)", "", text)
    text = DOCS_LINK.sub(lambda m: m.group(1), text)
    text = re.sub(r"\s*\((?:TauCeti#\d+(?:,\s*)?)+\)\s*$", "", text)
    text = re.sub(r"\s+,", ",", text)
    return " ".join(text.split())


def roadmap_names(root: Path) -> list:
    """Every named result and notable definition in the roadmaps' STATUS.md files."""
    found = []
    for path in sorted(root.glob("TauCetiRoadmap/*/STATUS.md")) + sorted(root.glob("Completed/*/STATUS.md")):
        what = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                what = SECTIONS.get(line.lstrip("#").strip()) if line.startswith("### ") else None
                continue
            bullet = STATUS_BULLET.match(line)
            if what and bullet:
                for link in DOCS_LINK.finditer(bullet.group(2)):
                    found.append({"decl": link.group(3), "name": bullet.group(1), "what": what, "about": plain(bullet.group(2)),
                                  "source": {"roadmap": path.parent.name, "path": path.relative_to(root).as_posix()}})
    return found


def voyager_names(posts: list) -> list:
    """Every announcement in Voyager's posts: the declaration its link points to."""
    found = []
    for post in posts:
        what = "result"
        at = datetime.fromtimestamp(post["timestamp"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for line in post["content"].splitlines():
            heading = line.strip().strip("*").strip()
            if heading in SECTIONS:
                what = SECTIONS[heading]
                continue
            bullet = POST_BULLET.match(line)
            if bullet and "#" in bullet.group(2):
                found.append({"decl": bullet.group(2).split("#", 1)[1], "name": bullet.group(1), "what": what,
                              "about": plain(bullet.group(3)), "source": {"voyager": post["id"], "prs": [int(n) for n in re.findall(r"TauCeti#(\d+)", bullet.group(3))]},
                              "at": at})
    return found


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def named_record(entry: dict, ds: Dataset, by: dict, at: str, origin: dict) -> dict | None:
    """The `named` record of an entry, keyed in ``ds``; None if the declaration is not there."""
    d = ds.by_name.get(entry["decl"])
    if d is None:
        return None
    r = {"schema": rec.SCHEMA, "kind": "named", "subject": rec.subject_from_decl(d, ds), "by": by, "at": at,
         "origin": origin, "name": entry["name"], "what": entry["what"], "source": entry["source"]}
    if entry.get("about"):
        r["about"] = entry["about"]
    return rec.with_id(r)


def key(r: dict) -> tuple:
    return (r["subject"]["name"], r.get("name"), json.dumps(r.get("source"), sort_keys=True))


def sync_roadmaps(store: Store, entries: list, ds: Dataset, at: str) -> tuple[list, list]:
    """The records that make the store say what the roadmaps say: a `named` record for each entry
    it lacks, and a `withdrawn` status for each of the reader's records whose entry is gone."""
    mine = [r for r in store.records if r.get("kind") == "named"
            and (r.get("by", {}).get("agent") or {}).get("tool") == ROADMAP_READER["agent"]["tool"]]
    withdrawn = {r["target"] for r in store.records if r.get("kind") == "status" and r.get("state") == "withdrawn"}
    live = {key(r): r for r in mine if r["id"] not in withdrawn}
    added, seen = [], set()
    for e in entries:
        r = named_record(e, ds, ROADMAP_READER, at, {"kind": "roadmap", "ref": f"TauCetiProject/TauCetiRoadmap/{e['source']['path']}"})
        if r is None:
            continue
        seen.add(key(r))
        if key(r) not in live:
            live[key(r)] = r
            added.append(r)
    gone = [rec.with_id({"schema": rec.SCHEMA, "kind": "status", "target": r["id"], "state": "withdrawn",
                         "by": ROADMAP_READER, "at": at, "note": "no longer in the roadmap"})
            for k, r in live.items() if k not in seen and r not in added]
    return added, gone


def load_announcements(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def entry_key(e: dict) -> tuple:
    return (e["decl"], e["name"], json.dumps(e["source"], sort_keys=True))


def add_announcements(known: list, posts: list) -> list:
    """The announcements of ``posts`` that ``known`` lacks."""
    seen = {entry_key(e) for e in known}
    new = []
    for e in voyager_names(posts):
        if entry_key(e) not in seen:
            seen.add(entry_key(e))
            new.append(e)
    return new


def sync_voyager(store: Store, entries: list, ds: Dataset) -> list:
    """A `named` record by Voyager for each announcement whose declaration is in ``ds`` and that the
    store lacks."""
    known = {key(r) for r in store.records if r.get("kind") == "named"}
    added = []
    for e in entries:
        r = named_record(e, ds, VOYAGER, e["at"], {"kind": "zulip", "ref": f"voyager {e['source']['voyager']}"})
        if r is not None and key(r) not in known:
            known.add(key(r))
            added.append(r)
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", choices=["roadmaps", "voyager"])
    parser.add_argument("paths", type=Path, nargs="*",
                        help="roadmaps: a checkout of TauCetiRoadmap; voyager: exports of Voyager's topic to add")
    parser.add_argument("--dataset", type=Path, required=True, help="the dataset of the pinned commit")
    parser.add_argument("--store", type=Path, default=STORE)
    args = parser.parse_args()
    store, ds = Store.load(args.store), Dataset.load(args.dataset)
    if args.source == "roadmaps":
        if len(args.paths) != 1:
            parser.error("roadmaps: give one checkout of TauCetiRoadmap")
        entries = roadmap_names(args.paths[0])
        added, gone = sync_roadmaps(store, entries, ds, now())
        store.add(added + gone)
        print(f"{len(entries)} named declarations in {len({e['source']['roadmap'] for e in entries})} roadmaps: "
              f"{len(added)} recorded, {len(gone)} withdrawn")
        return 0
    entries = load_announcements(ANNOUNCEMENTS)
    new = add_announcements(entries, [post for path in args.paths for post in json.loads(path.read_text(encoding="utf-8"))])
    if new:
        with ANNOUNCEMENTS.open("a", encoding="utf-8") as out:
            out.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in new)
    added = sync_voyager(store, entries + new, ds)
    store.add(added)
    print(f"{len(entries) + len(new)} announcements ({len(new)} new): {len(added)} recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
