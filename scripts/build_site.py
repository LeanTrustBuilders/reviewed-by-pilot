#!/usr/bin/env python3
"""Build the page of Tau Ceti declarations and what is known of each: reviews, tests, problems.

  python3 scripts/build_site.py --dataset DIR

The page (Reviewed-by's, kept as it was) is fed by the LeanTrustBuilders suite:

- the declarations and their hashes come from the dataset (S2) of the pinned commit, read into
  data/declarations.json by dataset_declarations.py;
- everything people and AI agents said about them is in the evidence store evidence/ (S3), which
  evidence-store's intake fills from the repository's issues and comments;
- what applies now (a review current or on an earlier version, a problem open or fixed, a test
  passing, a challenge met) is computed by evidence-core against the dataset.

It writes site/:

- index.html, the page: search every declaration by name or docstring, filter the named results and
  definitions, definitions from theorems and lemmas, by area and by review, and open one to read it
  and review it;
- data/search.json, one row per declaration (name, keyword, module, line), which the page loads
  first; data/docs.json, each declaration's docstring in one sentence, which it loads next;
- data/m/<n>.json, each module's declarations in full, read when one is opened;
- reviews.json, for other readers too (the atlas, Tau Ceti's docs): each declaration's current
  version, how many people and AI agents reviewed it, every review, the tests it passes, the tests
  proposed for it, and every problem reported with it;
- named.json, the named results and notable definitions, with the coverage of what they rest on.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from evidence_core import Dataset, Evidence, Policy, coverage as coverage_of
    from evidence_core import records as evidence_records
    from evidence_core.store import Store
except ImportError:  # a checkout of evidence-core next to this repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence-core"))
    from evidence_core import Dataset, Evidence, Policy, coverage as coverage_of
    from evidence_core import records as evidence_records
    from evidence_core.store import Store

ROOT = Path(__file__).resolve().parents[1]
MEANING = {"Reviewed-by": "it is the intended mathematical notion"}
DEFINITIONS = {"def", "structure", "class", "inductive", "instance"}
# The state of a problem, as the page shows it: open, or how it was resolved (S3 statuses).
PROBLEM_STATE = {"open": "open", "fixed": "fixed", "intended": "intended", "invalid": "invalid", "withdrawn": "withdrawn"}
# The state of a proposed test (an S3 challenge).
CHALLENGE_STATE = {"open": "open", "met": "written", "failed": "failed", "declined": "not planned", "withdrawn": "withdrawn"}


def issue_of(ref: str) -> tuple:
    """(repository, issue number) of an origin reference like `owner/repo#12`, `owner/repo#12/event/5`
    or a comment's URL."""
    m = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", ref or "")
    if m:
        return m.group(1), int(m.group(2))
    repo, _, rest = (ref or "").partition("#")
    number = re.match(r"\d+", rest)
    return (repo, int(number.group(0))) if number else (repo, None)


def who(by: dict) -> dict:
    """How the page shows who made a record: the GitHub login, and the agent if it is one."""
    return {"by": (by.get("identity") or {}).get("id", ""), "kind": by.get("kind", "person"),
            "agent": evidence_records.agent_label(by.get("agent"))}


def issue_url(r: dict) -> tuple:
    repo, issue = issue_of((r.get("origin") or {}).get("ref", ""))
    return issue, (f"https://github.com/{repo}/issues/{issue}" if repo and issue else "")


def marks_from_evidence(index: dict, ev: Evidence) -> dict:
    """Each declaration's review marks: the acceptances in the store that are neither withdrawn nor
    superseded, each with the status evidence-core gives it against the pinned commit's dataset:
    current, renamed (still current: it followed the declaration to its new name), stale underneath
    (the declaration is written the same, but something it rests on changed), or stale (the
    declaration changed)."""
    names = {item["name"] for item in index["declarations"]}
    marks = defaultdict(list)
    for name, rows in ev.by_decl.items():
        if name not in names:
            continue
        for r, s in rows:
            if r.get("kind") != "review" or r.get("verdict") != "accept":
                continue
            if r["id"] in ev.superseded_by or ev.state(r["id"]) == "withdrawn":
                continue
            issue, url = issue_url(r)
            marks[name].append({
                "trailer": "Reviewed-by", **who(r.get("by", {})),
                "hash": r.get("subject", {}).get("hashes", {}).get("meaning", ""),
                "current": s.applies, "status": s.state, "at": r.get("at", ""),
                "evidence": r.get("rationale", ""), "issue": issue, "url": url, "id": r["id"],
                **({"from": r["subject"]["name"]} if s.state == "renamed" else {})})
    for items in marks.values():
        items.sort(key=lambda m: (not m["current"], m["kind"] == "agent", m["at"]))
    return marks


def tally(marks: list) -> dict:
    """For each kind of mark: how many people and how many AI agents gave it on the current version
    (each counted once), and how many marks are on earlier versions."""
    out = {}
    for trailer in MEANING:
        given = [m for m in marks if m["trailer"] == trailer]
        now = [m for m in given if m["current"]]
        if given:
            out[trailer] = {"people": len({m["by"] for m in now if m["kind"] == "person"}),
                            "ai": len({(m["by"], m["agent"]) for m in now if m["kind"] == "agent"}),
                            "earlier": len(given) - len(now)}
    return out


def latest(ev: Evidence, rid: str) -> dict:
    return (ev.statuses.get(rid) or [{}])[-1]


def problems_from_evidence(index: dict, ev: Evidence) -> dict:
    """Each declaration's problem reports, open ones first, then the newest first."""
    names = {item["name"] for item in index["declarations"]}
    found = defaultdict(list)
    for name, rows in ev.by_decl.items():
        if name not in names:
            continue
        for r, s in rows:
            if r.get("kind") != "review" or r.get("verdict") != "problem" or r["id"] in ev.superseded_by:
                continue
            state = ev.state(r["id"])
            last = latest(ev, r["id"]) if state not in ("open",) else {}
            issue, url = issue_url(r)
            found[name].append({
                "id": r["id"], "issue": issue, "url": url, "status": PROBLEM_STATE.get(state, state),
                "what": (r.get("problem") or {}).get("category", "other"), "why": r.get("rationale", ""),
                "fix": r.get("fix", ""), **who(r.get("by", {})),
                "hash": r.get("subject", {}).get("hashes", {}).get("meaning", ""), "current": s.applies,
                "at": r.get("at", ""),
                **({"closedBy": who(last.get("by", {}))["by"], "closedAt": last.get("at", ""),
                    "commit": last.get("commit", ""), "note": last.get("note", "")} if last else {})})
    for items in found.values():
        items.sort(key=lambda p: p["at"], reverse=True)
        items.sort(key=lambda p: p["status"] != "open")
    return found


