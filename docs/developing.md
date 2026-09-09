# Developing MLRAgents

## Layout

| Directory | What lives there |
|---|---|
| `agents/` | the four `*.agent.md` role definitions |
| `skills/` | seven `*/SKILL.md` procedures |
| `hooks/` | `hooks.json` plus the `mlragents-hook` shim |
| `src/mlragents/` | the Python package and the MCP server |
| `bin/` | the `mlragents-mcp` launcher named by `.mcp.json` |

## Working on it

```bash
uv run pytest -q
copilot --plugin-dir ~/MLRAgents --agent=mlragents:experiment
```

`--plugin-dir` loads agents, skills and hooks live, with no install. It does
**not** register the bundled MCP server, so pair it with
`--additional-mcp-config @<file>` when changing MCP tools, or test through a real
install.

## Three ways to lose an hour

These are the failure modes that produce *no error message*. Each is now covered
by a test in `tests/test_plugin_assets.py`.

**An agent's `tools` allowlist hides MCP tools unless they are named
individually** — `mlragents-jobs_queue`, not `mlragents`. Naming the server
alone silently yields nothing. An agent that gains a tool needs that tool added
to its frontmatter or it simply cannot do its job, with no indication why.

**A skill with a malformed header is never offered.** It does not error; the
session just proceeds slightly worse.

**Plugin agents are namespaced.** `--agent=experiment` fails with "No such
agent"; it is `--agent=mlragents:experiment`.

## Design notes

**The three layers.** Methodology (`agents/`, `skills/`) is persuasion — the
model may disagree. Tools (`src/mlragents/`) are tested facts. Guardrails
(`hooks/`) get no vote. The rule that decides which layer something belongs to:
*anything whose violation would silently corrupt a paper belongs in a hook, not
in a prompt.*

**Nothing is inferred from a repository's shape.** The Python layer uses
universal substrates — git, Slurm, SQLite, the filesystem — or it shells out to a
command the project declared in `.mlragents.toml`. A tool that needs an
undeclared command fails by naming the missing key rather than guessing.

**Every guardrail fails open.** One that fires when it cannot establish the
facts trains the user to disable it, and then it protects nothing.

**Confinement is asymmetric.** `experiment` is unconfined, because a guardrail
that fires during ordinary paper-grade work is a guardrail that gets turned off.
The gates that protect *provenance*, though, apply to every role — a dirty run is
unusable to anyone, whatever their intent.

**The registry is a cache, never a source of truth.** Every field in it is
recoverable from the lane outputs trees, git and `sacct`, which is exactly what
`mlragents runs sync` does. Run ids are lane-qualified —
`exploit/ablation/softmax/01-00-00` — so a citation carries its lane and the two
trees cannot collide.

**`jobs_submit` is listed only by `experiment`.** The other three roles launch
with `--deny-tool=shell(sbatch:*)`, and a submitting MCP tool in their allowlists
would route straight around that.

## Verification

Claims about the platform are checked against the platform, not against its
documentation, and recorded in [`verification/`](verification/). Several
documented or assumed behaviours turned out to be false, and several bugs were
found only by running against a real repository — including two that the test
suite passed clean. Read those files before trusting a design decision that
depends on CLI behaviour.

The full design rationale is in
[`superpowers/specs/2026-09-08-mlragents-design.md`](superpowers/specs/2026-09-08-mlragents-design.md).
