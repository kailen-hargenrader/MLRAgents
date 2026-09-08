# MLRAgents

A GitHub Copilot CLI plugin for machine learning research: agents that know the
difference between a scratch experiment and one whose numbers may reach a paper,
backed by tools that read run provenance and cluster state as facts rather than
guesses.

Status: **phases 0–4 complete** — foundation, the explore/exploit structure,
the four agents with their skill library, the guardrails, and the paper loop
(see the
[design spec](docs/superpowers/specs/2026-09-08-mlragents-design.md)). The
registry, scheduler adapters, session-start context, hook dispatch and MCP
server work and are verified against a live cluster and a real 65G research
repository.

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

See [Starting a new project](#starting-a-new-project) for the full walkthrough
from an empty directory.

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

## Tools

Twelve, over MCP. Each is either universal or a passthrough to a command the
project declared.

| Tool | Answers |
|---|---|
| `runs_list`, `runs_get` | what has been run, and with what provenance |
| `runs_provenance` | **may the paper cite this run**, and if not, what disqualifies it |
| `lanes_list` | which trees exist and which of them is citable |
| `jobs_queue`, `jobs_history` | what is queued, what finished, and how |
| `jobs_logs` | the tails of a job's `.out`/`.err` plus the first error line |
| `jobs_submit` | submit *and* record the commit in one step; refuses when it cannot |
| `grid_diff` | do these two cells differ **only** along the declared axis |
| `collect_results` | `commands.collect` |
| `paper_build` | `commands.paper`, with errors, undefined refs and undefined citations extracted from the log |
| `paper_audit_numbers` | which numbers in the `.tex` are not carried by a macro |

`jobs_submit` is listed only by the `experiment` agent. The other three roles
launch with `--deny-tool=shell(sbatch:*)`, and a submitting tool in their
allowlists would route straight around that.

`grid_diff` is the ablation invariant made mechanical. Two cells that differ in
two places support no claim about either, and that is not visible by reading
two YAML files side by side.

## Requirements

| | Needed for | If absent |
|---|---|---|
| **GitHub Copilot CLI** | everything — this is a plugin, not a standalone tool | nothing loads |
| **git** | all provenance. A run's commit is the thing that makes it citable | `jobs_submit` refuses; the session fact block omits the branch |
| **`uv`** *(or `mlragents` on `PATH`)* | the hook and MCP shims, which run the Python package | hooks silently no-op; the MCP server fails to start |
| Slurm — `sbatch`, `squeue`, `sacct` | only when `scheduler.kind = "slurm"` | set `kind = "none"`; the `jobs_*` tools and the dirty-tree gate stand down |
| A LaTeX toolchain | only via `commands.paper` | `paper_build` reports the command's failure |

Python is supplied by `uv` (≥ 3.11). Nothing else is required. Verified against
Copilot CLI 1.0.83; the plugin uses agents, skills, hooks and MCP, so any
version supporting those should work.

**No VS Code extension is involved.** This is a terminal plugin for Copilot CLI;
it has no editor component, and installing anything in VS Code does not affect
it.

**The LaTeX dependency is indirect.** This package never invokes a LaTeX engine.
It runs whatever string you put in `commands.paper` — `latexmk -pdf main.tex`,
`tectonic main.tex`, `bash scripts/build_paper.sh` — and parses the output. Any
engine works, and if you do not write papers you can leave the key out; only
`paper_build` needs it.

`tracker.kind` is parsed and preserved, but **no tool acts on it yet**. W&B and
MLflow are not currently required or used.

## Install

Two steps, because they install different things. The plugin gives Copilot the
agents, skills, hooks and MCP tools. The CLI gives *you* `mlragents init` and
`mlragents run`.

```bash
# 1. the plugin (agents, skills, hooks, MCP server)
copilot plugin marketplace add ssh://git@github.com/kailen-hargenrader/MLRAgents.git
copilot plugin install mlragents@mlragents

# 2. the command line tool
uv tool install git+ssh://git@github.com/kailen-hargenrader/MLRAgents.git
```

The SSH URLs are load-bearing: this repository is private, and the `owner/repo`
shorthand resolves to an anonymous HTTPS `git clone`, which cannot authenticate
(`fatal: could not read Username for 'https://github.com'`). The `ssh://` form
uses your existing key.

Step 2 is not optional in practice. A plugin install only copies the tree into
Copilot's plugin directory; it puts nothing on your `PATH`, so `mlragents init`
would be "command not found". Installing the CLI also makes the shims faster:
they prefer `mlragents` on `PATH` and fall back to `uv run` otherwise.

Check both:

```bash
copilot plugin list          # mlragents@mlragents
mlragents --version          # 0.1.0
```

To update after a change to this repository:

```bash
copilot plugin uninstall mlragents
copilot plugin marketplace update mlragents
copilot plugin install mlragents@mlragents
uv tool install --force git+ssh://git@github.com/kailen-hargenrader/MLRAgents.git
```

The uninstall is needed: `marketplace update` refreshes the marketplace's copy,
not the installed one.

Direct installs from a local path still work but are deprecated, and they copy
the directory as-is — including a `.venv` if one is present, which turned a 39M
checkout into 170M. A marketplace install of the same tree is 401K.

The bundled MCP server runs through `uv`, so the first tool call after a fresh
install pays ~8s to build the plugin's virtualenv. Subsequent calls are fast.

## Starting a new project

From an empty directory:

```bash
mkdir thermo-paper && cd thermo-paper
git init
mlragents init --name thermo-paper
```

`init` is not a template. It writes only the structure the guardrails depend on:

```
explore/outputs/    explore/README.md    what this lane means, so the distinction
exploit/outputs/    exploit/README.md    does not live only in your memory
paper/
.mlragents.toml     the adapter — the one file you must edit
.gitignore          gains .mlragents/ (the registry is a cache, never committed)
```

On a laptop with no cluster, pass `--scheduler none`.

**Then edit `.mlragents.toml`.** It is generated with no `[commands]`, and this
is deliberate: nothing here guesses what your repository means. Declare how your
project actually runs:

```toml
[commands]
train    = "uv run experiments/run.py --config-name={config}"
collect  = "uv run scripts/collect_results.py"
paper    = "latexmk -pdf -cd paper/main.tex"
generate = "uv run scripts/make_configs.py"

[paths]
paper = "paper"
generated = ["exploit/configs"]      # hand-edits here are refused
```

A tool that needs an undeclared command fails by naming the missing key and the
file to add it to — it never guesses a command that might work. Start from
[`examples/surf-2026.mlragents.toml`](examples/surf-2026.mlragents.toml), a
working adapter for a Hydra + uv + W&B + Slurm project, and see
[`docs/mlragents-toml.md`](docs/mlragents-toml.md) for every key.

Commit the scaffold, then work in a role:

```bash
git add -A && git commit -m "mlragents structure"
mlragents run explore
```

Adopting an existing repository is the same, minus `git init`. Point the lanes
at the directories you already have, and run `mlragents runs sync` once to
populate the registry from your existing outputs.

## Use

```bash
mlragents run explore      # cheap model, confined to explore/, no sbatch
mlragents run experiment   # the exploit lane: paper-grade runs
mlragents run analysis     # figures, tables and macros from finished runs
mlragents run paper        # .tex and .bib only
```

Each launches Copilot CLI with that role's agent and limits, and exports
`MLRAGENTS_ROLE` so the hooks know which role is running. The underlying command
is `copilot --agent=mlragents:experiment`; the `mlragents:` prefix is required,
since plugin agents are namespaced and `--agent=experiment` fails with "No such
agent".

You can also run plain `copilot` and switch with `/agent`, or let it delegate by
intent. You lose the launch-time denials that way — `mlragents run` is what
applies `--deny-tool`, and no hook can undo a job that has already been queued.

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