def tests_from_evidence(index: dict, ev: Evidence) -> dict:
    """What each declaration is tested by: its unit tests (Tau Ceti's examples that name it, from
    the dataset's examples facet), the key results listed as its tests and the challenges met (S3
    `test` records and met `challenge`s), and the tests proposed for it (S3 challenges). A test
    passes while it is in Tau Ceti at the pinned commit without `sorry`; the counts are of tests
    that pass and of proposals still open."""
    items = {item["name"]: item for item in index["declarations"]}
    out = {}

    def entry(name):
        return out.setdefault(name, {"unit": [], "results": [], "suggested": []})
    for example in index.get("examples", []):
        for name in example["tests"]:
            if name in items:
                entry(name)["unit"].append({"statement": example["statement"], "path": example["path"],
                                            "line": example["line"], "url": example["url"], "passes": not example["sorry"]})
    for name in ev.by_decl:
        if name not in items:
            continue
        for t in ev.tests(name):
            test = items.get(t["test"])
            r = t["record"] if "challenge" not in t else t["met"]
            entry(name)["results"].append({
                "test": t["test"], "status": t["result"], "statement": test["source"] if test else "",
                "url": test["url"] if test else "", "checks": t["checks"], **who(r.get("by", {})),
                "at": r.get("at", ""), **({"challenge": t["challenge"]["id"]} if "challenge" in t else {})})
        for c, state in ev.challenges(name):
            issue, url = issue_url(c)
            last = latest(ev, c["id"]) if state != "open" else {}
            met_by = (last.get("test") or {}).get("name", "") if isinstance(last.get("test"), dict) else ""
            entry(name)["suggested"].append({
                "id": c["id"], "issue": issue, "url": url, "status": CHALLENGE_STATE.get(state, state),
                "test": c.get("property", ""), "statement": c.get("statement", ""), "catches": c.get("catches", ""),
                "modes": c.get("modes", []), **who(c.get("by", {})), "at": c.get("at", ""),
                **({"closedBy": who(last.get("by", {}))["by"], "closedAt": last.get("at", ""), "metBy": met_by} if last else {})})
    for tests in out.values():
        tests["tally"] = {"unit": sum(t["passes"] for t in tests["unit"]),
                          "results": sum(r["status"] == "passes" for r in tests["results"]),
                          "suggested": sum(s["status"] == "open" for s in tests["suggested"])}
    return out


def named_from_evidence(index: dict, ev: Evidence) -> dict:
    """The named results and notable definitions: the declarations with a `named` record in force,
    each with its name, what it is, a sentence, who named it and where, and how much of what it
    rests on is reviewed: the project declarations in its meaning closure (itself included), those
    with a current review by a person, and those with one by a person or an AI agent."""
    names = {item["name"] for item in index["declarations"]}
    out = {}
    for name in sorted(ev.by_decl):
        if name not in names:
            continue
        records = sorted(ev.named(name), key=lambda r: r.get("at", ""))
        if not records:
            continue
        first = records[0]
        people = coverage_of(ev, name, Policy())
        anyone = coverage_of(ev, name, Policy(agents=True))
        out[name] = {"name": first.get("name", ""), "what": first.get("what", "result"), "about": first.get("about", ""),
                     "sources": [{"source": r.get("source") or {}, "by": who(r.get("by", {}))["by"],
                                  "agent": who(r.get("by", {}))["agent"], "at": r.get("at", "")} for r in records],
                     "coverage": {"members": len(people.members), "people": len(people.covered),
                                  "any": len(anyone.covered), "problems": len(people.with_problems),
                                  "upstream": len(people.upstream)}}
    return out


def summary(doc: str, limit: int = 120) -> str:
    """A docstring's first sentence, in plain text."""
    text = " ".join(doc.split())
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*|\*([^*]+)\*", lambda m: m.group(1) or m.group(2), text)
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text, maxsplit=1)[0]
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + " …"


def search_index(index: dict) -> dict:
    modules = [module["module"] for module in index["modules"]]
    position = {name: n for n, name in enumerate(modules)}
    keywords = sorted({item.get("keyword", item["kind"]) for item in index["declarations"]})
    column = {keyword: n for n, keyword in enumerate(keywords)}
    rows = [[item["name"], column[item.get("keyword", item["kind"])], position[item["module"]], item.get("line", 0)]
            for item in index["declarations"] if item["module"] in position]
    return {"tauceti": index["tauceti"], "read": index["read"], "modules": modules, "keywords": keywords, "rows": rows}


def module_summary(doc: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", doc.strip()) if p.strip() and not p.lstrip().startswith("#")]
    return " ".join(paragraphs[0].split()) if paragraphs else ""


def shards(index: dict) -> dict:
    """Each module's declarations in full, keyed by the module's position in the search index."""
    position = {module["module"]: n for n, module in enumerate(index["modules"])}
    out = {n: {"module": module["module"], "path": module["path"], "url": module["url"], "summary": module_summary(module["doc"]),
               "declarations": []} for n, module in enumerate(index["modules"])}
    for item in index["declarations"]:
        if item["module"] in position:
            out[position[item["module"]]]["declarations"].append(
                {key: item.get(key) for key in ("name", "kind", "keyword", "line", "end", "doc", "source", "hash", "url")})
    return out


def named(index: dict, ev: Evidence) -> dict:
    return {"schema": "named/v1", "tauceti": index["tauceti"], "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "declarations": named_from_evidence(index, ev)}


def data(index: dict, ev: Evidence) -> dict:
    marks = marks_from_evidence(index, ev)
    found = problems_from_evidence(index, ev)
    tests = tests_from_evidence(index, ev)
    by_name = {item["name"]: item for item in index["declarations"]}
    return {"schema": "reviewed-by/v1", "tauceti": index["tauceti"], "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "declarations": {name: {"hash": by_name[name]["hash"], "kind": by_name[name]["kind"], "url": by_name[name]["url"],
                                    "tally": tally(marks.get(name, [])), "marks": marks.get(name, []),
                                    "problems": found.get(name, []), **({"tests": tests[name]} if name in tests else {})}
                             for name in sorted(set(marks) | set(found) | set(tests))}}


