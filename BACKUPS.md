# Backups and Restore Guide

This repository maintains explicit backup points (branches/tags) to make it easy to restore or branch off from a known-good state.

## Current backup points

- Date: 2025-11-05
  - Branch: `backup/2025-11-05_pre_mods`
  - Tag: `backup-2025-11-05`
  - Commit: `be200e2`

## Typical restore workflows

Pick the workflow that matches what you want to do.

### 1) Explore the backup state (no changes)

```bash
# Switch to the backup branch (read/write allowed on your local clone)
git switch backup/2025-11-05_pre_mods

# Or check out the tag (detached HEAD, read-only until you create a branch)
git checkout tags/backup-2025-11-05
```

### 2) Create a new working branch from the backup

```bash
# From the backup branch
git switch -c restore-2025-11-05 backup/2025-11-05_pre_mods

# Or from the tag
git switch -c restore-2025-11-05 backup-2025-11-05
```

### 3) Restore main to the backup (advanced, use with caution)

If you need to move `main` back to the backup state, consider opening a PR from the backup branch. If you must force-reset:

```bash
# HARD RESET YOUR LOCAL MAIN TO THE BACKUP COMMIT
git switch main
git reset --hard be200e2

# FORCE-PUSH TO REMOTE MAIN (this rewrites history)
git push --force-with-lease origin main
```

### 4) Cherry-pick specific changes from the backup

```bash
# Example: cherry-pick one commit from the backup into your current branch
git cherry-pick be200e2
```

## Discover available backup points

```bash
# List backup tags
git tag -l 'backup-*'

# List backup branches
git branch -a | grep backup/
```

## Cleanup (optional)

If you no longer need the backup artifacts:

```bash
# Delete the backup branch locally and remotely
git branch -D backup/2025-11-05_pre_mods
git push origin --delete backup/2025-11-05_pre_mods

# Delete the backup tag locally and remotely
git tag -d backup-2025-11-05
git push origin --delete backup-2025-11-05
```

## Notes

- Prefer creating a new branch from the backup (safe) over force-resetting `main` (disruptive).
- When sharing the backup point with collaborators, reference the tag `backup-2025-11-05` and commit `be200e2` for an immutable pointer.
- If you need additional periodic backups, create a dated branch/tag pair following the naming used here.
