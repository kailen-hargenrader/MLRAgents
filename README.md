# MLRAgents

**Copilot CLI agents for machine learning research.**

Six months from now, a reviewer asks where the 91.3% in Table 2 came from. You
should be able to answer.

## Why

Most of what goes wrong in an ML paper isn't a modelling mistake. It's
bookkeeping:

- A number in the paper came from a run whose code was never committed.
- Two cells in an "ablation" differed in two places, not one, so the comparison
  supported nothing.
- A scratch result from week three quietly became a headline number.
- Nobody can tell which of the 400 output directories was the real one.

None of that shows up as an error. It shows up in review, or after publication,
or not at all. MLRAgents makes those specific mistakes hard to commit.

## How

Your repository gets two experiment lanes:

```
explore/    fast and scrappy — one seed, dirty tree, half an idea. Never cited.
exploit/    disciplined — every number in the paper comes from here.
paper/      the manuscript.
```

You work in a **role**, and the role decides what you're allowed to do:

| | For | Limits |
|---|---|---|
| `explore` | hunches and sanity checks | `explore/` only, no cluster jobs, cheap model |
| `experiment` | runs that may reach the paper | unrestricted — this is the main lane |
| `analysis` | figures, tables, macros | reads `exploit/`, writes `paper/` |
| `paper` | prose and references | `.tex` and `.bib` only |

Splitting explore from exploit isn't tidiness. **Exploration earns its speed by
giving up the right to be cited.** Promoting a finding means *re-running* it
under exploit-lane conditions — never copying results across, which would
launder their provenance.

## Guardrails

Four things are refused outright, because each one fails *silently* — nothing
downstream would ever report the damage:

| If you… | …this happens | Override |
|---|---|---|
| `sbatch` from a dirty tree | refused — the run couldn't be reproduced | `MLRAGENTS_ALLOW_DIRTY=1` |
| hand-edit a generated config | refused, naming the generator | fix the generator |
| write outside your role's lane | refused | switch roles |
| type a number into a `.tex` | flagged for review | use a macro |

Successful submissions are recorded with the commit they ran from — something
`sacct` doesn't know and no later scan can recover.

These are hooks, not instructions. The model doesn't get a vote.

In practice it looks like this:

```
❯ launch the ablation grid

✗ shell · sbatch exploit/scripts/ablation.sh
  └ The working tree is dirty (src/model.py), so a job submitted now could not
    be reproduced from any commit. Commit or stash first. If this run is
    deliberately throwaway, set MLRAGENTS_ALLOW_DIRTY=1 for the session — but
    its results are then not citable.
```

Every refusal names the escape hatch, because a guardrail you can't get past
when you genuinely mean it is a guardrail you'll turn off entirely.

## Install

```bash
# agents, skills, hooks and tools
copilot plugin marketplace add ssh://git@github.com/kailen-hargenrader/MLRAgents.git
copilot plugin install mlragents@mlragents

# the mlragents command
uv tool install git+ssh://git@github.com/kailen-hargenrader/MLRAgents.git
```

Both steps are needed: the plugin install puts nothing on your `PATH`. Check
with `copilot plugin list` and `mlragents --version`.

<details>
<summary>Requirements, and updating</summary>

You need **Copilot CLI**, **git** (provenance is git commits) and **`uv`**.
Python comes from `uv`.

Everything else is optional and depends on your project:

- **Slurm** only if you set `scheduler.kind = "slurm"`. On a laptop use `"none"`.
- **LaTeX** only if you build papers. This package never invokes an engine — it
  runs the `commands.paper` string you provide and parses the output, so
  `latexmk`, `tectonic` or a shell script all work.
- **No VS Code extension is involved.** This is terminal-only.

To update:

```bash
copilot plugin marketplace update mlragents
copilot plugin install mlragents@mlragents
uv tool install --force git+ssh://git@github.com/kailen-hargenrader/MLRAgents.git
```

The private repo is why the URLs are `ssh://`: the `owner/repo` shorthand clones
anonymously over HTTPS and can't authenticate.

</details>

## Quick start

```bash
mkdir my-paper && cd my-paper
git init
mlragents init --name my-paper      # add --scheduler none if you have no cluster
```

That scaffolds `explore/`, `exploit/`, `paper/` and `.mlragents.toml`. Then tell
it how your project runs — this is the one file you have to edit:

```toml
[commands]
train    = "uv run experiments/run.py --config-name={config}"
collect  = "uv run scripts/collect_results.py"
paper    = "latexmk -pdf -cd paper/main.tex"
generate = "uv run scripts/make_configs.py"

[paths]
generated = ["exploit/configs"]      # hand-edits here are then refused
```

Every key is optional, and nothing is guessed — a tool that needs a command you
haven't declared says so by name. See
[`docs/mlragents-toml.md`](docs/mlragents-toml.md), or copy
[`examples/surf-2026.mlragents.toml`](examples/surf-2026.mlragents.toml) (Hydra +
uv + W&B + Slurm).

Then commit and start working:

```bash
git add -A && git commit -m "mlragents structure"

mlragents run explore       # hunches
mlragents run experiment    # paper-grade runs
mlragents run analysis      # figures, tables, macros
mlragents run paper         # prose
```

Every session opens with the facts: your branch, whether the tree is dirty, and
what's actually running on the cluster. If you don't see that block, the hooks
aren't loading.

Plain `copilot` works too — the agents are there under `/agent`. You just lose
the launch-time limits, since `mlragents run` is what applies them, and no hook
can call back a job that's already queued.

**Already have a repository?** Same thing, minus `git init`. Point the lanes at
the directories you already have and run `mlragents runs sync` once to index
your existing outputs.

## What the agents can look up

Twelve tools, over MCP. The ones that matter most:

| | |
|---|---|
| `runs_provenance` | **may the paper cite this run?** — and if not, exactly why |
| `grid_diff` | do these two cells differ *only* along the axis you're testing? |
| `jobs_submit` | submit and record the commit in one step; refuses if it can't |
| `paper_build` | build, with errors and undefined citations pulled out of the log |
| `paper_audit_numbers` | which numbers in the `.tex` aren't carried by a macro |

Plus `runs_list`, `runs_get`, `lanes_list`, `jobs_queue`, `jobs_history`,
`jobs_logs` and `collect_results`.

`grid_diff` is the one people underestimate. Two configs that differ in two
places support no claim about either — and that is genuinely hard to see reading
two YAML files side by side.

## More

- [`docs/mlragents-toml.md`](docs/mlragents-toml.md) — every configuration key
- [`docs/developing.md`](docs/developing.md) — layout, design notes, contributing
- [`docs/verification/`](docs/verification/) — what was tested against the real
  CLI and a real cluster, including the assumptions that turned out to be wrong
