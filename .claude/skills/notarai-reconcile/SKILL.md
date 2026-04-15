---
name: notarai-reconcile
description: Detect drift between project's specs and actual artifacts.
---

You are a **NotarAI reconciliation engine**. Your job is to detect drift between NotarAI spec files and the current code, then propose targeted updates to bring them into alignment.

This skill is a thin orchestrator over the `notarai export-context` CLI. The CLI does the heavy lifting (spec discovery, governed-file selection, per-spec markdown rendering); the skill handles baseline selection, fan-out, interactive resolution, and state snapshotting.

## Instructions

### Step 1: Determine baseline

Read `.notarai/reconciliation_state.json` if it exists.

- **If state exists and `git_hash` is reachable** (test with `git merge-base --is-ancestor <git_hash> HEAD`): use the stored `git_hash` as the baseline. Tell the user: "Using reconciliation baseline from `<timestamp>` (`<git_hash_short>`)." No branch question needed.
- **If state exists but `git_hash` is unreachable** (rebase, squash, force-push): warn the user and fall through to the branch question below.
- **If no state file exists** (first run): fall through to the branch question below.

When a branch question is needed, use the **AskUserQuestion** tool to ask which base branch to use. Offer the most likely options (e.g., `main`, `master`, `dev`) based on `git branch` output, rather than asking a free-form question.

The chosen value (a git hash or a branch name) is the `BASELINE` used in every subsequent step.

### Step 2: Export reconciliation context

Run via the **Bash** tool:

```sh
notarai export-context --all --base-branch <BASELINE> --format markdown
```

The output is a stream of per-spec reconciliation blocks separated by `---`. Each block contains:

- A `# Reconciliation: <spec_name>` heading
- The full spec YAML
- A `## Changed Files` list of governed files that changed since `<BASELINE>`
- Built-in instructions for analyzing drift, listing the issue types (DRIFT / VIOLATED / UNSPECCED / STALE REF)

If `notarai` is not on PATH, fall back to: `cargo run --quiet -- export-context --all --base-branch <BASELINE> --format markdown` from the repo root.

If the command exits non-zero, report the error and stop.

> **Why this command, not MCP?** `export-context` is the canonical context assembler for both Claude and agent-agnostic flows; using it here keeps the two paths in lockstep. The `notarai` MCP server is still used in Step 6 (mark_reconciled) and Step 7 (snapshot_state) when available -- those operations have no CLI equivalent that the skill should call directly.

### Step 3: Triage -- inline vs sub-agents

Parse the output from Step 2 into one block per spec. For each block, count:

- `changed_files_in_spec` = the number of bullets in its `## Changed Files` section
- `block_lines` = the total line count of that block

Compute totals across all blocks:

- `total_specs` = number of blocks
- `total_changed_files` = sum of `changed_files_in_spec` (deduplicated by file path)
- `total_block_lines` = sum of `block_lines`

**Decision:**

- **Inline** (`total_changed_files` <= 10 AND `total_block_lines` <= 500): analyze every spec block directly in the main agent. Skip to Step 3a.
- **Fan out** (above thresholds): spawn one parallel sub-agent per spec block. Skip to Step 3b.

If `total_specs == 0` (no affected specs), report "All specs clean." and skip to Step 7.

#### Step 3a: Inline analysis

For each spec block:

**a.** Read the spec content embedded in the block to extract its `applies` and `dependencies` `$ref` arrays (if any).

**b.** Read the changed files listed in the block, plus any `applies` spec files referenced in (a).

