---
name: doc-cleanup
description: Review documentation and propose removal of stale, duplicate, or orphaned files. Use "/doc-cleanup" to run.
invoke: user
---

# Documentation Review & Cleanup Skill

Review all documentation in this project and propose removals for unnecessary files. Be thorough but conservative—propose deletions only when confident.

## Scope

Analyze ALL documentation artifacts:
- Markdown files (`.md`)
- Inline docstrings and code comments (flag only if significantly stale)
- Generated documentation (if source exists)
- Config/setup docs

## Review Criteria

For each documentation file, check:

### 1. Staleness
- Does it describe features/code that no longer exists?
- Are code examples outdated or broken?
- Do file paths or URLs referenced still exist?

### 2. Duplication
- Is the same information documented elsewhere?
- Is there a "source of truth" that makes this redundant?

### 3. Orphaned
- Is this file linked from README or other docs?
- Is it referenced in code comments or imports?
- Would a new developer find/need this?

### 4. Auto-Generated
- Can this be regenerated from source? (API docs, type stubs)
- Is the generator still configured and working?

## Analysis Process

1. **Inventory**: List all documentation files with location and purpose
2. **Cross-Reference**: Check what references each file (links, imports, README)
3. **Validate Content**: Spot-check code examples and paths mentioned
4. **Classify**: Mark each file as KEEP, REMOVE, or UPDATE

## Output Format

### Documentation Inventory
| File | Purpose | Status | Reason |
|------|---------|--------|--------|

### Proposed Deletions
For each file proposed for removal:
```
**File**: `path/to/file.md`
**Reason**: [Staleness | Duplication | Orphaned | Auto-Generated]
**Evidence**: Specific proof (e.g., "References `src/old_module.py` which was deleted in commit abc123")
**Confidence**: [HIGH | MEDIUM | LOW]
**Risk**: What breaks if we delete this?
```

### Proposed Updates (Optional)
Files that are partially stale but worth keeping with edits.

### Summary
- Total docs reviewed: X
- Proposed for deletion: Y
- Proposed for update: Z
- Keeping as-is: W

## Confirmation Workflow

After presenting proposals:
1. Wait for user to confirm which deletions to proceed with
2. Only delete files explicitly approved
3. Suggest `git rm` for tracked files to maintain history

## Guidelines

- When in doubt, propose UPDATE instead of REMOVE
- Flag files with LOW confidence for manual review
- Check git history for recent activity before proposing deletion
- Never delete without showing evidence first
