# Sensel Morph Linux

This is a linux implementation of sensel features, breathing new linux life into the Sensel Morph, which didn't support linux through the SenselApp.

## NotarAI

NotarAI is a continuous intent reconciliation tool that keeps specs, code, and docs aligned.

### Specs

Specs live in `.notarai/*.spec.yaml` and are the canonical source of truth.
The JSON Schema is at `.notarai/notarai.spec.json`.

### Validation

Run `notarai validate .notarai/` to validate all specs against the schema.

### Drift Detection

Run `notarai check` for deterministic, LLM-free drift analysis:

- Coverage gaps (files not governed by any spec)
- Orphaned globs (spec patterns matching no files)
- Changed files since last reconciliation
- Overlapping coverage across specs

Run `notarai check --format json` for machine-readable output.

### Reconciliation

First, check if you have access to the `/notarai-bootstrap` skill. If so, use
that and ignore the remainder of this section. Otherwise, proceed.

If you have MCP tool access, use the NotarAI MCP tools directly. They are more efficient
than export-context because they fetch diffs lazily, one spec at a time:

```
list_affected_specs    -- find which specs have changed artifacts
get_spec_diff          -- get the filtered diff for a single spec
get_changed_artifacts  -- list which artifact files changed per spec
mark_reconciled        -- update the hash cache after reconciliation
```

If you do not have MCP tool access, run:

```
notarai export-context --all --base-branch main
```

and process the output. The output includes each affected spec's content and a list of
changed files. Use your file-reading and shell tools to read the changed files and run
`git diff` to examine what changed.

For a single spec:

```
notarai export-context --spec .notarai/<name>.spec.yaml --base-branch main
```

### Bootstrap

First, check if you have access to the `/notarai-bootstrap` skill. If so, use
that and ignore the remainder of this section. Otherwise, proceed.

If this is a new project with no specs yet, run:

```
notarai export-context --bootstrap
```

and follow the instructions in the output to discover the project, interview the developer,
and draft an initial `.notarai/` spec directory. See `.notarai/bootstrap-prompt.md` for the
prompt template used by the bootstrap skill.

### MCP Server Configuration

The MCP server is configured in `.mcp.json`:

```json
{
  "mcpServers": {
    "notarai": {
      "type": "stdio",
      "command": "notarai",
      "args": ["mcp"]
    }
  }
}
```
