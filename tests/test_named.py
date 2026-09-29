"""The named results and definitions: harvested from the roadmaps and from Voyager, and recorded
in the evidence store (scripts/named.py)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_core import records as rec  # noqa: E402
from evidence_core.store import Store, default_config  # noqa: E402
from named import add_announcements, sync_roadmaps, sync_voyager, roadmap_names, voyager_names  # noqa: E402
import mini  # noqa: E402

DOCS = "https://taucetiproject.github.io/TauCeti/docs/TauCeti/NumberTheory"
STATUS = f"""# Status: ArithmeticDirichletSeries

## Where this roadmap stands

### Named results

- **Landau's theorem** — a Dirichlet series with nonnegative coefficients admits no continuation across its abscissa ([`TauCeti.LSeries.landau`]({DOCS}/LSeries/Landau.html#TauCeti.LSeries.landau)), now with its corollary ([`TauCeti.LSeries.meromorphicOrderAt_lt_zero_of_eq_LSeries`]({DOCS}/LSeries/Landau.html#TauCeti.LSeries.meromorphicOrderAt_lt_zero_of_eq_LSeries)).

### Notable definitions and infrastructure

- **Euler-product data** — the package the export contract names ([`TauCeti.EulerProductData`]({DOCS}/EulerProduct/Data.html#TauCeti.EulerProductData)).

### Roadmap coverage

- **Not a result** — layers 0 to 5 are done ([`TauCeti.Nope`]({DOCS}/Nope.html#TauCeti.Nope)).

## The frontier

- **Wiener–Ikehara** — what remains is the sharp cutoff.
"""

POST = f"""**Voyager · what's new in Tau Ceti** *(AI-generated summary)*

*Named results*
- **[Landau's theorem]({DOCS}/LSeries/Landau.html#TauCeti.LSeries.landau)** — no continuation across the abscissa (Landau 1905). (TauCeti#7001)
- **[Rouché's theorem]({DOCS}/Rouche.html#TauCeti.rouche)**† — equal zero counts under domination. (TauCeti#7002, TauCeti#7010)

*Notable definitions*
- **[The ideal von Mangoldt function]({DOCS}/VonMangoldt.html#TauCeti.IdealArithmeticFunction.vonMangoldt)** — log N(P) on prime powers. (TauCeti#6990)

† = also being formalised in Mathlib.
"""



class Roadmaps(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        (root / "TauCetiRoadmap" / "ArithmeticDirichletSeries").mkdir(parents=True)
        (root / "TauCetiRoadmap" / "ArithmeticDirichletSeries" / "STATUS.md").write_text(STATUS, encoding="utf-8")
        self.found = roadmap_names(root)

    def tearDown(self):
        self.folder.cleanup()

    def test_named_results_and_notable_definitions_are_read_with_every_declaration_they_link(self):
        self.assertEqual([(n["decl"], n["name"], n["what"]) for n in self.found], [
            ("TauCeti.LSeries.landau", "Landau's theorem", "result"),
            ("TauCeti.LSeries.meromorphicOrderAt_lt_zero_of_eq_LSeries", "Landau's theorem", "result"),
            ("TauCeti.EulerProductData", "Euler-product data", "definition")])

    def test_each_keeps_its_sentence_without_the_links_and_its_roadmap(self):
        first = self.found[0]
        self.assertEqual(first["about"], "a Dirichlet series with nonnegative coefficients admits no continuation across its abscissa, "
                                         "now with its corollary.")
        self.assertEqual(first["source"], {"roadmap": "ArithmeticDirichletSeries",
                                           "path": "TauCetiRoadmap/ArithmeticDirichletSeries/STATUS.md"})


class Voyager(unittest.TestCase):
    def test_each_announcement_names_a_declaration(self):
        found = voyager_names([{"id": 614, "timestamp": 1790000000, "content": POST}])
        self.assertEqual([(n["decl"], n["name"], n["what"]) for n in found], [
            ("TauCeti.LSeries.landau", "Landau's theorem", "result"),
            ("TauCeti.rouche", "Rouché's theorem", "result"),
            ("TauCeti.IdealArithmeticFunction.vonMangoldt", "The ideal von Mangoldt function", "definition")])
        self.assertEqual(found[1]["source"], {"voyager": 614, "prs": [7002, 7010]})
        self.assertEqual(found[1]["about"], "equal zero counts under domination.")
        self.assertEqual(found[1]["at"], "2026-09-21T14:13:20Z")


class Recorded(unittest.TestCase):
    """What the roadmaps and Voyager name becomes `named` records in the store, keyed in the dataset."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.ds = mini.dataset(root / "ds")
        self.store = Store.init(root / "evidence", default_config("LeanTrustBuilders/reviewed-by-pilot", "TauCeti", "Tau Ceti"))
        self.entries = [
            {"decl": "TauCeti.X.f_one", "name": "The value of f", "what": "result", "about": "f is one.",
             "source": {"roadmap": "Functions", "path": "TauCetiRoadmap/Functions/STATUS.md"}},
            {"decl": "TauCeti.Y.g", "name": "The map g", "what": "definition", "about": "",
             "source": {"roadmap": "Maps", "path": "TauCetiRoadmap/Maps/STATUS.md"}},
            {"decl": "TauCeti.Gone", "name": "Gone", "what": "result", "about": "", "source": {"roadmap": "Maps", "path": "p"}}]

    def tearDown(self):
        self.folder.cleanup()

    def test_each_roadmap_entry_is_recorded_once(self):
        added, gone = sync_roadmaps(self.store, self.entries, self.ds, "2026-09-25T00:00:00Z")
        self.assertEqual(([r["subject"]["name"] for r in added], gone), (["TauCeti.X.f_one", "TauCeti.Y.g"], []))
        self.assertEqual((added[0]["name"], added[0]["text"], added[0]["by"]["agent"]["tool"]),
                         ("The value of f", "f is one.", "Tau Ceti roadmap reader"))
        self.assertEqual(added[0]["reference"], {"text": "the Functions roadmap", "url":
                         "https://github.com/TauCetiProject/TauCetiRoadmap/blob/main/TauCetiRoadmap/Functions/STATUS.md"})
        self.assertNotIn("text", added[1])
        self.store.add(added)
        self.assertEqual(sync_roadmaps(self.store, self.entries, self.ds, "2026-09-26T00:00:00Z"), ([], []))

    def test_an_entry_a_roadmap_no_longer_lists_is_withdrawn(self):
        self.store.add(sync_roadmaps(self.store, self.entries, self.ds, "2026-09-25T00:00:00Z")[0])
        added, gone = sync_roadmaps(self.store, self.entries[:1], self.ds, "2026-09-26T00:00:00Z")
        self.assertEqual(added, [])
        [status] = gone
        self.assertEqual((status["state"], status["target"]),
                         ("withdrawn", next(r["id"] for r in self.store.records if r["subject"]["name"] == "TauCeti.Y.g")))
        self.store.add(gone)
        self.assertEqual(sync_roadmaps(self.store, self.entries[:1], self.ds, "2026-09-27T00:00:00Z"), ([], []))
        # Listed again: recorded again.
        self.assertEqual([r["subject"]["name"] for r in sync_roadmaps(self.store, self.entries, self.ds, "2026-09-28T00:00:00Z")[0]],
                         ["TauCeti.Y.g"])

    def test_an_announcement_is_recorded_once_its_declaration_is_at_the_pin(self):
        docs = "https://taucetiproject.github.io/TauCeti/docs/X.html"
        post = {"id": 614, "timestamp": 1790000000, "content":
                f"- **[The value of f]({docs}#TauCeti.X.f_one)** — one. (TauCeti#7001)\n"
                f"- **[Not merged yet]({docs}#TauCeti.X.later)** — later. (TauCeti#7002)"}
        entries = add_announcements([], [post])
        self.assertEqual([e["decl"] for e in entries], ["TauCeti.X.f_one", "TauCeti.X.later"])
        self.assertEqual(add_announcements(entries, [post]), [])
        [r] = sync_voyager(self.store, entries, self.ds)
        self.assertEqual(rec.validate(r), [])
        self.assertEqual((r["subject"]["name"], r["by"]["agent"]["tool"], r["at"], r["reference"], r["origin"]["ref"]),
                         ("TauCeti.X.f_one", "Voyager", "2026-09-21T14:13:20Z", {"text": "Voyager, TauCeti#7001"}, "voyager 614"))
        self.store.add([r])
        self.assertEqual(sync_voyager(self.store, entries, self.ds), [])


if __name__ == "__main__":
    unittest.main()
