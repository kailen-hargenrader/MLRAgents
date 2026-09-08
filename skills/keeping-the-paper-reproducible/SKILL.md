---
name: keeping-the-paper-reproducible
description: Use when adding or updating a figure, table or number in the manuscript, or when setting up the paper build
---

# Keeping the Paper Reproducible

**Core principle:** a claim whose script does not run is a claim that does not
exist. Every figure, table and number in the manuscript is produced by the
build, from recorded runs, with no manual step in between.

## The rule

```
NO HAND-TYPED NUMBERS. EVER.
```

Not "for now". Not "just this one, it's from the final run". A typed number is
correct exactly until the experiment is re-run, and nothing will tell you when
it stops being correct — not the compiler, not the tests, not a reader.

## How a number reaches the page

```
exploit-lane run  →  recorded in the registry  →  analysis script
      →  generated macro or table file  →  \input / \ref in the .tex
```

Each arrow is executable. Deleting every generated artefact and running the
paper build must reproduce the PDF exactly. If it does not, something in the
manuscript came from somewhere unrecorded, and that is the thing to find.

## Practices

**One build command rebuilds everything.** Figures, tables, macros, then LaTeX.
If regenerating a figure is a separate thing you have to remember, it will be
stale in the submitted version.

**Generated files are outputs, not sources.** They may be committed for
convenience, but they are never edited. Editing a generated table is
indistinguishable from typing a number.

**Each figure names its runs.** A comment in the script, or better, the run ids
in the generated artefact. Six months later, "which runs is Figure 3?" must have
an answer that is not archaeology.

**Fail loudly on missing inputs.** A plotting script that silently skips an
absent run produces a figure that is missing a line, and it looks fine.

## The audit

Before submission, and any time the manuscript changes substantially:

1. Delete every generated figure, table and macro file.
2. Run the paper build.
3. Diff the PDF against the committed one.
4. Search the `.tex` for numeric literals. Every survivor is either a macro, a
   structural constant (a year, a section number, a hyperparameter that is
   *stated* not *measured*), or a bug.

Undefined references and missing citations are errors. A build that "works with
some warnings" has not been read.

## Red flags

| Thought | Reality |
|---|---|
| "I'll put the real number in later" | It will ship. |
| "The script is slow, I'll paste the output" | Cache the intermediate, not the conclusion. |
| "It's only the abstract" | The abstract is the most-read number in the paper. |
| "I tweaked the generated table to fit the column" | Change the generator's formatting. |
| "The figure is from an old run but the number didn't change much" | Then regenerating is cheap. |
