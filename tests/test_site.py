"""The page (scripts/build_site.py): what it shows of each declaration, computed from the evidence
store (S3) against the dataset (S2) by evidence-core."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import data, named, page, search_index, shards, summary  # noqa: E402
from evidence_core import Evidence  # noqa: E402
from evidence_core import records as rec  # noqa: E402
import mini  # noqa: E402
from mini import INDEX, SETTINGS, agent, person, record, status  # noqa: E402


def rekeyed(r: dict, subject: dict) -> dict:
    """A record about another version of its declaration."""
    out = {k: v for k, v in r.items() if k != "id"}
    out["subject"] = {**out["subject"], **subject}
    return rec.with_id(out)


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        ds = mini.dataset(Path(cls.tmp.name) / "ds")
        f, g = "TauCeti.X.f", "TauCeti.Y.g"
        alice = record(ds, "review", f, person("alice"), "2026-09-21T15:10:00Z", 3, verdict="accept", text="Matches Neukirch.")
        # Made on an earlier version of f: another meaning and local hash.
        bob = record(ds, "review", f, agent("bob"), "2026-09-20T10:00:00Z", 5, verdict="accept", text="Checked.")
        bob = rekeyed(bob, {"hashes": {"meaning": "0" * 16, "local": "9" * 16}})
        # Keyed by semantic_hash's hashes (S1 version 0), which datasets no longer carry: incomparable.
        dave = record(ds, "review", f, person("dave"), "2026-09-19T10:00:00Z", 4, verdict="accept")
        dave = rekeyed(dave, {"hashes": {"meaning": "a0a0a0a0a0a0a0a0", "local": "1111111111111111"},
                              "hasher": {"name": "semantic_hash", "revision": "r", "local": "ltb-local-v1"}})
        carol = record(ds, "review", g, person("carol"), "2026-09-21T11:00:00Z", 6, verdict="accept")
        p1 = record(ds, "review", g, person("alice"), "2026-09-22T15:00:00Z", 12, verdict="problem",
                    category="F3", text="It should be 3.", fix="def g := 3")
        p2 = record(ds, "review", f, agent("bob"), "2026-09-20T10:00:00Z", 13, verdict="problem",
                    category="naming", text="The docstring says two.")
        c1 = record(ds, "challenge", g, person("frank"), "2026-09-23T10:00:00Z", 30, text="`g = 2`", catches="an off-by-one")
        c2 = record(ds, "challenge", f, person("frank"), "2026-09-23T10:00:00Z", 31, text="`f = 1`", statement="f = 1")
        cls.records = [
            alice, bob, dave, carol, status(carol, "withdrawn", person("carol"), "2026-09-21T12:00:00Z"),
            p1, p2, status(p2, "fixed", person("carol"), "2026-09-21T10:00:00Z", commit="0123abcd4567"),
            record(ds, "test", g, person("erin"), "2026-09-22T10:00:00Z", 20, test={"name": "TauCeti.Y.g_bad"}, text="g is 2"),
            record(ds, "test", f, agent("op", tool="Claude Code"), "2026-09-22T10:00:00Z", 21,
                   test={"name": "TauCeti.X.f_one"}, text="f is 1"),
            record(ds, "test", f, person("erin"), "2026-09-22T10:00:00Z", 22, test={"name": "TauCeti.X.gone"}, text="renamed since"),
            c1, c2, status(c2, "met", person("frank"), "2026-09-23T12:00:00Z", test={"name": "TauCeti.X.f_one"}),
            record(ds, "named", "TauCeti.X.f_one", agent("github-actions[bot]", tool="Tau Ceti roadmap reader"),
                   "2026-09-20T00:00:00Z", name="The value of f", what="result", text="f is one.",
                   reference={"text": "the Functions roadmap", "url": "https://example.org/Functions/STATUS.md"})]
        for r in cls.records:
            assert not rec.validate(r), (r, rec.validate(r))
        cls.ev = Evidence.resolve(cls.records, ds)
        cls.out = data(INDEX, cls.ev)["declarations"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_marks_are_current_or_on_an_earlier_version(self):
        marks = {m["by"]: m for m in self.out["TauCeti.X.f"]["marks"]}
        self.assertEqual({by: (m["current"], m["status"]) for by, m in marks.items()},
                         {"alice": (True, "current"), "dave": (False, "incomparable"), "bob": (False, "stale")})
        self.assertEqual(marks["alice"]["url"], f"https://github.com/{SETTINGS['repo']}/issues/3")
        self.assertEqual(self.out["TauCeti.X.f"]["tally"], {"Reviewed-by": {"people": 1, "ai": 0, "earlier": 2}})

    def test_a_withdrawn_review_is_not_shown(self):
        self.assertEqual(self.out["TauCeti.Y.g"]["marks"], [])

    def test_a_problem_is_open_until_a_status_resolves_it(self):
        [report] = self.out["TauCeti.Y.g"]["problems"]
        self.assertEqual((report["status"], report["what"], report["why"], report["fix"], report["issue"]),
                         ("open", "F3", "It should be 3.", "def g := 3", 12))
        [fixed] = self.out["TauCeti.X.f"]["problems"]
        self.assertEqual((fixed["status"], fixed["closedBy"], fixed["commit"], fixed["kind"]), ("fixed", "carol", "0123abcd4567", "agent"))

    def test_a_test_passes_while_it_is_in_tau_ceti_without_sorry(self):
        f = self.out["TauCeti.X.f"]["tests"]
        self.assertEqual([(u["statement"], u["passes"]) for u in f["unit"]], [("example : f = 1", True)])
        self.assertEqual(sorted((r["test"], r["status"], "challenge" in r) for r in f["results"]),
                         [("TauCeti.X.f_one", "passes", False), ("TauCeti.X.f_one", "passes", True), ("TauCeti.X.gone", "missing", False)])
        self.assertEqual(f["tally"], {"unit": 1, "results": 2, "suggested": 0})
        g = self.out["TauCeti.Y.g"]["tests"]
        self.assertEqual([(r["test"], r["status"]) for r in g["results"]], [("TauCeti.Y.g_bad", "sorry")])
        self.assertEqual(g["tally"], {"unit": 0, "results": 0, "suggested": 1})

    def test_a_proposed_test_is_open_until_a_declaration_meets_it(self):
        [met] = self.out["TauCeti.X.f"]["tests"]["suggested"]
        self.assertEqual((met["status"], met["metBy"], met["statement"], met["closedBy"]), ("written", "TauCeti.X.f_one", "f = 1", "frank"))
        [proposed] = self.out["TauCeti.Y.g"]["tests"]["suggested"]
        self.assertEqual((proposed["status"], proposed["test"], proposed["catches"], proposed["issue"]),
                         ("open", "`g = 2`", "an off-by-one", 30))

    def test_a_named_result_carries_its_name_source_and_coverage(self):
        found = named(INDEX, self.ev)["declarations"]
        self.assertEqual(list(found), ["TauCeti.X.f_one"])
        entry = found["TauCeti.X.f_one"]
        self.assertEqual((entry["name"], entry["what"], entry["about"]), ("The value of f", "result", "f is one."))
        self.assertEqual(entry["sources"][0]["reference"], {"text": "the Functions roadmap", "url": "https://example.org/Functions/STATUS.md"})
        # It rests on itself and f: f has a current review by a person, f_one none.
        self.assertEqual(entry["coverage"], {"members": 2, "people": 1, "any": 1, "problems": 0, "upstream": 0})

    def test_the_page_opens_the_evidence_forms_filled_in(self):
        html = page(INDEX, SETTINGS, data(INDEX, self.ev), named(INDEX, self.ev)["declarations"])
        # The forms are evidence-store's.
        for kind in ("review", "challenge", "problem", "test"):
            self.assertIn(f'"{kind}": "evidence-{kind}.yml"', html)
        self.assertIn("decl: name, commit: SETTINGS.tauceti", html)
        self.assertIn("4 declarations in 2 modules · 1 named · 3 reviews · 1 open problem", html)
        self.assertIn('"repo": "LeanTrustBuilders/reviewed-by-pilot"', html)

    def test_settings_cannot_close_the_script(self):
        html = page(INDEX, dict(SETTINGS, repo="</script><script>alert(1)</script>"), {"declarations": {}}, {})
        self.assertNotIn("</script><script>alert(1)", html)


class Index(unittest.TestCase):
    def test_every_declaration_is_a_row_of_the_search_index(self):
        found = search_index(INDEX)
        self.assertEqual(found["modules"], ["TauCeti.NumberTheory.X", "TauCeti.Algebra.Y"])
        keywords = found["keywords"]
        self.assertEqual([(row[0], keywords[row[1]], found["modules"][row[2]], row[3]) for row in found["rows"]][:3],
                         [("TauCeti.X.f", "abbrev", "TauCeti.NumberTheory.X", 3), ("TauCeti.X.f_one", "lemma", "TauCeti.NumberTheory.X", 6),
                          ("TauCeti.Y.g", "def", "TauCeti.Algebra.Y", 1)])

    def test_a_summary_is_the_first_sentence_of_the_docstring_in_plain_text(self):
        self.assertEqual(summary("The **function** `f`. It is one."), "The function f.")
        self.assertEqual(summary(""), "")
        self.assertTrue(len(summary("word " * 100)) <= 121)

    def test_each_module_has_a_file_with_its_declarations_in_full(self):
        found = shards(INDEX)
        self.assertEqual(sorted(found), [0, 1])
        self.assertEqual([d["name"] for d in found[0]["declarations"]], ["TauCeti.X.f", "TauCeti.X.f_one"])
        self.assertEqual(found[0]["declarations"][0]["source"], "abbrev f := 1")
        self.assertEqual(found[0]["summary"], "About X.")


if __name__ == "__main__":
    unittest.main()
