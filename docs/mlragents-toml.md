# `.mlragents.toml`

The one file a research repository must provide. It is committed to the
research repository, not to this one.

MLRAgents never infers a repository's layout. Every tool either operates on a
universal substrate — git, Slurm, SQLite, LaTeX — or runs a command declared
here. A tool that needs an undeclared command fails and names the missing key
rather than guessing.

## Full example

```toml
[project]
name = "surf-2026"
python = "uv run python"

[paths]
outputs = "outputs"
configs = "configs"
paper = "paper"
scratch = "scratch"
protected = ["src", "experiments", "configs"]
run_pattern = ["*/{grid}/*", "*/{grid}/{cell}/**"]

[scheduler]
kind = "slurm"
log_dir = "slurm_logs"

[tracker]
kind = "wandb"

[commands]
train = "uv run experiments/run_experiment.py --config-name={config}"
collect = "uv run scripts/collect_ablation_eval.py"
paper = "bash scripts/build_paper.sh"
```

## Keys

Every key is optional. Omitted keys take the default shown.

### `[project]`

| Key | Default | Meaning |
|---|---|---|
| `name` | `"unnamed"` | Label used in the session fact block. |
| `python` | `"python"` | How to invoke the project's environment, e.g. `uv run python`. |

### `[paths]`

Paths are relative to the directory holding `.mlragents.toml`.

| Key | Default | Meaning |
|---|---|---|
| `outputs` | `"outputs"` | Root of the run artefact tree. Scanned by `mlragents runs sync`. |
| `configs` | `"configs"` | Root of the experiment configuration tree. |
| `paper` | `"paper"` | Manuscript sources, figures and generated tables. |
| `scratch` | `"scratch"` | Writable sandbox for exploratory work. |
| `protected` | `[]` | The main pipeline. Exploratory work must not modify these. |
| `run_pattern` | none | How to read experiment labels out of a run's path. See below. |

#### `run_pattern`

`mlragents runs sync` records the path of every run it finds, but it will not
guess what the components of that path mean. A directory named `2026-08-23` is a
Hydra date, not an experiment; only the repository knows the difference. So a
run is labelled with a `grid` and a `cell` only if this key says how to find
them.

A pattern is matched against the run's path relative to `outputs`:

| Segment | Matches |
|---|---|
| `{grid}`, `{cell}` | One component, recorded under that name. |
| `*` | Exactly one component, discarded. |
| `**` | Any number of components, discarded. Must be last. |
| anything else | Itself, literally. |

Without a trailing `**`, a pattern matches only paths of exactly its length.
A pattern that does not match yields no labels at all — an absent label is
better than a wrong one.

Give a list to handle a tree whose runs sit at different depths. Patterns are
tried in order and the first match wins, so put the most specific first:

```toml
run_pattern = ["*/{grid}/*", "*/{grid}/{cell}/**"]
```

against Hydra's `outputs/<date>/<experiment>/[<cell>/…]/<time>` skips the date,
takes the experiment as the grid, and leaves `cell` empty for the shallow runs
that have none — rather than recording their timestamp as a cell.

### `[scheduler]`

| Key | Default | Meaning |
|---|---|---|
| `kind` | `"none"` | `"slurm"` or `"none"`. Queue and history are only consulted for `"slurm"`. |
| `log_dir` | `"slurm_logs"` | Where job `.out` and `.err` files land. Searched by job id. |

### `[tracker]`

| Key | Default | Meaning |
|---|---|---|
| `kind` | `"none"` | `"wandb"`, `"mlflow"` or `"none"`. Recorded with each run. |

### `[commands]`

Free-form. Each value is a shell command. `{config}` and similar placeholders
are substituted by the caller. Keys used so far:

| Key | Used by |
|---|---|
| `train` | launching an experiment |
| `collect` | gathering evaluation results |
| `paper` | rebuilding every figure, table and macro, then the PDF |

## Unknown sections

Sections other than the five above are preserved verbatim on
`ProjectConfig.extra`. Adding project-specific configuration is safe; it will
not be rejected, and it survives a round trip.

## Discovery

`find_project` walks upward from the working directory until it finds
`.mlragents.toml`, so tools work from any subdirectory. When no file is found,
tools that need one raise `MissingProject`, and the session-start hook stays
silent rather than reporting a project that does not exist.
