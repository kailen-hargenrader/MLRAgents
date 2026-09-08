# MLRAgents — Design

Date: 2026-09-08
Status: **Draft for review.** No implementation has begun.

## 1. Purpose

A portable agentic system for machine-learning research, usable across every
research repository without copying files into each one.

The system encodes a research methodology that already exists implicitly in
`SURF_2026` and makes it enforceable:

- Every number in a manuscript is produced by a script reading run artefacts;
  none is typed by hand.
- Ablation cells differ only in the axis under test; everything else, including
  hardware, is held fixed and the reason is recorded.
- Exploratory work is cheap and disposable; work that enters a paper carries
  provenance (git SHA, config hash, seed, job id, device).
- Claims are scoped to the runs observed, not asserted as mechanisms.

The agent layer supplies judgement. The deterministic layer supplies facts and
refusals. The methodology layer supplies the rules.

## 2. Platform facts this design depends on

Verified against GitHub Copilot CLI v1.0.83 documentation (2026-09-08):

- A **plugin** is a git repository containing `plugin.json` (searched at
  `.plugin/`, repo root, `.github/plugin/`, `.claude-plugin/`). It may ship
  custom agents, skills, hooks, MCP server definitions, slash commands and LSP
  servers.
- Install: `copilot plugin install OWNER/REPO`, or via a marketplace declared by
  `marketplace.json` in the same repository. Updates: `copilot plugin update`.
  Installs land in `~/.copilot/installed-plugins/MARKETPLACE/PLUGIN`. Local path
  installs load live from disk, which makes development iteration cheap.
- **Agents** are `*.agent.md`; the filename minus the extension is the id.
  Frontmatter: `name`, `description` (required), `target`, `tools`, `model`
  (may be an ordered list; `model-policy: required` pins it),
  `disable-model-invocation`, `user-invocable`, `mcp-servers`, `metadata`.
  Instructions are the Markdown body (30,000 character limit). There is no
  `instructions` key. `tools` is an allow-list supporting aliases (`read`,
  `edit`, `shell`, `search`), MCP wildcards (`github/*`) and the empty list.
  Path restriction is **not** an agent frontmatter feature.
- **Skills** are directories containing `SKILL.md` with `name`, `description`
  and optional `allowed-tools`. Selection is driven by matching the prompt
  against `description`.
- **Hooks** cover 14 events. The ones this design uses: `sessionStart`
  (returns `additionalContext`), `preToolUse` (returns `permissionDecision`
  allow/deny/ask plus `modifiedArgs`; command hooks are fail-closed),
  `postToolUse` (`modifiedResult`, `additionalContext`), `agentStop`
  (`decision: block` with a reason, capped at 8 consecutive blocks).
  Payloads arrive as JSON on stdin; decisions are returned as JSON on stdout.
  Hooks from every source are combined — none overrides another.
- **MCP** servers are declared per-plugin (`.mcp.json`), per-repo (`.mcp.json`,
  `.github/mcp.json`) or per-user (`~/.copilot/mcp-config.json`), and may also
  be scoped to a single agent through `mcp-servers` frontmatter.
- Non-interactive use: `copilot -p PROMPT --agent=ID --model=M --allow-tool=...
  -s`. There is no documented JSON output mode; scripted chaining is ordinary
  shell composition.

Two consequences for the plan in the original transcript:

1. **A Python package that copies or symlinks `.agent.md` files into each
   repository is unnecessary.** Distribution, versioning and update are native
   plugin features. Drop the sync command.
2. **Path confinement cannot be expressed in an agent file.** "The exploratory
   agent may not modify the main pipeline" must be enforced outside the agent
   definition — by session-level path and tool filters, and by a `preToolUse`
   hook — not by prompt text or frontmatter.
3. **Hook payloads do not identify the active agent.** Documented `preToolUse`
   fields are `sessionId`, `timestamp`, `cwd`, `toolName`, `toolArgs`. A hook
   therefore cannot ask "which agent is running?" without help. See §3.3.

## 3. Architecture

One repository, `kailen-hargenrader/MLRAgents`, that is simultaneously a Copilot
CLI plugin, its own single-plugin marketplace, and a Python package.

