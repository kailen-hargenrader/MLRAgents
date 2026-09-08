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
paper = "paper"
generated = ["exploit/configs"]

# Insight. Never cited.
[explore]
root = "explore"
outputs = "outputs"

# Evidence. Everything in the paper comes from here.
[exploit]
root = "exploit"
outputs = "outputs"
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
| `paper` | `"paper"` | Manuscript sources, figures and generated tables. |
| `generated` | `[]` | Trees a generator owns. Hand-edits to them are refused. |

Declaring `generated` turns on the hand-edit denial: a write into one of these
directories is refused, and the refusal names `commands.generate` if it is
declared. Editing one generated config is how a second axis enters an ablation
without anyone deciding to add it, and the edited file still sits beside the
run's artefacts looking authoritative.

### `[explore]` and `[exploit]`

The two experiment lanes. Their names are fixed, because the names carry meaning
the system enforces: a quantity in the paper must resolve to an `exploit` run,
and an `explore` run is never evidence. Only where the trees live is
configurable.

Declare both, or declare only one. A repository that has not separated the two
declares a single lane rooted at itself:

```toml
[exploit]
root = "."
```

| Key | Default | Meaning |
|---|---|---|
| `root` | the lane's name | The lane's tree, relative to the project root. |
| `outputs` | `"outputs"` | Run artefacts, relative to `root`. Scanned by `mlragents runs sync`. |
| `run_pattern` | none | How to read experiment labels out of a run's path. See below. |

Run ids are qualified by lane — `exploit/ablation/softmax/01-00-00` — so that
two lanes cannot collide on an identical relative path, and so that a citation
carries the lane it came from.

Only the `explore` lane is confined. A `preToolUse` hook refuses writes outside
it when the session runs in the explore role, and `mlragents run explore` denies
scheduler submission at launch. The exploit lane is deliberately unguarded: a
guardrail that fires during ordinary paper work would be turned off.

#### `run_pattern`
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
| `collect` | gathering evaluation results — the `collect_results` tool |
| `paper` | rebuilding every figure, table and macro, then the PDF — the `paper_build` tool |
| `generate` | regenerating configs; named in the hand-edit refusal |

A tool that needs an undeclared command fails with a message naming the key and
the file to add it to, rather than guessing a command that might work.

## Unknown sections

Sections other than those above are preserved verbatim on
`ProjectConfig.extra`. Adding project-specific configuration is safe; it will
not be rejected, and it survives a round trip.

## Discovery

`find_project` walks upward from the working directory until it finds
`.mlragents.toml`, so tools work from any subdirectory. When no file is found,
tools that need one raise `MissingProject`, and the session-start hook stays
silent rather than reporting a project that does not exist.
