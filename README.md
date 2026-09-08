# MLRAgents

A GitHub Copilot CLI plugin for machine learning research: agents that know the
difference between a scratch experiment and one whose numbers may reach a paper,
backed by tools that read run provenance and cluster state as facts rather than
guesses.

Status: **foundation complete** (phases 0–1 of the
[design spec](docs/superpowers/specs/2026-09-08-mlragents-design.md)). The
registry, scheduler adapters, session-start context, hook dispatch and MCP
server work and are verified against a live cluster and a real 65G research
repository. The agent and skill library is deliberately still thin.

## What it is

Three layers, separated by how often they change and by what happens when they
are wrong:

| Layer | Lives in | Enforcement |
|---|---|---|
| Methodology — how to run an experiment, what to check before launching | `agents/`, `skills/` | Persuasion. The model may disagree. |
| Tools — run registry, Slurm queue and history, log triage | `src/mlragents/`, exposed over MCP | Tested facts. |
| Guardrails — what must never happen | `hooks/` | Enforcement. The model gets no vote. |

The rule that decides the layer: anything whose violation would silently corrupt
a paper belongs in a hook, not in a prompt.

**The Python layer never infers what a repository means.** It uses universal
substrates — git, Slurm, SQLite, the filesystem — or it shells out to a command
the repository declared. Nothing is guessed from a directory name. See
[`docs/mlragents-toml.md`](docs/mlragents-toml.md).

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
copilot --agent=mlragents:experiment
```

The `mlragents:` prefix is required — plugin agents are namespaced, and
`--agent=experiment` fails with "No such agent".

Every session opens with a fact block: the current branch, whether the tree is
dirty, and what is actually running on the cluster. It is injected by a
`sessionStart` hook, so it is true regardless of what the model believes.

```bash
mlragents runs sync     # rebuild the registry from outputs/ and sacct
```

The registry is a cache and never a source of truth. Every field in it is
recoverable from `outputs/`, git and `sacct`, which is what `runs sync` does.

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
documentation, and recorded in [`docs/verification/`](docs/verification/). Four
documented or assumed behaviours turned out to be false; two bugs were found
only by running against a real repository. Read those files before trusting a
design decision that depends on CLI behaviour.
