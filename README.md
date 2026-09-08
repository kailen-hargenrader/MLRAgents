# MLRAgents

A GitHub Copilot CLI plugin for machine learning research: agents that know the
difference between a scratch experiment and one whose numbers may reach a paper,
backed by tools that read run provenance and cluster state as facts rather than
guesses.

Status: **phases 0–3 complete** — foundation, the explore/exploit structure,
and the four agents with their skill library (see the
[design spec](docs/superpowers/specs/2026-09-08-mlragents-design.md)). The
registry, scheduler adapters, session-start context, hook dispatch and MCP
server work and are verified against a live cluster and a real 65G research
repository. Phase 4 — `grid_diff`, `paper_build` and the full paper loop — is not built
yet.

## The structure

A project has two experiment trees, and the difference between them is
evidentiary rather than organisational:

```
explore/     insight — may never reach the paper, and is never cited
exploit/     evidence — every quantity in the paper resolves to a run here
paper/       the manuscript
```

**A number in the paper must trace to an `exploit` run.** That is the whole
point of the split. Exploration buys its speed — one seed, a dirty tree, a
hard-coded path — by giving up the right to be cited, and promotion across the
boundary means *re-running* the experiment under exploit-lane conditions.
Artefacts are never copied from `explore/` to `exploit/`; that would launder
their provenance.

Only the explore lane is confined. A `preToolUse` hook refuses writes outside
`explore/` in the explore role, and `mlragents run explore` denies scheduler
submission at launch. The exploit lane is deliberately unguarded, because a
guardrail that fires during ordinary paper work is a guardrail that gets turned
off.

```bash
mlragents init          # scaffold explore/, exploit/, paper/ and the adapter
```

## What it is

Three layers, separated by how often they change and by what happens when they
are wrong:

| Layer | Lives in | Enforcement |
|---|---|---|
| Methodology — how to run an experiment, what to check before launching | `agents/` (4), `skills/` (7) | Persuasion. The model may disagree. |
| Tools — run registry, Slurm queue and history, log triage | `src/mlragents/`, exposed over MCP | Tested facts. |
| Guardrails — what must never happen | `hooks/` | Enforcement. The model gets no vote. |

The rule that decides the layer: anything whose violation would silently corrupt
a paper belongs in a hook, not in a prompt.

**The Python layer never infers what a repository means.** It uses universal
substrates — git, Slurm, SQLite, the filesystem — or it shells out to a command
the repository declared. Nothing is guessed from a directory name. See
[`docs/mlragents-toml.md`](docs/mlragents-toml.md).

## Guardrails

Four, and each one exists because its violation is *silent*: nothing downstream
would report the damage.

| When | What is refused | Override |
|---|---|---|
| `sbatch`/`srun`/`salloc` from a dirty tree | The submission | `MLRAGENTS_ALLOW_DIRTY=1` |
| A write into a declared `paths.generated` tree | The edit; names the generator | change the generator |
| A write outside a role's tree | The edit | run a different role |
| A `.tex` file gains a numeric literal | The turn is blocked for review | use a macro |

A successful submission is recorded automatically with the commit it ran from —
something `sacct` does not know and no later scan can recover.

The gates that protect provenance apply to **every** role, because a dirty run
is unusable to anyone whatever their intent. Role confinement is asymmetric:
`experiment` is unconfined, because a guardrail that fires during ordinary
paper-grade work is a guardrail that gets turned off.

## Install

```bash
copilot plugin marketplace add kailen-hargenrader/MLRAgents
copilot plugin install mlragents@mlragents
```

Direct installs from a local path still work but are deprecated, and they copy
the directory as-is — including a `.venv` if one is present, which turned a 39M
checkout into 170M. Install from a clean clone or from the marketplace.

Then, in a research repository, create `.mlragents.toml`. Start from
[`examples/surf-2026.mlragents.toml`](examples/surf-2026.mlragents.toml), a
working adapter for a Hydra + uv + W&B + Slurm project.

## Use

```bash
mlragents run explore      # cheap model, confined to explore/, no sbatch
mlragents run experiment   # the exploit lane: paper-grade runs
```

Each launches Copilot CLI with that role's agent and limits, and exports
`MLRAGENTS_ROLE` so the hooks know which role is running. The underlying command
is `copilot --agent=mlragents:experiment`; the `mlragents:` prefix is required,
since plugin agents are namespaced and `--agent=experiment` fails with "No such
agent".

Every session opens with a fact block: the current branch, whether the tree is
dirty, and what is actually running on the cluster. It is injected by a
`sessionStart` hook, so it is true regardless of what the model believes.

```bash
mlragents runs sync     # rebuild the registry from both lanes and sacct
```

The registry is a cache and never a source of truth. Every field in it is
recoverable from the lane outputs trees, git and `sacct`, which is what
`runs sync` does. Run ids are lane-qualified — `exploit/ablation/softmax/01-00-00`
— so a citation carries its lane and the two trees cannot collide.

## Develop

```bash
uv run pytest -q
copilot --plugin-dir ~/MLRAgents --agent=mlragents:experiment
```

`--plugin-dir` loads agents, skills and hooks live, with no install. It does
**not** register the bundled MCP server, so pair it with
`--additional-mcp-config @<file>` when changing MCP tools, or test through a
real install.

An agent's `tools` allowlist hides MCP tools unless they are named individually
(`mlragents-jobs_queue`, not `mlragents`). An agent that gains a tool needs that
tool added to its frontmatter, or it will silently be unable to do its job.

## Verification

Claims about the platform are checked against the platform, not against its
documentation, and recorded in [`docs/verification/`](docs/verification/). Several
documented or assumed behaviours turned out to be false; two bugs were found
only by running against a real repository. Read those files before trusting a
design decision that depends on CLI behaviour.
