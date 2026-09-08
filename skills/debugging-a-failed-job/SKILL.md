---
name: debugging-a-failed-job
description: Use when a Slurm job fails, dies early, produces no output, or ends in an unexpected state
---

# Debugging a Failed Job

**Core principle:** find out *how* it died before theorising about *why*. The
scheduler already knows, and its answer is cheaper than any hypothesis.

## Triage order

Do these in order. Most failures are identified in step 2.

### 1. Ask the scheduler for the state

`sacct` for the job id. The state distinguishes categories that need completely
different responses:

| State | Meaning | Response |
|---|---|---|
| `OUT_OF_MEMORY` | Exceeded the memory limit | Reduce batch or model, or raise `--mem`. |
| `TIMEOUT` | Hit the wall clock | Raise the limit, or checkpoint and resume. |
| `CANCELLED` | Preemption or a human | Check who. Preemption means requeue, not debug. |
| `NODE_FAIL` | Hardware | Resubmit. Nothing in your code is wrong. |
| `FAILED` | The process exited nonzero | Go to step 2. |
| `RUNNING`/`PENDING` | Not finished | Nothing has failed yet. **`sacct` prints `0:0` for unfinished jobs — that is not a success.** |

### 2. Read the end of `.err`, then the beginning

The last traceback is usually the real one. But read the *first* error too: a
job frequently reports a confusing failure downstream of an earlier, clearer
one — a missing file, a failed import, an unsupported kernel silently falling
back.

### 3. Confirm the job ran what you think it ran

Read the resolved config in the run's output directory, not the config you
intended to submit. Check the git commit. A surprising fraction of "the code is
broken" is "the job ran a different config".

### 4. Only now, hypothesise

## Common causes, in the order they actually occur

1. **OOM disguised as something else.** A killed worker surfaces as a
   dataloader error or a NCCL timeout. Check the state first — that is why
   step 1 exists.
2. **Environment differs from the login node.** The job did not activate the
   environment, or a module is missing. The error is an `ImportError` and it
   looks like a code bug.
3. **Path relative to the wrong directory.** The job's working directory is not
   where you launched it from.
4. **Architecture unsupported.** A kernel or dtype the allocated GPU does not
   implement. The message names the capability; the fix is a constraint on the
   submission, not a code change.
5. **Preemption.** Not a bug. Requeue.

## Rules

**One change at a time.** Two simultaneous fixes mean you never learn which one
worked, and the other one stays in the codebase forever.

**Reproduce interactively before fixing**, on a short allocation, if the failure
is not obvious from the log. A fix validated only by a six-hour resubmission is
a guess with a long feedback loop.

**Do not "fix" a failure by removing the check that reported it.** A run that
completes with an assertion disabled has not succeeded.
