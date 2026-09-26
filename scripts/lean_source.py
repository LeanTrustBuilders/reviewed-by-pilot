"""Where Tau Ceti's declarations are in a checkout's Lean sources, for apply.py.

apply.py writes the review lines into the files of a fork, whose lines are not the pinned commit's
(the lines it wrote last time are there too), so it finds each declaration by reading the files
rather than from the dataset: its full name, kind, the keyword it is written with, its lines and its
docstring. Private declarations are left out: nobody reviews them from the page.
"""
from __future__ import annotations

import re
from pathlib import Path

KEYWORDS = r"class\s+inductive|def|theorem|lemma|abbrev|structure|class|inductive|instance"
DECLARATION = re.compile(r"^(?:@\[[^\]]*\]\s*)*(?P<mods>(?:(?:private|protected|noncomputable|nonrec|partial|unsafe|scoped)\s+)*)"
                         r"(?P<kind>" + KEYWORDS + r")\s+(?P<name>[^\s:({\[⦃]+)")
EXAMPLE = re.compile(r"^(?:@\[[^\]]*\]\s*)*(?:(?:private|noncomputable)\s+)*example\b")
NAMESPACE = re.compile(r"^namespace\s+(\S+)")
SECTION = re.compile(r"^(?:@\[[^\]]*\]\s*)?(?:(?:noncomputable|public|private)\s+)*section\b")
END = re.compile(r"^end\b")
ATTRIBUTE = re.compile(r"^\s*@\[[^\]]*\]\s*$")
KIND = {"def": "def", "abbrev": "def", "theorem": "theorem", "lemma": "theorem", "structure": "structure", "class": "class",
        "class inductive": "class", "inductive": "inductive", "instance": "instance"}


def comment_end(lines: list, i: int) -> int:
    """The line after the block comment that starts on line i. Lean's block comments nest."""
    depth = 0
    for j in range(i, len(lines)):
        line, k = lines[j], 0
        while k < len(line):
            if line.startswith("/-", k):
                depth, k = depth + 1, k + 2
            elif line.startswith("-/", k):
                depth, k = depth - 1, k + 2
                if depth == 0:
                    return j + 1
            else:
                k += 1
    return len(lines)


def declarations(source: str, path: str) -> list:
    """The declarations of a module."""
    lines = source.splitlines()
    scopes, found, doc = [], [], None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("/-") and not line.startswith("/--"):
            # A comment or a module docstring: nothing in it is a declaration.
            i = comment_end(lines, i)
            continue
        if line.startswith("/--"):
            start = i
            while "-/" not in lines[i]:
                i += 1
            text = "\n".join(lines[start:i + 1])
            doc = (text[3:text.rindex("-/")].strip(), i)
            i += 1
            continue
        if NAMESPACE.match(line):
            scopes.append(NAMESPACE.match(line).group(1).split("."))
        elif SECTION.match(line) or line.startswith("mutual"):
            scopes.append([])
        elif END.match(line) and scopes:
            scopes.pop()
        match = DECLARATION.match(line)
        if match or EXAMPLE.match(line):
            start = i
            i += 1
            # A declaration runs until the next line that starts at the margin.
            while i < len(lines) and (not lines[i] or lines[i][0].isspace() or lines[i].startswith(("deriving", "|"))):
                i += 1
            end = start + len("\n".join(lines[start:i]).rstrip().splitlines())
            attached = doc and all(ATTRIBUTE.match(lines[k]) or not lines[k].strip() for k in range(doc[1] + 1, start))
            if match and "private" not in match.group("mods").split():
                name = match.group("name")
                prefix = [part for scope in scopes for part in scope]
                keyword = " ".join(match.group("kind").split())
                found.append({"name": name[len("_root_."):] if name.startswith("_root_.") else ".".join(prefix + [name]),
                              "kind": KIND[keyword], "keyword": keyword, "module": path[:-len(".lean")].replace("/", "."),
                              "path": path, "line": start + 1, "end": end, "doc": doc[0] if attached else ""})
            doc = None
            continue
        i += 1
    return found


def read_clone(root: Path) -> dict:
    """Every module under TauCeti/ in a checkout, and its declarations."""
    modules, found = [], []
    for file in sorted((root / "TauCeti").rglob("*.lean")):
        path = file.relative_to(root).as_posix()
        these = declarations(file.read_text(encoding="utf-8", errors="replace"), path)
        modules.append({"module": path[:-len(".lean")].replace("/", "."), "path": path, "declarations": len(these)})
        found += these
    return {"modules": modules, "declarations": found}