**c.** Use the diff (via `git diff <BASELINE> -- <file>` for each changed file, or read the file's current content) to evaluate each behavior, constraint, and invariant in the spec.

**d.** Build the report data for this spec:

```
SPEC: <spec_path>

ISSUES:
- DRIFT: <name> -- <description>
- VIOLATED: <name> -- <description>
- UNSPECCED: <description>
- STALE REF: <path> -- <description>

DEPENDENCY_REFS: <list of $ref paths from this spec's dependencies array, if any>
APPLIES_REFS: <list of $ref paths from this spec's applies array, if any>
FILES_READ: <list of all files read, for mark_reconciled>
```

If no issues found, set `ISSUES: none`.

Proceed to Step 4.

#### Step 3b: Parallel sub-agents

For each spec block, use the **Agent** tool to spawn a sub-agent. Run all sub-agents in parallel (make all Agent tool calls in the same response).

Each sub-agent task description must be self-contained and include:

- The spec path
- The baseline (git hash or branch name)
- **The full spec block from Step 2** (so the sub-agent has the spec content and changed files list without re-running export-context)

Each sub-agent should:

**a.** Extract `applies` and `dependencies` `$ref` arrays from the embedded spec content.

**b.** Read the changed files listed in the block, plus any `applies` spec files.

**c.** Evaluate each behavior, constraint, and invariant against the changes.

**d.** Return a structured report in the same format as Step 3a.

After all sub-agents return, collect their reports and proceed to Step 4.

> Use the sub-agent reports to identify which specs have `APPLIES_REFS` or `DEPENDENCY_REFS`. If a cross-cutting spec's invariants are violated by the sub-agent's diff findings, add a VIOLATED issue to that spec's report before producing the final report in Step 5.

### Step 4: Note dependency ripple effects (`dependencies`)

For each spec report that lists `DEPENDENCY_REFS`:

- For each dependency, note the relationship in the report.
- If the dependency's governed files are also in the changed set (cross-reference against the union of changed files from all blocks), flag it explicitly.
- If not, add a one-line note: "Dependency on `<spec>` -- verify no ripple effects."

### Step 5: Produce the structured report

Print the report described in the **Report Format** section below.

### Step 6: Update cache

Collect all `FILES_READ` lists from the spec reports (whether inline or from sub-agents). If the `notarai` MCP server is available, call `mark_reconciled({files})` with the combined list. If MCP is unavailable, skip this step silently -- the user can run reconciliation again to recompute.

### Step 7: Interactive resolution (if drift found)

After presenting the report, if any drift was found:

Use the **AskUserQuestion** tool to ask which spec to address first. List the specs with drift as options, plus a "Skip" option to exit.

For the chosen spec:

- Walk through each issue one at a time.
- Propose the exact change (BEFORE/AFTER YAML or code diff).
- Use the **AskUserQuestion** tool to confirm before applying (options: "Apply", "Skip this issue", "Stop").
- Repeat for remaining issues in that spec.
- Call `mark_reconciled` after each spec is fully addressed (if MCP is available).

Use **AskUserQuestion** again to offer the remaining specs, repeating until the user skips or all specs are addressed.

### Step 8: Snapshot reconciliation state

After all specs have been reconciled (or skipped), persist the reconciliation baseline:

- If the `notarai` MCP server is available, call `snapshot_state`.
- Otherwise, run `notarai state snapshot` via the **Bash** tool.

Both write `.notarai/reconciliation_state.json` with the current file fingerprints and git HEAD hash.

---

## Report Format

**Default: silence is sync.** Only report deviations. Omit specs with no issues.

```
## Reconciliation Report: <baseline>

### [checkmark] auth.spec.yaml (4 behaviors * 2 constraints * 1 invariant)
### [X] cli.spec.yaml (9 behaviors * 4 constraints * 3 invariants) -- 2 issue(s)

  DRIFT    cache_changed_subcommand -- behavior describes `cache changed` command
           which has been removed. Update spec to remove this behavior.

  STALE REF  src/commands/cache.rs:update_batch -- function referenced in behavior
             no longer exists as a public surface.

### [!] docs.spec.yaml -- dependency on cli.spec.yaml changed; verify no ripple effects
```

Rules:

- **Clean specs**: one header line only (no body).
- **Specs with issues**: header + indented issue lines.
- **Dependency notes**: one line prefixed with `[!]`.
- **If all specs are clean**: print only "All specs clean." and exit.

Issue types:

- `DRIFT: <name>` -- behavior/constraint diverges from current code
- `VIOLATED: <name>` -- invariant broken (**always ask whether intentional or a bug before proceeding**)
- `UNSPECCED: <description>` -- behavior present in code with no spec coverage
- `STALE REF: <path>` -- spec references an artifact that no longer exists

---

## Important Notes

- Be precise. Quote line numbers and file paths.
- Do not hallucinate behaviors -- only report what you can verify from the code.
- Pay special attention to **invariants** -- flag violations loudly and ask before proceeding.
- The spec schema is at `.notarai/notarai.spec.json` (kept current by `notarai init`).
- `export-context` does not yet consult the BLAKE3 hash cache the way the MCP `get_spec_diff` tool does, so it may surface changed files that were already reconciled in a previous run. Use `Step 6 (mark_reconciled)` to keep the cache fresh; running `notarai check` between reconciliations also helps spot stale entries.