```
MLRAgents/
  .claude-plugin/
    plugin.json          # component paths
    marketplace.json     # so `marketplace add kailen-hargenrader/MLRAgents` works
  agents/*.agent.md      # L1: roles
  skills/<name>/SKILL.md # L1: methodology
  hooks/
    hooks.json           # L3: event wiring
    <event>/...          # L3: hook executables (thin; logic lives in Python)
  .mcp.json              # points at the L2 server, launched with uvx
  src/mlragents/         # L2: Python package
    adapter.py           # reads .mlragents.toml
    registry.py          # run registry (SQLite)
    scheduler/slurm.py   # squeue/sacct/sbatch wrappers
    latex.py             # build + numeric-literal audit
    grids.py             # config-cell diffing
    mcp_server.py        # MCP surface
    cli.py               # `mlragents ...`, used by hooks and by scripts
  tests/
  docs/
```

Three layers, separated because they change at different rates and have
different failure modes:

| Layer | Contents | Changes | Failure mode |
|---|---|---|---|
| L1 Methodology | agents, skills | often, cheaply | model ignores it |
| L2 Tools | Python package, MCP server | rarely, with tests | wrong answer, catchable |
| L3 Guardrails | hooks | rarely | blocks legitimate work |

Prompts persuade; hooks enforce. Anything whose violation would silently corrupt
a paper belongs in L3, not L1.

### 3.1 The project adapter

The central difficulty is that L2 tools must serve repositories with different
layouts. `SURF_2026` uses Hydra, `outputs/<date>/<experiment>/<cell>/<time>/`,
`uv run`, Slurm and Weights & Biases. The next project will not.

Resolution: a single file, `.mlragents.toml`, committed to each research
repository. It is the only per-repo artefact the system requires.

```toml
[project]
name = "surf-2026"
python = "uv run python"          # how to invoke the environment

[paths]
outputs = "outputs"
configs = "configs"
paper    = "paper"
scratch  = "scratch"              # exploratory agent's writable sandbox
protected = ["src", "experiments", "configs"]   # main pipeline

[scheduler]
kind = "slurm"
log_dir = "slurm_logs"

[tracker]
kind = "wandb"

[commands]
train   = "uv run experiments/run_experiment.py --config-name={config}"
collect = "uv run scripts/collect_ablation_eval.py --grid {grid}"
paper   = "bash scripts/build_paper.sh"
```

**Invariant: L2 never infers repository semantics.** Every tool either operates
on a universal substrate (Slurm, git, SQLite, LaTeX) or shells out to a command
declared here. This keeps the package generic, testable, and honest about what
it does not know. When `.mlragents.toml` is absent, tools that need it fail with
an actionable message and the `initializing-a-research-repo` skill offers to
generate one.

### 3.2 The run registry

`.mlragents/registry.sqlite` in the research repo (git-ignored; it is a cache of
facts recoverable from `outputs/` and Slurm).

One row per run: run id, grid, cell, config path, config hash, resolved-config
hash, git SHA, working-tree-dirty flag, seed, scheduler job id, node/GPU,
submitted/started/finished timestamps, status, outputs path, tracker URL.

Written automatically by the `postToolUse` hook on `sbatch`, and reconcilable
after the fact by `mlragents runs sync`, which walks `outputs/` and `sacct`.
Provenance is therefore a by-product of working, not a discipline the model has
to remember.

### 3.3 Role propagation

Because hook payloads omit the agent id (§2), role-dependent enforcement needs a
channel of its own. Two mechanisms, used together:

**Session-level filters at launch.** A thin launcher, `mlragents run <role>
[prompt]`, invokes the CLI with the filters that express the role:

```
copilot --agent=explore -p "..." \
        --add-dir "$(mlragents path scratch)" \
        --deny-tool='shell(sbatch:*), shell(srun:*)'
```

This is the load-bearing mechanism: it is documented, deterministic, and needs
no hook. Interactive `/agent explore` inside an unrestricted session gets the
prompt-level rules but not the hard filters, and the agent bodies say so.

**Role hint via environment.** The launcher exports `MLRAGENTS_ROLE`, which hook
processes read to refine messages and to catch the cases filters cannot express
(for example, "this `sbatch` targets a main-grid config"). Whether command hooks
inherit the CLI's environment is **unverified** and is a phase 0 check; if they
do not, the launcher writes the role to `.mlragents/session/<sessionId>.json`
instead, keyed by the `sessionId` present in every payload.