STYLE = """
:root { color-scheme: light dark; --bg: #f8f7f4; --surface: #ffffff; --ink: #1c2025; --muted: #59626c; --faint: #8b939b; --line: #e3e0da;
  --code: #f3f1ec; --accent: #2b6a99; --person: #2f7d4f; --agent: #6a58b8; --stale: #9aa0a6; --hit: #fff4c2; --problem: #b3261e; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #0e1114; --surface: #151a1f; --ink: #e5e8eb; --muted: #a5aeb6;
  --faint: #7b848d; --line: #252b32; --code: #1a1f25; --accent: #82b6de; --person: #6fcf97; --agent: #b2a4f1; --stale: #6b737b; --hit: #3a3417;
  --problem: #f2a29c; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
a { color: var(--accent); }
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
header { max-width: 1280px; margin: 0 auto; padding: 22px 16px 6px; }
.eyebrow { text-transform: uppercase; letter-spacing: 1.4px; font-size: 11.5px; color: var(--faint); margin: 0 0 4px; }
h1 { font-size: 24px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -.3px; }
.lede { color: var(--muted); margin: 0 0 4px; }
.meta { color: var(--faint); font-size: 13px; margin: 0; }
details.how { max-width: 1280px; margin: 10px auto 0; padding: 0 16px; color: var(--muted); font-size: 14px; }
details.how > summary { cursor: pointer; color: var(--accent); font-weight: 600; }
details.how ol { margin: 8px 0; padding-left: 20px; } details.how li { margin: 3px 0; }
.legend { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; margin: 8px 0; }
.legend dt { font-weight: 600; color: var(--ink); } .legend dd { margin: 0; }
.bar { position: sticky; top: 0; z-index: 5; background: var(--bg); border-bottom: 1px solid var(--line); }
.bar-inner { max-width: 1280px; margin: 0 auto; padding: 12px 16px 10px; display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; }
#search { flex: 1 1 360px; min-width: 0; font: inherit; font-size: 16px; padding: 9px 12px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); }
#search:focus { outline: 2px solid color-mix(in srgb, var(--accent) 45%, transparent); border-color: var(--accent); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chips button, select { font: inherit; font-size: 13px; padding: 5px 11px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); cursor: pointer; }
.chips button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--surface)); font-weight: 600; }
select { border-radius: 8px; max-width: 220px; }
.layout { max-width: 1280px; margin: 0 auto; padding: 10px 16px 60px; display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 18px; align-items: start; }
.status { color: var(--faint); font-size: 13px; margin: 4px 0 8px; }
.results { display: flex; flex-direction: column; gap: 6px; }
.result { display: block; width: 100%; text-align: left; font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 8px 11px; cursor: pointer; }
.result:hover, .result:focus-visible { border-color: var(--faint); }
.result[aria-current="true"] { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.result .name { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13.5px; overflow-wrap: anywhere; }
.result .ns { color: var(--faint); } .result .leaf { font-weight: 600; }
.result .line2 { display: flex; gap: 8px; align-items: baseline; margin-top: 2px; font-size: 12.5px; color: var(--muted); min-width: 0; }
.result .doc1 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.kw { flex: none; font-size: 10.5px; text-transform: uppercase; letter-spacing: .7px; color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; }
.kw.def { color: var(--accent); border-color: currentColor; }
.tickmini { flex: none; font-size: 11px; font-weight: 700; color: var(--person); }
.named { flex: none; font-weight: 600; color: var(--accent); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
.panel .namedline { margin: 6px 0 2px; font-size: 15px; } .panel .namedline strong { font-size: 16px; }
.panel .namedline .from { color: var(--faint); font-size: 12.5px; }
.flag { flex: none; font-size: 11px; font-weight: 700; color: var(--problem); }
.more { font: inherit; font-size: 13px; margin: 6px 0; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: var(--accent); cursor: pointer; }
.panel { position: sticky; top: 70px; max-height: calc(100vh - 86px); overflow: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }
.panel h2 { font-size: 16px; margin: 6px 0 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; font-weight: 600; }
.panel .where { color: var(--faint); font-size: 13px; margin: 0 0 8px; overflow-wrap: anywhere; }
.panel .doc { color: var(--muted); font-size: 14.5px; } .panel .doc p { margin: 6px 0; } .panel .doc code { font-size: 12.5px; }
pre { background: var(--code); border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 10px 0 8px; line-height: 1.45; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 10px 0 4px; }
.primary { font-size: 13.5px; font-weight: 600; text-decoration: none; padding: 5px 14px; border-radius: 6px; border: 1px solid var(--accent); background: var(--accent); color: var(--surface); }
.quiet { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); cursor: pointer; text-decoration: none; }
.marks { display: flex; flex-wrap: wrap; gap: 6px 10px; margin: 8px 0; }
.mark { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink); text-decoration: none; border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px 2px 3px; }
.tick { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; font-weight: 700; }
.mark.person .tick { background: var(--person); color: var(--surface); }
.mark.agent .tick { border: 1.5px solid var(--agent); color: var(--agent); }
.trailer { font-weight: 600; } .ai { font-size: 10.5px; font-weight: 700; letter-spacing: .6px; color: var(--agent); }
.mark.stale { color: var(--stale); } .mark.stale .tick { background: none; border: 1.5px solid var(--stale); color: var(--stale); } .mark.stale .ai { color: var(--stale); }
.note { font-size: 11.5px; font-style: italic; }
.mark.summary { padding-right: 12px; } .mark.summary .who { color: var(--muted); }
details.who, details.which { margin: 2px 0 8px; }
details.who > summary, details.which > summary { cursor: pointer; color: var(--accent); font-size: 13px; }
details.who .head, details.which .head { font-size: 12.5px; font-weight: 600; margin: 8px 0 2px; }
.mark.tested .tick { background: var(--accent); color: var(--surface); }
.test { border-top: 1px solid var(--line); padding: 6px 0 2px; font-size: 13.5px; } .test p { margin: 3px 0; }
.test .line { margin: 0; font-size: 12.5px; color: var(--muted); } .test pre { margin: 4px 0; white-space: pre-wrap; }
.pass { color: var(--person); font-weight: 600; } .fail { color: var(--problem); font-weight: 600; }
.quiet.warn { color: var(--problem); border-color: color-mix(in srgb, var(--problem) 40%, var(--line)); }
.problem { border: 1px solid color-mix(in srgb, var(--problem) 45%, var(--line)); border-radius: 8px; padding: 8px 12px; margin: 8px 0; font-size: 14px; }
.problem.closed { border-color: var(--line); color: var(--muted); }
.problem .head { margin: 0; font-size: 13px; color: var(--muted); }
.problem .state { font-weight: 700; color: var(--problem); } .problem.closed .state { color: var(--muted); }
.problem p { margin: 6px 0; } .problem .fix { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--faint); margin: 10px 0 0; }
.problem pre { white-space: pre-wrap; margin: 4px 0; }
.sub { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--faint); margin: 16px 0 6px; }
.siblings { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.siblings button { font: inherit; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; text-align: left; background: none; border: 0; padding: 2px 0; color: var(--accent); cursor: pointer; overflow-wrap: anywhere; }
.siblings button[aria-current="true"] { color: var(--ink); font-weight: 600; }
.linkish { font: inherit; font-size: 13px; background: none; border: 0; padding: 0; color: var(--accent); cursor: pointer; }
.detail-note { color: var(--faint); font-size: 12.5px; margin: 2px 0 6px; }
.areas { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 14px; }
.areas button { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); cursor: pointer; }
.areas button span { color: var(--faint); margin-left: 4px; }
.empty { color: var(--muted); }
.back { display: none; }
footer { max-width: 1280px; margin: 0 auto; padding: 0 16px 40px; color: var(--faint); font-size: 13px; }
@media (max-width: 860px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .panel { display: none; position: fixed; inset: 0; top: 0; max-height: none; border-radius: 0; z-index: 10; padding: 14px 16px 40px; }
  body.reading .panel { display: block; }
  .back { display: inline-block; }
  h1 { font-size: 21px; }
}
"""

