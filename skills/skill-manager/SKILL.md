---
name: skill-manager
description: Manage this repository's skill registry, sources, enablement state, exports, dependency install plans, and migration bundles through the local skillctl CLI. Use when the user wants to list, inspect, add, scan, register, update, enable, disable, validate, lock, export, or restore skills and skill sources.
license: Apache 2.0
---

# Skill Manager

Use this skill to manage the unified skill registry for this repository.

## Rules

- Use the local `./skillctl` CLI as the source of truth for registry operations.
- Prefer `--json` for every command so results stay machine-readable.
- Start with read-only commands before changing registry state.
- For risky actions, inspect the target first, then run `doctor` if there is any doubt.
- Do not edit `registry/registry.json` by hand when the CLI can perform the operation.
- Treat `install` as plan-only unless the user explicitly asks to run installs with `--execute`.
- For external monorepos, register the repository as a source first, then register only the wanted skills.

## Recommended Command Flow

### List and inspect

```bash
./skillctl source list --json
./skillctl skill list --json
./skillctl source inspect anthropic-local --json
./skillctl source scan anthropic-local --json
./skillctl skill inspect skill-manager --json
./skillctl sync --json
```

### Add an external monorepo source

```bash
./skillctl source add external-skills \
  --url https://example.com/vendor/skills.git \
  --layout monorepo_skills \
  --skills-root skills \
  --origin third_party \
  --json
./skillctl source update external-skills --json
./skillctl source scan external-skills --json
```

Register discovered skills only after reviewing scan output:

```bash
./skillctl source scan external-skills --register --disabled --json
```

### Validate and lock

```bash
./skillctl doctor --json
./skillctl lock --json
```

### Enable or disable a skill

```bash
./skillctl skill enable skill-manager --json
./skillctl skill disable skill-manager --json
```

### Dependency install plan

```bash
./skillctl install playwright-scraper-skill --json
```

Only run installs when the user explicitly approves execution:

```bash
./skillctl install playwright-scraper-skill --execute --json
```

### Export and restore

```bash
./skillctl export --skills skill-manager config-safe --json
./skillctl restore exports/<bundle-name> --json
```

## Notes

- Export honors `export_policy`; restricted skills are metadata-only or local-only.
- Runtime assets such as `node_modules` are intentionally excluded from bundles.
- `source add` records metadata; add `--fetch` only when the source should be cloned immediately.
- `source scan --register --disabled` is safest for newly discovered external skills.
