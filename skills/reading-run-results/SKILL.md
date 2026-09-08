---
name: reading-run-results
description: Use when interpreting finished runs, comparing cells of a grid, or deciding whether a difference is real
---

# Reading Run Results

**Core principle:** choose the summary statistic **before** looking at the
numbers. Every degree of freedom you keep until after you have seen the data is
a degree of freedom you will spend, unconsciously, on the answer you expected.

## Order of operations

1. **Decide what you are measuring.** Final value, best value, mean over the
   last N steps, area under the curve — pick one and say why.
2. **Decide what "different" means.** A threshold, or a spread across seeds.
3. *Then* look.

## Before comparing anything

**Check convergence, per cell.** A comparison between one converged run and one
still descending measures the training budget, not the axis.

**Check for saturation.** If every cell sits at the metric's floor or ceiling,
the grid has no resolving power. Report that the comparison is uninformative —
this is a real finding about the setup, and reporting it is much better than
ranking noise.

**Check the runs came from the same grid.** Two grids with different targets or
parents produce numbers that must not share a table, however similar the column
headings look.

**Check the lane.** Only exploit-lane runs are evidence. An explore run may
motivate a claim; it may never support one.

## Reporting

**Report the alternative statistic when the verdict depends on it.** If A beats
B on final loss but B beats A on best-so-far, that is the result: the ordering
is not robust. Silently picking the statistic that produces a cleaner story is
the most common way an honest person publishes a wrong claim.

**Report n.** One seed is one sample. Say "in the single run tested".

**Report the failures.** Cells that diverged, OOMed or were preempted are part
of the grid. A table showing only the cells that finished is a filtered table.

## Language

Describe what was observed in the runs tested. Do not assert a mechanism.

- Yes: "the log-domain kernel reached a lower final loss in every cell tested."
- No: "the log-domain kernel is more stable, which is why it converges better."

The second sentence contains a causal claim, a mechanism and a generalisation,
none of which were measured.

## Red flags

| Thought | What it means |
|---|---|
| "Let me check whether the mean or the median looks better" | You are choosing the statistic from the answer. |
| "That cell is an outlier" | Say why it is excluded, before excluding it, or keep it. |
| "It's clearly better, the gap is big" | Big relative to what spread? You have one seed. |
| "The trend is obvious even though one cell disagrees" | Report the disagreeing cell. |