SCRIPT = r"""
const SETTINGS = JSON.parse(document.getElementById('settings').textContent);
const $ = id => document.getElementById(id);
const DEFS = new Set(['def', 'abbrev', 'structure', 'class', 'inductive', 'instance', 'class inductive']);
const MEANING = {'Reviewed-by': 'it is the intended mathematical notion', 'Tested-by': 'its examples and unit tests check out'};
// What a problem report says is wrong: the failure modes of trusting-definitions.md, as the problem form asks.
const WHAT = {F1: 'A different object', F2: 'A different convention', F3: 'Wrong on edge cases', F4: 'A junk value',
  F5: 'Vacuous or trivial', F6: 'An arbitrary choice', F7: 'Something wrong underneath', F8: 'Drift', F9: 'Less general than the source',
  naming: 'Misleading name or docstring', other: 'Something else is off', wrong: 'Wrong', misleading: 'Misleading name or docstring'};
const CLOSED = {fixed: 'Fixed', intended: 'Intended as it is', invalid: 'Not a problem', withdrawn: 'Withdrawn',
  'not planned': 'Closed without a fix', duplicate: 'Closed as a duplicate'};
const PAGE = 60;
let index = null, lower = [], leafLower = [], area = [], docs = null, docsLower = null, marks = {}, reviewed = new Set(), flagged = new Set(), tested = new Set();
let namedOf = {}, namedLower = [];
let state = {q: '', group: 'all', status: 'all', area: '', d: ''}, shown = PAGE, results = [];
const shardCache = new Map();

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
function prose(text) {
  return String(text || '').trim().split(/\n\s*\n/).filter(Boolean).map(block => '<p>' + esc(block.replace(/\s+/g, ' '))
    .replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2">$1</a>') + '</p>').join('');
}
const when = s => { const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}); };
// The evidence store's issue forms (evidence-store), with the declaration and the commit shown filled in.
function formLink(template, title, name) {
  const q = new URLSearchParams({template, title: title + name, decl: name, commit: SETTINGS.tauceti});
  return 'https://github.com/' + SETTINGS.repo + '/issues/new?' + q.toString();
}
const reviewLink = name => formLink('evidence-review.yml', 'Review: ', name);
const suggestLink = name => formLink('evidence-challenge.yml', 'Challenge: ', name);
const problemLink = name => formLink('evidence-problem.yml', 'Problem: ', name);
const testLink = name => formLink('evidence-test.yml', 'Test: ', name);
const issueUrl = n => 'https://github.com/' + SETTINGS.repo + '/issues/' + n;

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state = {q: p.get('q') || '', group: p.get('kind') || 'all', status: p.get('status') || 'all', area: p.get('area') || '',
           d: p.get('d') || '', m: p.get('m') || ''};
}
function writeHash(replace) {
  const p = new URLSearchParams();
  if (state.q) p.set('q', state.q); if (state.group !== 'all') p.set('kind', state.group); if (state.status !== 'all') p.set('status', state.status);
  if (state.area) p.set('area', state.area); if (state.m) p.set('m', state.m); if (state.d) p.set('d', state.d);
  const hash = '#' + p.toString();
  if (location.hash !== hash) history[replace ? 'replaceState' : 'pushState'](null, '', hash || '#');
}

function passes(i) {
  const kw = index.keywords[index.rows[i][1]];
  if (state.m && index.modules[index.rows[i][2]] !== state.m) return false;
  if (state.group === 'def' && !DEFS.has(kw)) return false;
  if (state.group === 'thm' && DEFS.has(kw)) return false;
  if (state.group === 'named' && !namedOf[index.rows[i][0]]) return false;
  if (state.area && area[i] !== state.area) return false;
  if (state.status === 'reviewed' && !reviewed.has(index.rows[i][0])) return false;
  if (state.status === 'open' && reviewed.has(index.rows[i][0])) return false;
  if (state.status === 'problem' && !flagged.has(index.rows[i][0])) return false;
  if (state.status === 'tested' && !tested.has(index.rows[i][0])) return false;
  return true;
}
function search() {
  const tokens = state.q.toLowerCase().split(/\s+/).filter(Boolean), joined = tokens.join('');
  const found = [];
  for (let i = 0; i < index.rows.length; i++) {
    if (!passes(i)) continue;
    if (!tokens.length) { found.push([0, i]); continue; }
    let score = 0;
    for (const t of tokens) {
      const leaf = leafLower[i], full = lower[i];
      const s = leaf === t ? 100 : leaf.startsWith(t) ? 60 : leaf.includes(t) ? 40 : full.includes(t) ? 25
        : namedLower[i] && namedLower[i].includes(t) ? 30 : docsLower && docsLower[i].includes(t) ? 8 : 0;
      if (!s) { score = -1; break; }
      score += s;
    }
    if (score < 0) continue;
    if (lower[i] === joined) score += 1000;
    found.push([score, i]);
  }
  if (tokens.length) found.sort((a, b) => b[0] - a[0] || lower[a[1]].length - lower[b[1]].length);
  return found.map(x => x[1]);
}

function nameHtml(name) {
  const cut = name.lastIndexOf('.');
  return cut < 0 ? '<span class="leaf">' + esc(name) + '</span>' : '<span class="ns">' + esc(name.slice(0, cut + 1)) + '</span><span class="leaf">' + esc(name.slice(cut + 1)) + '</span>';
}
function resultHtml(i) {
  const [name, k] = index.rows[i], kw = index.keywords[k];
  const doc = docs ? docs[i] : '', named = namedOf[name];
  return '<button class="result" data-i="' + i + '"' + (state.d === name ? ' aria-current="true"' : '') + '><div class="name">' + nameHtml(name) + '</div>' +
    '<div class="line2"><span class="kw' + (DEFS.has(kw) ? ' def' : '') + '">' + esc(kw) + '</span>' + (flagged.has(name) ? '<span class="flag" title="A problem is reported">!</span>' : '') +
    (reviewed.has(name) ? '<span class="tickmini" title="' + esc(reviewedTip(name)) + '">✓</span>' : '') +
    (named ? '<span class="named" title="A named result or definition">' + esc(named.name) + '</span>' : '') +
    '<span class="doc1">' + esc(doc || index.modules[index.rows[i][2]]) + '</span></div></button>';
}
function renderResults() {
  const box = $('results');
  const filtered = state.q || state.group !== 'all' || state.status !== 'all' || state.area || state.m;
  if (!filtered) {
    const counts = {};
    area.forEach(a => { counts[a] = (counts[a] || 0) + 1; });
    const recent = Object.entries(marks).flatMap(([name, entry]) => entry.marks.map(m => ({name, ...m}))).sort((a, b) => (b.at || '').localeCompare(a.at || ''))
      .filter((m, n, all) => all.findIndex(o => o.name === m.name) === n).slice(0, 12);
    const reported = Object.entries(marks).flatMap(([name, entry]) => (entry.problems || []).filter(p => p.status === 'open').map(p => ({name, ...p})))
      .sort((a, b) => (b.at || '').localeCompare(a.at || '')).filter((p, n, all) => all.findIndex(q => q.name === p.name) === n);
    const row = m => { const i = rowOf.get(m.name); return i === undefined ? '' : resultHtml(i); };
    $('status').textContent = index.rows.length.toLocaleString() + ' declarations. Search by name or by words from their docstrings.';
    box.innerHTML = '<p class="sub">Areas</p><div class="areas">' + Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([a, n]) =>
      '<button data-area="' + esc(a) + '">' + esc(a) + '<span>' + n.toLocaleString() + '</span></button>').join('') + '</div>' +
      (reported.length ? '<p class="sub">Open problems</p><div class="results">' + reported.map(row).join('') + '</div>' : '') +
      '<p class="sub">Recently reviewed</p>' + (recent.length ? '<div class="results">' + recent.map(row).join('') + '</div>' : '<p class="empty">No marks yet.</p>');
    return;
  }
  results = search();
  if (state.m) results.sort((a, b) => index.rows[a][3] - index.rows[b][3]);
  const n = results.length;
  $('status').textContent = n ? n.toLocaleString() + ' match' + (n === 1 ? '' : 'es') + (state.q && !docs ? ' by name (docstrings still loading)' : '') : 'No matches.';
  box.innerHTML = '<div class="results">' + results.slice(0, shown).map(resultHtml).join('') + '</div>' + (n > shown ? '<button class="more" id="more">Show more</button>' : '');
}

async function shard(m) {
  if (!shardCache.has(m)) shardCache.set(m, fetch('data/m/' + m + '.json').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }));
  return shardCache.get(m);
}
function countText(t) {
  const parts = [];
  if (t.people) parts.push(t.people + (t.people === 1 ? ' person' : ' people'));
  if (t.ai) parts.push(t.ai + ' AI');
  return parts.join(' · ');
}
function tallyHtml(entry) {
  return Object.entries(entry.tally || {}).map(([trailer, t]) => {
    const now = countText(t), kind = t.people ? 'person' : t.ai ? 'agent' : 'stale';
    const earlier = t.earlier ? '<span class="note">' + t.earlier + ' on earlier versions</span>' : '';
    return '<span class="mark summary ' + kind + '" title="' + esc(trailer + ': ' + (MEANING[trailer] || '')) + '"><span class="tick" aria-hidden="true">✓</span>' +
      '<span class="trailer">' + esc(trailer) + '</span> <span class="who">' + esc(now) + '</span>' + (now && earlier ? ' · ' : '') + earlier + '</span>';
  }).join('');
}
function reviewedTip(name) {
  const t = ((marks[name] || {}).tally || {})['Reviewed-by'];
  return t && countText(t) ? 'Reviewed by ' + countText(t).replace(' · ', ' and ') : 'Reviewed';
}
function byHtml(r) {
  return r.kind === 'agent' ? esc(r.agent) + ' <span class="ai">AI</span> via @' + esc(r.by) : '@' + esc(r.by);
}
function testCount(t) {
  const parts = [];
  if (t.unit) parts.push(t.unit + (t.unit === 1 ? ' unit test' : ' unit tests'));
  if (t.results) parts.push(t.results + (t.results === 1 ? ' key result' : ' key results'));
  if (t.suggested) parts.push(t.suggested + ' proposed');
  return parts.join(' · ');
}
const PASSES = {passes: '<span class="pass">passes</span>', sorry: '<span class="fail">has sorry</span>', missing: '<span class="fail">not in Tau Ceti at this commit</span>'};
function testsHtml(tests) {
  const total = tests.unit.length + tests.results.length + tests.suggested.length;
  const unit = tests.unit.map(u => '<div class="test"><p class="line">' + PASSES[u.passes ? 'passes' : 'sorry'] + ' · <a href="' + esc(u.url) + '">' +
    esc(u.path) + ', line ' + esc(u.line) + '</a></p><pre>' + esc(u.statement) + '</pre></div>').join('');
  const results = tests.results.map(r => '<div class="test"><p class="line">' + (PASSES[r.status] || '') + ' · ' +
    (r.url ? '<a class="mono" href="' + esc(r.url) + '">' + esc(r.test) + '</a>' : '<span class="mono">' + esc(r.test) + '</span>') +
    (r.challenge ? ' · meets a proposed test, by ' : ' · listed by ') + byHtml(r) + '</p>' +
    (r.statement ? '<pre>' + esc(r.statement) + '</pre>' : '') + (r.checks ? '<p>' + esc(r.checks) + '</p>' : '') + '</div>').join('');
  const suggested = tests.suggested.map(t => '<div class="test"><p class="line">' + (t.status === 'open' ? 'Proposed' : esc(t.status[0].toUpperCase() + t.status.slice(1))) +
    (t.metBy ? ' as <span class="mono">' + esc(t.metBy) + '</span>' : '') + ' · proposed by ' + byHtml(t) +
    ', ' + when(t.at) + (t.issue ? ' · <a href="' + esc(t.url || issueUrl(t.issue)) + '">Issue #' + esc(t.issue) + '</a>' : '') + '</p>' + prose(t.test) +
    (t.statement ? '<pre>' + esc(t.statement) + '</pre>' : '') +
    (t.catches ? '<p class="note">Would catch: ' + esc(t.catches) + '</p>' : '') + '</div>').join('');
  return '<div class="marks"><span class="mark summary tested" title="What it passes: unit tests and key results in Tau Ceti"><span class="tick" aria-hidden="true">✓</span>' +
    '<span class="trailer">Tested by</span> <span class="who">' + esc(testCount(tests.tally) || 'nothing that passes yet') + '</span></span></div>' +
    '<details class="which"' + (total <= 3 ? ' open' : '') + '><summary>Which (' + total + ')</summary>' +
    (unit ? '<p class="head">Unit tests: examples in Tau Ceti that name it</p>' + unit : '') +
    (results ? '<p class="head">Key results listed as tests</p>' + results : '') + (suggested ? '<p class="head">Proposed tests</p>' + suggested : '') + '</details>';
}
function namedHtml(name) {
  const named = namedOf[name];
  if (!named) return '';
  const from = named.sources.map(s => {
    if (s.source && s.source.roadmap) {
      return 'the <a href="https://github.com/TauCetiProject/TauCetiRoadmap/blob/main/' + esc(s.source.path) + '">' + esc(s.source.roadmap) + '</a> roadmap';
    }
    if (s.source && s.source.voyager) {
      const prs = (s.source.prs || []).map(n => '<a href="https://github.com/TauCetiProject/TauCeti/pull/' + n + '">TauCeti#' + n + '</a>').join(', ');
      return 'Voyager' + (prs ? ', ' + prs : '') + (s.at ? ', ' + when(s.at) : '');
    }
    if (s.source && s.source.url) return '<a href="' + esc(s.source.url) + '">' + esc(s.agent || ('@' + s.by)) + '</a>';
    return s.agent ? esc(s.agent) + (s.by ? ' via @' + esc(s.by) : '') : esc(s.by ? '@' + s.by : 'a reader');
  });
  const c = named.coverage;
  const cover = c ? '<br><span class="from">What it says rests on ' + c.members + ' Tau Ceti declaration' + (c.members === 1 ? '' : 's') +
    ' (itself included): ' + c.people + ' reviewed by people' + (c.any > c.people ? ', ' + c.any + ' counting AI agents' : '') +
    (c.problems ? ', ' + c.problems + ' with an open problem' : '') + '.</span>' : '';
  return '<p class="namedline"><strong>' + esc(named.name) + '</strong>' + (named.about ? ' — ' + esc(named.about) : '') +
    '<br><span class="from">Named ' + (named.what === 'definition' ? 'as a notable definition' : 'as a result') + ' by ' + from.join('; ') + '.</span>' + cover + '</p>';
}
function whoHtml(entry) {
  return Object.keys(MEANING).map(trailer => {
    const given = entry.marks.filter(m => m.trailer === trailer);
    return given.length ? '<p class="head">' + esc(trailer) + '</p><div class="marks">' + given.map(m => markHtml(m, false)).join('') + '</div>' : '';
  }).join('');
}
function markHtml(m, named = true) {
  const who = m.kind === 'agent' ? esc(m.agent) + ' <span class="ai">AI</span> via @' + esc(m.by) : '@' + esc(m.by);
  const tip = m.trailer + ': ' + (MEANING[m.trailer] || '') + '. Version ' + m.hash + ', ' + when(m.at) + '.' + (m.evidence ? ' Evidence: ' + m.evidence : '');
  const href = m.url || (m.issue ? 'https://github.com/' + SETTINGS.repo + '/issues/' + m.issue : '#');
  const note = m.current ? (m.status === 'renamed' ? ' <span class="note">made on ' + esc(m.from) + '</span>' : '') :
    ' <span class="note">' + (m.status === 'stale-underneath' ? 'something it rests on changed since' : 'earlier version') + '</span>';
  return '<a class="mark ' + esc(m.kind) + (m.current ? '' : ' stale') + '" href="' + esc(href) + '" title="' + esc(tip) + '"><span class="tick" aria-hidden="true">✓</span>' +
    (named ? '<span class="trailer">' + esc(m.trailer) + '</span> ' : '') + '<span class="who">' + who + '</span>' + note + '</a>';
}
function problemHtml(p) {
  const who = p.kind === 'agent' ? esc(p.agent) + ' <span class="ai">AI</span> via @' + esc(p.by) : '@' + esc(p.by);
  const open = p.status === 'open';
  return '<div class="problem' + (open ? '' : ' closed') + '"><p class="head"><span class="state">' + (open ? 'Open' : esc(CLOSED[p.status] || 'Closed')) + '</span> · ' +
    esc(WHAT[p.what] || 'Problem') + ' · reported by ' + who + ', ' + when(p.at) +
    (p.current ? '' : ' · <span class="note">about an earlier version; the declaration has changed since</span>') + '</p>' + prose(p.why) +
    (p.fix ? '<p class="fix">Suggested fix</p><pre>' + esc(p.fix) + '</pre>' : '') +
    '<p><a href="' + esc(p.url || issueUrl(p.issue)) + '">Issue #' + esc(p.issue) + '</a>' + (p.closedAt ? ' · ' + esc((CLOSED[p.status] || 'closed').toLowerCase()) + ' by @' + esc(p.closedBy) + ', ' + when(p.closedAt) +
      (p.commit ? ' in <span class="mono">' + esc(p.commit.slice(0, 12)) + '</span>' : '') : '') + '</p></div>';
}
function moduleHtml(name) {
  const m = index.modules.indexOf(name);
  if (m < 0) return '<p class="empty">' + esc(name) + ' is not a module at this commit.</p>';
  const rows = index.rows.map((r, i) => [r, i]).filter(([r]) => r[2] === m);
  const named = rows.filter(([r]) => namedOf[r[0]]), seen = rows.filter(([r]) => reviewed.has(r[0]));
  const shown = rows.filter(([r]) => tested.has(r[0])), reported = rows.filter(([r]) => flagged.has(r[0]));
  return '<button class="quiet back" id="back">← Back</button><p class="where">File</p><h2>' + esc(name) + '</h2>' +
    '<p class="where">' + rows.length + ' declaration' + (rows.length === 1 ? '' : 's') + ' · ' + seen.length + ' reviewed · ' +
    shown.length + ' with tests' + (reported.length ? ' · <span class="fail">' + reported.length + ' reported</span>' : '') + '</p>' +
    (named.length ? '<p class="sub">Named here</p><div class="results">' + named.map(([, i]) => resultHtml(i)).join('') + '</div>' : '') +
    '<p class="sub">Every declaration in this file</p><p class="detail-note">Choose one to read it, review it, suggest a test or report a problem.</p>' +
    '<div class="siblings">' + rows.map(([r]) => '<button data-name="' + esc(r[0]) + '">' + esc(r[0]) + '</button>').join('') + '</div>';
}
async function renderPanel() {
  const panel = $('panel');
  document.body.classList.toggle('reading', !!state.d || !!state.m);
  if (!state.d && state.m) { panel.innerHTML = moduleHtml(state.m); return; }
  if (!state.d) { panel.innerHTML = '<p class="empty">Choose a declaration to read it, see its marks and review it.</p>'; return; }
  const i = rowOf.get(state.d);
  if (i === undefined) { panel.innerHTML = '<button class="quiet back" id="back">← Back</button><p class="empty">' + esc(state.d) + ' is not a declaration at this commit.</p>'; return; }
  const [name, k, m, line] = index.rows[i];
  panel.innerHTML = '<button class="quiet back" id="back">← Back</button><h2>' + esc(name) + '</h2><p class="where">' + esc(index.keywords[k]) + ' in ' + esc(index.modules[m]) + ', line ' + line + '</p><p class="empty">Loading…</p>';
  let data;
  try { data = await shard(m); } catch (e) { panel.querySelector('.empty').textContent = 'Could not load this module.'; return; }
  if (state.d !== name) return;
  const item = data.declarations.find(d => d.name === name);
  const entry = marks[name];
  const lines = item.source.split('\n'), long = lines.length > 60;
  panel.innerHTML = '<button class="quiet back" id="back">← Back</button>' +
    '<span class="kw' + (DEFS.has(item.keyword) ? ' def' : '') + '">' + esc(item.keyword) + '</span><h2>' + nameHtml(name) + '</h2>' +
    '<p class="where"><a href="' + esc(data.url) + '">' + esc(data.module) + '</a> (<button class="linkish" id="file">this file</button>), lines ' +
    item.line + '–' + item.end + ' · version <span class="mono">' + esc(item.hash) + '</span></p>' +
    namedHtml(name) + (item.doc ? '<div class="doc">' + prose(item.doc) + '</div>' : '') +
    '<pre><code id="src">' + esc(long ? lines.slice(0, 60).join('\n') + '\n…' : item.source) + '</code></pre>' +
    '<div class="actions"><a class="primary" href="' + esc(reviewLink(name, item.hash)) + '">Review this</a>' +
    '<a class="quiet" href="' + esc(suggestLink(name, item.hash)) + '">Suggest a test</a>' +
    '<a class="quiet" href="' + esc(testLink(name)) + '">List a test</a>' +
    '<a class="quiet warn" href="' + esc(problemLink(name, item.hash)) + '">Report a problem</a>' +
    '<button class="quiet" id="copy">Copy name</button><a class="quiet" href="' + esc(item.url) + '">Source on GitHub</a>' + (long ? '<button class="quiet" id="all">Show all ' + lines.length + ' lines</button>' : '') + '</div>' +
    (entry && entry.problems && entry.problems.length ? '<p class="sub">Problems</p>' + entry.problems.map(problemHtml).join('') : '') +
    '<p class="sub">Reviews</p>' + (entry && entry.marks.length ? '<div class="marks">' + tallyHtml(entry) + '</div>' +
      '<details class="who"' + (entry.marks.length <= 3 ? ' open' : '') + '><summary>Who (' + entry.marks.length + ')</summary>' +
      whoHtml(entry) + '</details>' : '<p class="empty">No reviews yet.</p>') +
    '<p class="sub">Tests</p>' + (entry && entry.tests ? testsHtml(entry.tests) : '<p class="empty">No tests yet: no example in Tau Ceti names it, and none is listed or suggested.</p>') +
    '<p class="sub">In ' + esc(data.module.split('.').slice(-1)[0]) + '</p><div class="siblings">' + data.declarations.map(d =>
      '<button data-name="' + esc(d.name) + '"' + (d.name === name ? ' aria-current="true"' : '') + '>' + esc(d.name.split('.').slice(-1)[0]) + '</button>').join('') + '</div>';
  const file = $('file');
  if (file) file.addEventListener('click', () => update({m: data.module, d: ''}));
  const all = $('all');
  if (all) all.addEventListener('click', () => { $('src').textContent = item.source; all.remove(); });
  $('copy').addEventListener('click', () => navigator.clipboard && navigator.clipboard.writeText(name).then(() => { $('copy').textContent = 'Copied'; }));
}
let rowOf = new Map();
function render() { renderResults(); renderPanel(); syncControls(); }
function syncControls() {
  if (document.activeElement !== $('search') && $('search').value !== state.q) $('search').value = state.q;
  document.querySelectorAll('[data-group]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.group === state.group)));
  $('state-filter').value = state.status; $('area-filter').value = state.area;
}
function update(change, replace) { state = {...state, ...change}; shown = PAGE; writeHash(replace); render(); }

document.addEventListener('click', event => {
  const result = event.target.closest('.result');
  if (result) { update({d: index.rows[+result.dataset.i][0]}); return; }
  const sibling = event.target.closest('.siblings button');
  if (sibling) { update({d: sibling.dataset.name}); return; }
  const chip = event.target.closest('[data-group]');
  if (chip) { update({group: chip.dataset.group}, true); return; }
  const areaButton = event.target.closest('[data-area]');
  if (areaButton) { update({area: areaButton.dataset.area}); return; }
  if (event.target.id === 'more') { shown += PAGE * 2; renderResults(); return; }
  if (event.target.closest('#back')) { update(state.d ? {d: ''} : {m: ''}); }
});
let timer;
$('search').addEventListener('input', event => { clearTimeout(timer); timer = setTimeout(() => update({q: event.target.value.trim()}, true), 120); });
$('search').addEventListener('keydown', event => { if (event.key === 'Enter' && results.length) update({q: event.target.value.trim(), d: index.rows[results[0]][0]}); });
$('state-filter').addEventListener('change', event => update({status: event.target.value}, true));
$('area-filter').addEventListener('change', event => update({area: event.target.value}, true));
document.addEventListener('keydown', event => {
  if (event.key === '/' && document.activeElement !== $('search')) { event.preventDefault(); $('search').focus(); }
  if (event.key === 'Escape' && state.d) update({d: ''});
});
window.addEventListener('popstate', () => { readHash(); render(); });

(async () => {
  readHash();
  $('status').textContent = 'Loading ' + SETTINGS.count.toLocaleString() + ' declarations…';
  const [loaded, reviews, namedFile] = await Promise.all([fetch('data/search.json').then(r => r.json()),
    fetch('reviews.json').then(r => r.json()).catch(() => ({declarations: {}})), fetch('named.json').then(r => r.json()).catch(() => ({declarations: {}}))]);
  index = loaded;
  namedOf = namedFile.declarations || {};
  marks = reviews.declarations || {};
  reviewed = new Set(Object.entries(marks).filter(([, e]) => e.marks.some(m => m.current)).map(([name]) => name));
  flagged = new Set(Object.entries(marks).filter(([, e]) => (e.problems || []).some(p => p.status === 'open')).map(([name]) => name));
  tested = new Set(Object.entries(marks).filter(([, e]) => e.tests && (e.tests.tally.unit || e.tests.tally.results)).map(([name]) => name));
  lower = index.rows.map(r => r[0].toLowerCase());
  leafLower = lower.map(n => n.slice(n.lastIndexOf('.') + 1));
  area = index.rows.map(r => (index.modules[r[2]].split('.')[1] || index.modules[r[2]]));
  rowOf = new Map(index.rows.map((r, i) => [r[0], i]));
  namedLower = index.rows.map(r => { const n = namedOf[r[0]]; return n ? (n.name + ' ' + (n.about || '')).toLowerCase() : ''; });
  const areas = [...new Set(area)].sort();
  $('area-filter').innerHTML = '<option value="">Every area</option>' + areas.map(a => '<option value="' + esc(a) + '">' + esc(a) + '</option>').join('');
  window.TauReview = {state: () => ({...state}), results: () => results.map(i => index.rows[i][0]), ready: false};
  render();
  const loadedDocs = await fetch('data/docs.json').then(r => r.json()).catch(() => null);
  if (loadedDocs) { docs = loadedDocs; docsLower = docs.map(d => d.toLowerCase()); renderResults(); }
  window.TauReview.ready = true;
})();
"""


