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
