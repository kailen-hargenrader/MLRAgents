---
name: promoting-an-experiment
description: Use when an explore-lane finding looks worth keeping and should become evidence the paper can cite
---

# Promoting an Experiment

**Core principle:** promotion is a **re-run**, not a move. The explore lane
bought its speed by giving up conditions that make a result citable; you cannot
retroactively buy them back by copying files.

## The iron law

```
NEVER COPY AN ARTEFACT FROM explore/ TO exploit/
```

Not metrics, not checkpoints, not logs, not a figure. A copied artefact carries
an exploit-lane path and explore-lane provenance, and nothing downstream can
tell. That single act defeats the entire structure. If someone asks you to
"just move the results over", they are asking for a re-run.

## The gate

Every item must be true before the exploit-lane run is launched. A "no" is not
a blocker to argue past; it is the work.

- [ ] **Clean working tree.** A result whose code cannot be reconstructed is not
      evidence, however good the number is.
- [ ] **Seed set and logged**, and more than one seed if the claim is a
      comparison between close numbers.
- [ ] **Config generated, not hand-edited.** The config beside the artefacts
      must describe what actually ran.
- [ ] **Comparability argued in writing.** Against what baseline, under what
      held-fixed set? A number with nothing to compare against is not a result.
- [ ] **Cost estimated from a measured rate**, not guessed.
- [ ] **Falsifier stated.** What outcome would kill the claim.

## Procedure

1. Write the finding down as a hypothesis with its falsifier. The explore run is
   now *motivation*, and never gets cited again.
2. Walk the gate above. Fix what fails.
3. Launch in the exploit lane from a clean tree.
4. Record the run. Its id is what the paper will cite.
5. If the re-run disagrees with the exploratory result, **the re-run wins**.
   Say so plainly. This is the case the whole mechanism exists for, and it is
   the moment it is most tempting to go looking for the difference until the
   original number comes back.

## Red flags

| Thought | Reality |
|---|---|
| "It's the same experiment, just copy the numbers" | Then re-running is cheap. Re-run. |
| "The tree is only dirty with unrelated changes" | You cannot know that without checking, and "unrelated" is exactly what a reviewer cannot verify. |
| "One seed was enough to see the effect" | Enough to *see* it. Not enough to report it. |
| "I'll clean up the config after launching" | The config in the outputs directory is now a lie about what ran. |
| "The re-run is worse, the explore run must have had a better setting" | Find the setting, declare it, and re-run again — or report the re-run. Do not report the better number. |