def page(index: dict, settings: dict, reviews: dict, named_decls: dict) -> str:
    total = len(index["declarations"])
    named_count = len(named_decls)
    entries = reviews["declarations"].values()
    marks = sum(len(e["marks"]) for e in entries)
    open_problems = sum(p["status"] == "open" for e in entries for p in e["problems"])
    config = json.dumps({"repo": settings["repo"], "bulk_issue": settings["bulk_issue"], "count": total, "tauceti": index["tauceti"]})
    config = config.replace("<", "\\u003c")
    bulk = f"https://github.com/{settings['repo']}/issues/{settings['bulk_issue']}"
    legend = "".join(f"<dt>{t}</dt><dd>{m}</dd>" for t, m in MEANING.items())
    repo = html.escape(settings["repo"])
    # Modules that did not build at the pinned commit: the dataset leaves them out, with their
    # declarations and the marks on them, until they build again.
    unavailable = (index.get("dataset") or {}).get("unavailable") or []
    missing = (f" {len(unavailable)} module{'s' if len(unavailable) != 1 else ''} did not build at this commit and "
               f"{'are' if len(unavailable) != 1 else 'is'} left out, with {'their' if len(unavailable) != 1 else 'its'} "
               f"declarations and the marks on them: {', '.join(html.escape(m) for m in unavailable)}.") if unavailable else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reviewed-by marks</title>