Guardrails that hold regardless of role — dirty-tree submission, hand-edited
generated configs, provenance recording, the numeric audit — need neither
mechanism and are the ones shipped first.

## 4. Components

### 4.1 Agents

Four. Each is a role with a distinct tool budget and a distinct definition of
done. More would be speculative.

**`explore`** — cheap, fast model. Writable only under `paths.scratch` and
barred from `sbatch`/`srun`, enforced by the launcher's session filters (§3.3)
rather than by prompt text. Deliverable is a written finding with the command
that produced it, never code of record. Explicitly licensed to be sloppy, and
explicitly barred from claiming a result is real.

**`experiment`** — paper-grade runs. Strong model. May write configs only
through the repository's generator, may `sbatch`, must register every run.
Refuses to launch from a dirty working tree. Before a grid, requires: the axis
under test named, the held-fixed set named, and the outcome that would falsify
the hypothesis written down.

**`analysis`** — read-only over `outputs/`; writes only under `paths.paper`
(figure/table scripts and their outputs). May not touch training code, which
prevents the failure where a disappointing result is "fixed" upstream.

**`paper`** — `*.tex` and `*.bib` only. May not invent numbers: every quantity
must resolve to a macro or table generated by `analysis`. Builds, reads the log,
and fixes its own errors.

Promotion between stages (`explore` → `experiment`) is a skill, not an agent.

### 4.2 Skills

Methodology, invocable by any agent. Initial set, each earned by an observed
practice in `SURF_2026`:

- `designing-an-ablation` — one axis at a time; shared parent config; fix the
  device across cells when timings are reported; state the falsifier first;
  record why each cell exists.
- `promoting-an-experiment` — the scratch→main gate: seed set and logged, config
  generated not hand-edited, comparability argued, cost estimated from a measured
  rate rather than guessed.
- `reading-run-results` — plateau and convergence rules; choose the summary
  statistic before looking; report the alternative statistic when the verdict
  depends on it.
- `debugging-a-failed-job` — triage order for Slurm `.err`/`.out`, OOM vs.
  architecture-unsupported vs. preemption.
- `writing-results-prose` — terse, formal, no first person; describe what was
  observed in the runs tested rather than asserting a mechanism.
- `keeping-the-paper-reproducible` — no hand-typed numbers; every table and
  figure regenerated by the paper build; a claim whose script does not run is a
  claim that does not exist.
- `initializing-a-research-repo` — generate `.mlragents.toml` by inspecting the
  repository, and confirm each inferred field with the user.

### 4.3 Hooks

| Event | Behaviour |
|---|---|
| `sessionStart` | Inject a compact fact block: `.mlragents.toml` summary, git branch and dirty state, the user's current Slurm queue, the last five registry entries with status. Grounds the session in the cluster's actual state rather than the model's assumption of it. |
| `preToolUse` (shell) | Deny `sbatch`/`srun` of a main-grid config from a dirty working tree, or when provenance cannot be recorded. Role-dependent denials are refined by the role hint of §3.3 but do not depend on it. Fail-closed, with a reason string that tells the agent what to do instead. |
| `preToolUse` (edit/write) | Deny hand-edits to generated config directories; direct the agent to the generator script. |
| `postToolUse` (shell) | On a successful `sbatch`, parse the job id and insert the provenance row into the registry. |
| `agentStop` | If `*.tex` was modified this session, run the numeric-literal audit; `decision: block` with the offending lines when a number appears that no macro or generated table produced. |

Hook executables are thin shims over `mlragents hook <event>`, so the logic is
Python, unit-testable, and shared with the CLI.

### 4.4 MCP tools

Deliberately small. Each is either universal or a declared-command passthrough.

- `runs_list`, `runs_get`, `runs_provenance` — query the registry.
- `jobs_queue`, `jobs_status`, `jobs_logs` — `squeue`/`sacct`, plus the tail of a
  job's `.err`/`.out` with the first error line extracted.
- `jobs_submit` — submit through the scheduler, refusing when provenance cannot
  be recorded.
- `grid_diff` — diff two config cells and assert that only the intended axis
  differs. This is the ablation invariant made mechanical.
- `paper_build` — run `commands.paper`; return errors and undefined references.
- `paper_audit_numbers` — the numeric-literal check the `agentStop` hook uses.
- `collect_results` — run `commands.collect` and return its output.

