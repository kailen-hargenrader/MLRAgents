---
name: designing-an-ablation
description: Use before launching any grid, sweep or multi-cell experiment, when deciding what to vary and what to hold fixed
---

# Designing an Ablation

**Core principle:** an ablation varies one axis. Everything a reader could
blame the difference on instead must be held fixed, and written down as held
fixed.

## The rule

```
ONE AXIS. STATE THE FALSIFIER BEFORE LAUNCHING.
```

If you cannot say what outcome would make the hypothesis wrong, you are not
running an experiment; you are producing an illustration.

## Before launch, write these four things

1. **The axis.** The one thing that differs between cells. Name it.
2. **The held-fixed set.** Seed, data, optimiser, schedule, initialisation,
   parameter count, and — if you will report timings — the device. A grid split
   across an A100 and an H100 has two axes.
3. **The falsifier.** "If the kernels are within noise of each other, the
   hypothesis is dead." Write the number.
4. **Why each cell exists.** A cell that answers no question is cost, and its
   presence invites a post-hoc story.

Do not launch until all four exist. This costs ten minutes and is the only
cheap moment to notice the grid answers a different question than intended.

## Structure

**Every cell descends from one parent config.** Shared settings are written
once. When cells are independent files, they drift, and the drift is invisible:
the diff that matters is between a cell and its siblings, not between a cell and
what you remember writing.

**Generate the cells; never hand-write them.** A generator makes the axis
mechanical — the difference between two cells is exactly what the generator
varied. Hand-editing one cell to fix something is how a second axis enters an
ablation without anyone deciding to add it.

**Name cells after what they are, not when they ran.** A directory named for a
timestamp carries no information a reader or a tool can use.

## Cost, before submitting

Estimate from a measured rate, not a guess: run one cell, time it, multiply.
A grid whose cost was guessed is a grid that gets cancelled halfway, and half a
grid answers nothing.

## Comparability traps

- **Saturation.** If a metric is at its floor or ceiling for every cell, the
  grid cannot separate them. Check one cell's final value against the metric's
  bound before launching the rest.
- **Unidentifiable targets.** A target with a symmetry the model cannot break
  produces a flat comparison regardless of the axis. Fix the target so the
  quantity under test is identifiable.
- **Scores from different grids are not comparable** unless the parent config
  and target are the same. Two grids differing in a "small" setting do not
  produce numbers that belong in one table.

## Red flags

| Thought | What it means |
|---|---|
| "I'll add the other variant while I'm at it" | Second axis. Separate grid. |
| "This cell needs a slightly different learning rate" | The axis is now confounded with the learning rate. |
| "I'll decide what to measure once it finishes" | The falsifier will be chosen to fit the result. |
| "Timings vary a bit because of the queue" | Fix the device, or do not report timings. |