<meta name="description" content="Search every Tau Ceti declaration and leave review marks from the browser, without pull requests. A test.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✓</text></svg>">
<style>{STYLE}</style>
</head>
<body>
<header>
  <p class="eyebrow">Test · review marks</p>
  <h1>Reviewed-by for Tau Ceti</h1>
  <p class="lede">Every declaration of Tau Ceti, searchable, with who has checked which and on which version, recorded from the browser without pull requests.</p>
  <p class="meta">Tau Ceti <a href="https://github.com/TauCetiProject/TauCeti/tree/{html.escape(index['tauceti'])}">{html.escape(index['tauceti'][:7])}</a> · {total:,} declarations in {len(index['modules']):,} modules · {named_count:,} named{f" · {marks} review{'s' if marks != 1 else ''}" if marks else ''}{f" · {open_problems} open problem{'s' if open_problems != 1 else ''}" if open_problems else ''}</p>
</header>
<details class="how">
  <summary>How to leave a mark</summary>
  <ol>
    <li>Find the declaration, open it and press <strong>Review this</strong>: a GitHub form opens with its name and the commit shown filled in. Submit it to say it is the intended mathematical notion, and, if you like, what you compared it with and which ways a definition goes wrong you checked. Saying why is optional for people; AI agents must.</li>
    <li>A bot records the review in the evidence store of this repository, answers on the issue and closes it. There is no pull request, and this page updates within a few minutes.</li>
    <li>A review is keyed by the declaration's <em>meaning hash</em>, which changes when the declaration, or anything it rests on, changes meaning, and not when it is renamed, reformatted or re-proved. When it changes, the mark stays but is greyed, as <em>earlier version</em> if the declaration itself was rewritten, or as <em>something it rests on changed since</em> if it reads the same but a definition it uses moved. A renamed declaration keeps its marks. Comment <code>/withdraw</code> on your review's issue to take it back.</li>
    <li>Each declaration counts its reviews, people apart from AI agents; <strong>Who</strong> lists them, with dates, versions and evidence.</li>
    <li><strong>Named</strong> shows only the named results and notable definitions: the ones the roadmaps' status files and Voyager's announcements single out, rather than the API and proof steps around them.</li>
  </ol>
  <p><strong>Tests</strong> are what a declaration passes, rather than a mark: its unit tests (the examples in Tau Ceti that name it), key results listed as its tests with <strong>List a test</strong>, and tests anyone proposes with <strong>Suggest a test</strong>: a property it should have, which stays open until someone proves it in Tau Ceti and comments <code>/met &lt;the declaration that proves it&gt;</code> on its issue (or <code>/failed</code>, if it turns out false: then report the problem). A test passes while it is in Tau Ceti at the pinned commit without <code>sorry</code>. <strong>Which</strong> shows each with its statement.</p>
  <p>If a declaration is wrong, press <strong>Report a problem</strong> instead and say why, and how to fix it if you know. The report is the issue for fixing it: it stays open, and the page flags the declaration, until its reporter or a maintainer closes it as completed (fixed) or as not planned (not a problem), or comments <code>/fixed &lt;commit&gt;</code>, <code>/intended</code> or <code>/invalid</code>.</p>
  <p>Marking many at once: comment lines like <code>Reviewed-by: TauCeti.X.y — what you checked</code>, <code>Test: TauCeti.X.y — TauCeti.X.y_zero — what it checks</code> or <code>Named: TauCeti.X.y — its name — a sentence</code> on <a href="{html.escape(bulk)}">issue #{settings['bulk_issue']}</a>. AI agents use the same routes and name the agent, model and session; their marks are shown apart from people's.</p>
  <dl class="legend">{legend}</dl>
