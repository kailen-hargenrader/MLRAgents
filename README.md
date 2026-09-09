# MLRAgents

A GitHub Copilot CLI plugin for machine learning research: specialised agents, and
guardrails that keep a paper's numbers traceable.

## Highlights

- Four agents — `explore`, `experiment`, `analysis`, `paper` — each confined at launch,
  not by asking the model.
- Two experiment lanes: `explore/` for hunches, `exploit/` for anything the paper cites.
- Refuses cluster submissions from a dirty tree, and records the commit for the ones it
  allows.
- Refuses hand-edits to generated configs, naming the generator that owns them.
- Checks that two ablation cells differ along exactly one axis.
- Builds the manuscript and pulls errors and undefined citations out of the log.
- Flags numbers typed into `.tex` that no macro carries.
- Twelve [MCP tools](#tools) over your runs, queue and manuscript.
- Works with or without Slurm, any LaTeX engine, any config system.
- The dirty-tree and generated-config gates are hooks, so they hold in a plain `copilot`
  session too; lane confinement needs `mlragents run`.

## Installation

Requires [Copilot CLI](https://github.com/github/copilot-cli), `git` and
[`uv`](https://github.com/astral-sh/uv).

```bash
# 1. the plugin: agents, skills, hooks, MCP server
copilot plugin marketplace add ssh://git@github.com/kailen-hargenrader/MLRAgents.git
copilot plugin install mlragents@mlragents

# 2. the mlragents command
uv tool install git+ssh://git@github.com/kailen-hargenrader/MLRAgents.git
```

Both steps are needed — the plugin install puts nothing on your `PATH`. Verify with
`copilot plugin list` and `mlragents --version`.

To update:

```bash
copilot plugin marketplace update mlragents
copilot plugin install mlragents@mlragents
uv tool install --force git+ssh://git@github.com/kailen-hargenrader/MLRAgents.git
```

## Quick start

```console
$ mkdir my-paper && cd my-paper && git init

$ mlragents init --name my-paper
created explore/README.md
created exploit/README.md
created explore/outputs/.gitkeep
created exploit/outputs/.gitkeep
created paper/.gitkeep
created .mlragents.toml
created .gitignore
explore/ is insight; exploit/ is what the paper cites.
```

Uncomment and edit the keys in `.mlragents.toml` that describe how your project runs.
Every key is optional; a tool that needs one you haven't set fails with its name.

```toml
[commands]
train    = "uv run experiments/run.py --config-name={config}"
paper    = "latexmk -pdf -cd paper/main.tex"
generate = "uv run scripts/make_configs.py"

[paths]
generated = ["exploit/configs"]   # hand-edits here are refused

[scheduler]
kind = "slurm"                    # or "none"
```

Then commit and start a session:

```console
$ git add -A && git commit -m "mlragents structure"

$ mlragents run experiment
```

Every session opens with the current facts, injected by a hook:

```
MLRAgents: project 'my-paper' at /home/you/my-paper
git: main @ 55a4c74a (clean)
slurm (you): 1 job(s)
  2541417 pers_comp RUNNING 8:15:00 hpc-92-09
recent runs: registry empty (run `mlragents runs sync`)
```

Roles are `explore`, `experiment`, `analysis` and `paper`. On an existing repository,
skip `git init`, point the lanes at the directories you already have, and run
`mlragents runs sync` once to index past outputs.

See [`docs/mlragents-toml.md`](docs/mlragents-toml.md) for every key, or copy
[`examples/surf-2026.mlragents.toml`](examples/surf-2026.mlragents.toml) (Hydra, uv, W&B,
Slurm).

## Guardrails

Four actions are refused, each one because it fails silently otherwise:

| Action | Result | Override |
| --- | --- | --- |
| `sbatch` from a dirty tree | refused | `MLRAGENTS_ALLOW_DIRTY=1` |
| hand-editing a generated config | refused, naming the generator | fix the generator |
| writing outside your role's lane | refused | switch roles |
| a bare number in a `.tex` | flagged | use a macro |

When the agent tries `sbatch exploit/scripts/ablation.sh` with uncommitted changes:

```
The working tree is dirty (src/model.py), so a job submitted now could not be
reproduced from any commit. Commit or stash first. If this run is deliberately
throwaway, set MLRAGENTS_ALLOW_DIRTY=1 for the session — but its results are
then not citable.
```

## Tools

The agents query your project over MCP:

| Tool | |
| --- | --- |
| `runs_provenance` | may the paper cite this run, and if not, why |
| `grid_diff` | do two cells differ only along the declared axis |
| `jobs_submit` | submit and record the commit in one step |
| `paper_build` | build, with errors and undefined citations extracted |
| `paper_audit_numbers` | numbers in the `.tex` that no macro carries |

Plus `runs_list`, `runs_get`, `lanes_list`, `jobs_queue`, `jobs_history`, `jobs_logs` and
`collect_results`.

`grid_diff` on two cells whose depth was changed along with the kernel:

```json
{
  "ok": false,
  "differing_keys": ["model.depth", "model.kernel"],
  "violations": ["model.depth"],
  "summary": "1 key(s) differ outside the declared axes: model.depth. These two cells do not isolate model.kernel."
}
```

## Documentation

- [`docs/mlragents-toml.md`](docs/mlragents-toml.md) — configuration reference
- [`docs/developing.md`](docs/developing.md) — repository layout and design notes
- [`docs/verification/`](docs/verification/) — what was tested against a real cluster
