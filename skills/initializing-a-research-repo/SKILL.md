---
name: initializing-a-research-repo
description: Use when setting up MLRAgents in a repository, writing or fixing .mlragents.toml, or adopting the explore/exploit structure in an existing project
---

# Initializing a Research Repo

**Core principle:** `.mlragents.toml` is a *declaration*, not a detection. Every
field is something the repository asserts about itself. Nothing here may be
inferred from a directory name and left unconfirmed, because a wrong label is
worse than an absent one — it is confidently wrong in a tool that gets cited.

## New repository

```bash
mlragents init --name <project>
```

This creates `explore/`, `exploit/`, `paper/`, `.mlragents.toml` and a
`.gitignore` entry. Then fill in `[commands]`: each tool that needs a command
and cannot find it fails with the name of the missing key rather than guessing.

## Existing repository

Do **not** invent an explore lane that does not exist. A repository whose
experiments all predate the split is honestly described as a single exploit
lane at its root:

```toml
[exploit]
root = "."
outputs = "outputs"
```

Everything already there is treated as evidence, which is the conservative
reading. Adding an `explore/` tree afterwards, for new work only, is a separate
and reversible decision. Retroactively sorting existing runs into lanes means
judging, run by run, which were evidence and which were exploration — that is a
research judgement, not a migration, and it should not be automated.

## Deriving `run_pattern`

The only genuinely tricky field. It tells discovery how a run's path encodes its
experiment, and it must be *checked*, not guessed.

1. List a dozen real run directories. Note their depth — they will not all be
   the same.
2. Identify which components are labels and which are incidental. **A date or a
   timestamp is not a label.** Frameworks like Hydra write
   `outputs/<date>/<name>/[<cell>/…]/<time>`; the date and time carry no meaning
   a table should show.
3. Write the shallow pattern first, then deeper ones. Patterns are tried in
   order, and a deep pattern will happily match a shallow run and record its
   timestamp as a cell name:

   ```toml
   run_pattern = ["*/{grid}/*", "*/{grid}/{cell}/**"]
   ```

4. **Verify against the whole tree.** Run `mlragents runs sync` and check that
   every run got a grid, and that the grids are names you recognise. Grid values
   that look like dates mean the pattern is off by a component.

Confirm each field with the user before writing it. A plausible-looking config
that mislabels runs will not announce itself.

## Checklist

- [ ] `[project] name`, and `python` — how to invoke the environment
      (e.g. `uv run python`), not just `python`.
- [ ] Lanes declared, matching what actually exists on disk.
- [ ] `run_pattern` verified against real paths, not assumed.
- [ ] `[scheduler] kind` and `log_dir`, so job logs can be found by id.
- [ ] `[commands]` for train, collect and paper as they exist today.
- [ ] `mlragents runs sync` produces a sane count and sane labels.