</details>
<div class="bar"><div class="bar-inner">
  <input id="search" type="search" placeholder="Search {total:,} declarations: a name, part of one, or words from a docstring" autocomplete="off" spellcheck="false" aria-label="Search declarations">
  <div class="chips" role="group" aria-label="Kind">
    <button data-group="all" aria-pressed="true">All</button><button data-group="named" aria-pressed="false">Named</button><button data-group="def" aria-pressed="false">Definitions</button><button data-group="thm" aria-pressed="false">Theorems and lemmas</button>
  </div>
  <select id="state-filter" aria-label="Review"><option value="all">Reviewed or not</option><option value="reviewed">Reviewed</option><option value="open">Not yet reviewed</option><option value="tested">Tested</option><option value="problem">Reported problems</option></select>
  <select id="area-filter" aria-label="Area"><option value="">Every area</option></select>
</div></div>
<div class="layout">
  <section aria-label="Results"><p class="status" id="status"></p><div id="results"></div></section>
  <aside class="panel" id="panel" aria-live="polite"></aside>
</div>
<footer>
  <p>The marks as data, for the atlas or Tau Ceti's own documentation: <a href="reviews.json">reviews.json</a>. Everything shown here comes from the <a href="https://github.com/LeanTrustBuilders">LeanTrustBuilders</a> suite: declarations and hashes from a dataset extracted from the compiled library by <a href="https://github.com/LeanTrustBuilders/extractor">trust-extract</a>; reviews, tests, problems and names from the evidence store <a href="https://github.com/{repo}/tree/main/evidence">evidence/</a>, filled from this repository's issues by <a href="https://github.com/LeanTrustBuilders/evidence-store">evidence-store</a>; what applies now computed by <a href="https://github.com/LeanTrustBuilders/evidence-core">evidence-core</a>. In <a href="https://github.com/{repo}">{repo}</a>; nothing here changes Tau Ceti.{missing}</p>
