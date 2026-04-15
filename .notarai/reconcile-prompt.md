# Reconciliation: {{spec_name}}

## Spec Content

```yaml
{ { spec_content } }
```

## Changed Files

The following files governed by this spec have changed since `{{base_branch}}`:

{{changed_files}}

## Instructions

For each changed file listed above:

1. Read the file's current content using your file-reading tools.
2. Run `git diff {{base_branch}} -- <file>` (or equivalent) to see what changed.

Then review the changes against the spec. For each behavior, constraint, and invariant:

- Check whether the changes support or contradict it.
- Identify any drift between spec intent and implementation.
- Propose targeted updates to bring spec, code, and docs into alignment.

The spec is the canonical tiebreaker when code and spec disagree.

Classify each finding into a severity tier and group your report accordingly:

## Critical

Behavioral or invariant violations where code contradicts the spec.

- **VIOLATED**: Code contradicts a spec constraint or invariant
- **STALE REF**: Spec references code or docs that no longer exist

## Drift

Code has changed in ways that may not align with the spec, but no clear violation.

- **DRIFT**: Code has changed in ways not reflected in the spec
- **UNSPECCED**: New code not covered by any spec behavior

## Housekeeping

Documentation, style, or organizational misalignment.

- **STALE DOC**: Documentation references outdated APIs or behaviors
- **STYLE**: Naming or organizational conventions diverged from spec

If everything aligns, report: "No drift detected."
