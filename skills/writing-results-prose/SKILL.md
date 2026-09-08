---
name: writing-results-prose
description: Use when writing or editing any prose that reports experimental results, in a paper, report or summary
---

# Writing Results Prose

**Core principle:** report what was observed in the runs tested. Everything
beyond that — mechanism, generality, cause — is a separate claim that needs its
own evidence.

## Voice

Terse and formal. No first person. No editorialising.

| Instead of | Write |
|---|---|
| "We can see that the loss drops" | "The loss decreases" |
| "The inputs we care about" | "The inputs" |
| "Interestingly, performance improves" | "Performance improves" |
| "This nicely demonstrates" | "This shows" — or delete the sentence |
| "It is worth noting that" | *(delete)* |

Cut every phrase that comments on the result rather than stating it. If a
sentence would survive with its first clause removed, remove it.

## Hedging causal claims

State the observation, scoped to what was run. Do not assert a mechanism.

- No: "the higher growth rate causes the instability."
- Yes: "in the runs tested, cells with higher growth rate diverged more often."

- No: "prenorm is more stable."
- Yes: "prenorm reached a lower final loss in every configuration tested."

Scope explicitly when the evidence is thin: "in the single run tested", "across
the three seeds run", "for the kernels tested". A reader can discount a scoped
claim; an unscoped one they can only disbelieve entirely.

**"because" is a load-bearing word.** Using it asserts a mechanism was measured.
If the experiment varied one axis and observed a difference, you may say the
difference accompanied the axis. You may not say the axis produced it unless
the held-fixed set rules out the alternatives — and then say which alternatives.

## Numbers

Never type a number into prose. Every quantity is a macro or comes from a
generated table, so that re-running the experiment updates the manuscript and a
number no script produced cannot exist. If the quantity you want has no macro,
say which one is missing rather than reading it off a log.

## Structure of a results paragraph

1. What was varied and what was held fixed.
2. What was observed, with the statistic named.
3. Where it does not hold — the cells that disagree, the failures, the n.
4. Stop. Interpretation belongs in the discussion, and it is a different claim.

## Red flags

| Phrase | Problem |
|---|---|
| "significantly" | Statistical term. Only with a test. |
| "consistently" | Only with the number of runs it was consistent across. |
| "as expected" | Says nothing, and pre-commits the reader. |
| "slightly worse but" | The "but" is doing the work the evidence should. |
| "generally", "tends to" | Unfalsifiable. Give the count. |