</footer>
<script type="application/json" id="settings">{config}</script>
<script>{SCRIPT}</script>
</body>
</html>
"""


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True, help="the dataset (S2) of the pinned commit")
    parser.add_argument("--store", type=Path, default=ROOT / "evidence", help="the evidence store (S3)")
    args = parser.parse_args()
    index = json.loads((ROOT / "data" / "declarations.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
    ev = Evidence.resolve(Store.load(args.store).records, Dataset.load(args.dataset))
    reviews = data(index, ev)
    named_file = named(index, ev)
    out = ROOT / "site"
    if (out / "data").exists():
        shutil.rmtree(out / "data")
    (out / "data" / "m").mkdir(parents=True)
    compact = {"ensure_ascii": False, "separators": (",", ":")}
    (out / "index.html").write_text(page(index, settings, reviews, named_file["declarations"]), encoding="utf-8")
    (out / "named.json").write_text(json.dumps(named_file, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "data" / "search.json").write_text(json.dumps(search_index(index), **compact), encoding="utf-8")
    (out / "data" / "docs.json").write_text(json.dumps([summary(item["doc"]) for item in index["declarations"]], **compact), encoding="utf-8")
    for n, shard in shards(index).items():
        (out / "data" / "m" / f"{n}.json").write_text(json.dumps(shard, **compact), encoding="utf-8")
    (out / "reviews.json").write_text(json.dumps(reviews, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    entries = reviews["declarations"].values()
    print(f"site: {len(index['declarations'])} declarations in {len(index['modules'])} modules, "
          f"{len(named_file['declarations'])} named, {sum(len(e['marks']) for e in entries)} marks, "
          f"{sum(len(e['problems']) for e in entries)} problem reports, "
          f"{sum(len(e.get('tests', {}).get('results', [])) for e in entries)} listed tests, "
          f"{sum(len(e.get('tests', {}).get('suggested', [])) for e in entries)} proposed tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
