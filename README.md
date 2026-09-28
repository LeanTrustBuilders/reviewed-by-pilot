# Reviewed-by for Tau Ceti, on the LeanTrustBuilders suite

A fork of [CBirkbeck/tauceti-reviewed-by-test](https://github.com/CBirkbeck/tauceti-reviewed-by-test):
the same page, with every tool behind it replaced by the
[LeanTrustBuilders](https://github.com/LeanTrustBuilders) suite, which works the same way for any
Lean library (the design:
[`suite-design.md`](https://github.com/LeanTrustBuilders/design/blob/main/AI_initial_docs/suite-design.md)).

**Page:** https://leantrustbuilders.github.io/reviewed-by-pilot/

Nothing here changes Tau Ceti, and nothing is posted to it: the page reads Tau Ceti's main branch at
a pinned commit, and every review, test, problem and name is an issue of this repository.

## What replaced what

| | the original | the pilot |
|---|---|---|
| declarations | read from Tau Ceti's sources with regular expressions | a **dataset** (spec [S2](https://github.com/LeanTrustBuilders/specs/blob/main/S2-dataset.md)) extracted from the compiled library by [trust-extract](https://github.com/LeanTrustBuilders/extractor): true names, and the declarations the regexes cannot see (`@[to_additive]` twins, `@[simps]` lemmas, `deriving` instances) |
| what a review is keyed by | a hash of the declaration's text | its **meaning hash** (spec [S1](https://github.com/LeanTrustBuilders/specs/blob/main/S1-declaration-key.md), rule `ltb-meaning/1`), which changes when the declaration **or anything it rests on** changes meaning, and not when it is renamed, reformatted or re-proved |
| forms and the bot | `reviewed-by.yml`, `problem.yml`, `test.yml` and `scripts/reviews.py` | the forms and intake of [evidence-store](https://github.com/LeanTrustBuilders/evidence-store), set up by `evidence-store init` |
| storage | ledgers `reviews/*.jsonl`, one format each | the **evidence store** [`evidence/`](evidence/): records of spec [S3](https://github.com/LeanTrustBuilders/specs/blob/main/S3-evidence.md), append-only, each change checked |
| what applies now | computed by the page's script | [evidence-core](https://github.com/LeanTrustBuilders/evidence-core): whether a review is current, a problem open, a test passing, a proposed test met, and how much of what a named result rests on is reviewed |
| unit tests | the `example`s, found by regular expressions | none: an `example` that names a declaration need not test it |
| proposed tests | suggestion issues | S3 **challenges**: a property the declaration should have, open until a declaration of Tau Ceti proves it |
| named results | a file of the roadmaps' names, and a ledger of Voyager's | S3 `named` records by the roadmap reader and by Voyager, AI agents like any other |

The page's script only turns what evidence-core computes into the files it already read
(`reviews.json`, `named.json`): the search, the panels and their wording are the original's.

## Using it

Every action is a GitHub issue of this repository: the page's buttons open the forms with the
declaration and the pinned commit filled in, and the bot turns the issue into a record, answers,
and rebuilds the page within a few minutes. No pull request.

| on the page | the form | what it records |
|---|---|---|
| **Review this** | [Review a declaration](.github/ISSUE_TEMPLATE/evidence-review.yml) | an acceptance: it is the intended mathematical notion. Saying why is optional for people; AI agents must |
| **Report a problem** | [Report a problem](.github/ISSUE_TEMPLATE/evidence-problem.yml) | a problem: which way it goes wrong (the failure modes F1–F9, a misleading name, something else), why, and a fix if you have one. The issue stays open, and the page flags the declaration, until the problem is resolved |
| **Suggest a test** | [Propose a test](.github/ISSUE_TEMPLATE/evidence-challenge.yml) | a challenge: a property the declaration should have, the Lean statement if you can write it, and what it would catch. It stays open until someone proves it in Tau Ceti |
| **List a test** | [List a test](.github/ISSUE_TEMPLATE/evidence-test.yml) | a test: a declaration of Tau Ceti that pins this one down, and what it checks |
| | [Name a result](.github/ISSUE_TEMPLATE/evidence-named.yml), [Ask a question](.github/ISSUE_TEMPLATE/evidence-question.yml) | a name for a result or notable definition; a question |

Then, on a record's issue, a comment whose first line is a command changes its state:

| command | on | who |
|---|---|---|
| `/withdraw` | anything | its author |
| `/fixed [commit]`, `/intended`, `/invalid` | a problem | its reporter, a maintainer |
| `/met <declaration>` | a proposed test | its author, a maintainer: the declaration that proves it, which the page then checks as a test |
| `/failed`, `/declined` | a proposed test | its author, a maintainer (a property that turns out false is a problem to report) |
| `/answered` | a question | its asker, a maintainer |
| `/reopen` | a problem, proposed test or question | its author, a maintainer |

Closing the issue by hand says the same: a problem closed as completed is fixed, as not planned
invalid; a proposed test closed as completed is met, as not planned declined.

**Many at once**: comment lines on [issue #1](../../issues/1) (label `evidence:bulk`), one record each:

```
Reviewed-by: TauCeti.IdealArithmeticFunction.vonMangoldt — what you checked
Test: TauCeti.IdealArithmeticFunction.vonMangoldt — TauCeti.IdealArithmeticFunction.vonMangoldt_one — the unit ideal gets 0
Challenge: TauCeti.IdealArithmeticFunction.vonMangoldt — it is multiplicative on coprime ideals
Named: TauCeti.LSeries.landau — Landau's theorem — a sentence
```

An AI agent names itself in its comment with `<!-- agent: tool=…; model=…; session=… -->` (the
original's `<!--reviewed-by:v1 {"agent": "…"}-->` works too); its records are shown apart from
people's.

## What the page shows

- **Reviews**, counted people apart from AI agents. A review whose meaning hash no longer matches
  stays, greyed: *earlier version* if the declaration itself changed, *something it rests on changed
  since* if it reads the same but a definition under it moved. A renamed declaration keeps its
  reviews. Reviews made before the rule `ltb-meaning/1` are compared with the hash they were made
  with, which the dataset keeps as `legacy`.
- **Tests**: the key results listed as tests, and the proposed tests met by a declaration. A test passes while it is
  in Tau Ceti at the pinned commit without `sorry`: Lean checks it at every commit, so it does not go
  stale as a review does. The proposed tests still open are listed with them.
- **Problems**, open ones first, each with its issue and how it was resolved.
- **Named** results and notable definitions, from the roadmaps' `STATUS.md` files, Voyager's
  announcements on Zulip, and anyone's `Named:` lines, each with the coverage of what its statement
  rests on: how many of those Tau Ceti declarations people have reviewed, and counting AI agents.

`reviews.json` and `named.json` carry the same, for other readers (the atlas, Tau Ceti's docs).

## How the pieces fit

1. **[Follow Tau Ceti](.github/workflows/refresh.yml)**, daily: moves the pin in
   `data/settings.json` to the newest commit of main that the extractor has a release for and Tau
   Ceti's cache has built; runs **[Dataset](.github/workflows/dataset.yml)** for it, which fetches
   Tau Ceti and Mathlib from their caches, runs trust-extract, and publishes the
   dataset as the release `dataset-<commit>` of this repository; then records the named results
   ([`scripts/named.py`](scripts/named.py)): the roadmaps' as they stand today (a name the roadmaps
   drop is withdrawn), and Voyager's announcements whose declaration has reached the pin. Voyager's
   announcements are kept in [`data/voyager.jsonl`](data/voyager.jsonl), since reading Zulip takes an
   account: `named.py voyager <export.json>` adds those of an export of its topic.
2. **[Evidence intake](.github/workflows/evidence-intake.yml)**, on every issue event and every six
   hours: evidence-store's intake keys each record in the dataset of the commit its form names and
   appends it to `evidence/`. **[Evidence check](.github/workflows/evidence-check.yml)** checks every
   change to the store.
3. **[Page](.github/workflows/pages.yml)**, after either: reads the pinned dataset into
   `data/declarations.json` ([`scripts/dataset_declarations.py`](scripts/dataset_declarations.py)),
   asks evidence-core what applies now, and builds the page
   ([`scripts/build_site.py`](scripts/build_site.py)).

The reviews and tests made on the original page were carried over as S3 records, keyed in datasets
of the commits they were made at; they still link to the original repository's issues.

## In the code: the fork

As in the original, [`scripts/apply.py`](scripts/apply.py) writes the counts into a **fork** of Tau
Ceti's sources, never Tau Ceti itself: a line under each module docstring's title linking to the
file's page, and the counts at the end of each reviewed declaration's docstring, from the page's
`reviews.json`. It finds the declarations in the fork's files with
[`scripts/lean_source.py`](scripts/lean_source.py), since the fork's lines are not the pinned
commit's. The commit ends in one git trailer per review, as the kernel's `b4 trailers -u` collects
Reviewed-by replies.

## Files

- `scripts/dataset_declarations.py` reads a dataset into `data/declarations.json` (generated, not
  committed).
- `scripts/build_site.py` builds the page: `index.html`; `data/search.json` and `data/docs.json`,
  which it loads first; one file per module in `data/m/`, read when a declaration is opened;
  `reviews.json` and `named.json`.
- `scripts/named.py` records the named results; `scripts/apply.py` and `scripts/lean_source.py`
  write the lines into a fork.
- `evidence/` is the evidence store; `.github/ISSUE_TEMPLATE/evidence-*.yml` and
  `.github/workflows/evidence-*.yml` are evidence-store's, regenerated by `evidence-store init`.
- `python3 -m unittest discover -s tests` runs the tests (with evidence-core installed);
  `python3 tests/validate_site.py` checks the built page in a browser.