The server is launched from the plugin's `.mcp.json` with
`uvx --from git+https://github.com/kailen-hargenrader/MLRAgents mlragents-mcp`,
pinned by tag, so installing the plugin is the only installation step.

## 5. Alternatives considered

**Repository template.** Rejected: every change requires touching every existing
paper repository, and the copies drift.

**Git submodule.** Rejected: Copilot CLI's discovery paths are fixed, so a
submodule needs symlinks into `.github/`, and submodule state becomes another
thing to get wrong during a deadline.

**Global-only `~/.copilot/`.** Rejected as the primary mechanism: it is
unversioned, unshareable and untestable, and cannot express per-project
configuration. It remains available for genuinely personal overrides, which the
plugin's precedence rules already accommodate (user-level agents win).

**Python package that syncs configs into repos** (the original proposal).
Rejected: this reimplements plugin install and update, badly. The package
survives as the tool runtime, which is the part plugins do not provide.

**Full autonomy (an AI-Scientist-style loop).** Rejected: the value here is a
human-steered loop with mechanical guarantees, not unattended paper generation.

## 6. Testing

- L2 is ordinary Python with pytest. Slurm, git and LaTeX are behind thin
  adapters, faked in tests; a small set of integration tests runs against a real
  repository fixture.
- Hooks are tested by piping a recorded event payload to `mlragents hook EVENT`
  and asserting the JSON decision and exit code, including the fail-closed path.
- Agents and skills are linted against the documented frontmatter schema, plus a
  smoke test that `copilot -p "..." --agent=<id>` loads each agent from a local
  plugin install.
- The registry has a reconciliation test: a synthetic `outputs/` tree plus
  `sacct` output must yield the same rows as live hook recording.

## 7. Phasing

Each phase ends with something usable.

0. **Skeleton and de-risking.** `plugin.json`, `marketplace.json`, one trivial
   agent, one trivial skill, one `sessionStart` hook that prints a fixed string.
   Verify local install, `-p --agent` loading, hook firing, whether command
   hooks inherit the CLI environment (§3.3), and that `--deny-tool='shell(sbatch:*)'`
   actually blocks. This validates every platform assumption in §2 before any
   real work depends on it.
1. **Adapter and read-only tools.** `.mlragents.toml`, registry schema,
   `runs_*`/`jobs_*`, `mlragents runs sync`, the real `sessionStart` hook.
   Validated against `SURF_2026` without writing to it.
2. **Agents and skills.** The four agents and the seven skills; used in anger on
   the current paper.
3. **Guardrails.** The `preToolUse` denials, `postToolUse` provenance recording,
   and the `agentStop` numeric audit.
4. **Paper loop.** `grid_diff`, `paper_build`, `paper_audit_numbers`, and the
   `analysis`/`paper` agents' full workflow.

## 8. Risks

- **Guardrails that block real work.** A fail-closed `preToolUse` hook that
  misjudges is worse than no hook. Mitigation: every denial names an override,
  and phase 3 ships after phase 2 has produced evidence about what the agents
  actually do.
- **Platform drift.** Copilot CLI is moving quickly; §2 is dated. Mitigation:
  phase 0 is an executable check of those assumptions, and it is kept as a test.
- **Adapter under-specification.** `.mlragents.toml` may not describe a future
  project. Mitigation: unknown keys are preserved, and any tool lacking a
  declared command fails loudly instead of guessing.
- **Registry divergence.** The hook may miss submissions made outside the agent.
  Mitigation: `runs sync` reconstructs from `outputs/` and `sacct`; the registry
  is a cache, never a source of truth.

## 9. Open questions for review

1. **Scope confirmation.** The design treats *experiment rigour and provenance*
   as the primary problem, with the paper loop second. If cluster ergonomics
   (fewer bespoke `submit_*.sh` scripts) matters more, phases 1 and 4 swap.
2. **Audience.** Solo use, or the Stuart group? Group use raises the priority of
   `.mlragents.toml` ergonomics and the marketplace path.
3. **Agent count.** Four agents, or is `analysis` better folded into `paper`?
4. **Registry location.** In-repo SQLite as specified, or a single global
   registry under `~/.mlragents/` spanning projects?
5. **Retrofit depth.** Should phase 1 include migrating `SURF_2026`'s existing
   `outputs/` tree into the registry, or start recording from installation
   onward?
