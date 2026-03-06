# Agent Guidelines for Skills Repository

This document provides guidelines for agentic coding assistants working in this fork of Anthropic's skills repository, now used as a personal skills repository.

## Repository Overview

This is a personal fork of Anthropic's skills repository. It contains self-contained Claude AI skills that teach Claude how to complete specialized tasks in a repeatable way.

**Purpose**: Guide agents in understanding, using, and maintaining skills in this repository, including both existing Anthropic reference skills and custom skills.

**Current State**: Original Anthropic skills are preserved as reference/base and may be modified following their license terms. Custom skills can be added following the same structure.

## Repository Structure

- `skills/` - Individual skill directories, each with `SKILL.md` (contains Anthropic reference skills and custom skills)
- `spec/` - Agent Skills specification reference (see agentskills.io)
- `template/` - Skill template for creating new skills
- `.claude-plugin/marketplace.json` - Plugin marketplace configuration

## Submodules

This repo includes a git submodule at `skills/cnb-openapi-skills`.

After cloning, run:
```
git submodule update --init --recursive
```

To pull the latest submodule changes:
```
git submodule update --remote
```

## Skill File Format

**SKILL.md with YAML Frontmatter:**

```yaml
---
name: skill-name-here
description: Clear description of when to trigger this skill
license: Apache 2.0 | Proprietary. LICENSE.txt has complete terms
---
```

**Required Fields:**
- `name`: Lowercase with hyphens, unique identifier
- `description`: Complete, specific description of when to use this skill (triggers)
- `license`: Either "Apache 2.0" or reference to LICENSE.txt for proprietary

## Using Existing Skills

**Anthropic Reference Skills:**
- Original skills from Anthropic serve as high-quality examples
- May be modified following their license terms (check LICENSE.txt in each skill directory)
- Most are Apache 2.0; some are proprietary (docx, pdf, pptx, xlsx) - follow license terms

**Working with Skill Scripts:**
- **Black Box Principle**: Always run scripts with `--help` flag first to understand usage
- Only read script source if customization is absolutely necessary
- Scripts are designed to be invoked directly, not studied for context
- Example: `python scripts/with_server.py --help`

**Dependencies:**
- Each skill manages its own dependencies independently
- Python: `requirements.txt` with version constraints
- JS/TS: `package.json` (pnpm preferred)
- Install per-skill: `pip install -r skills/skill-name/requirements.txt`

## Creating Custom Skills

1. Start with `template/SKILL.md` as a base
2. Copy to new directory: `skills/your-skill-name/SKILL.md`
3. Write complete YAML frontmatter with descriptive name and clear trigger conditions
4. Provide actionable instructions with specific examples
5. Keep skills self-contained (don't depend on other skills)
6. Document external tool requirements
7. Test instructions in isolation and verify triggers work

## Code Style Guidelines

**Python:**
- Type hints (Python 3.9+): `def func(arg: str) -> tuple[int, str]:`
- Docstrings for modules/functions
- Use `pathlib.Path`, not `os.path`; use `argparse` for CLI scripts with clear help text
- Private functions: `_` prefix; snake_case functions, PascalCase classes, UPPER_CASE constants
- Use `defusedxml` for XML parsing
- Error handling: try/except with specific exceptions

**JavaScript/TypeScript:**
- ES6+ syntax (const/let, arrow functions, template literals)
- Async/await for promises; descriptive variable/function names
- Prefer `pnpm` over npm for dependencies

**Shell Scripts:**
- Start with `#!/bin/bash` or `#!/usr/bin/env python3`
- Use `set -e` to exit on error; detect OS: `if [[ "$OSTYPE" == "darwin"* ]]`
- Clear error messages with exit codes; include usage in comments or --help flag

**Documentation:**
- YAML frontmatter for SKILL.md; section headers: `##` for major, `###` for subsections
- Code blocks with language specified; use tables for quick reference
- Keep descriptions concise but complete

## Dependency Management

- Python: `requirements.txt` with version constraints (e.g., `anthropic>=0.39.0`)
- JS/TS: `package.json` with locked versions
- No centralized package.json or Makefile - each skill is independent
- Install dependencies per-skill as needed

## Execution and Testing

**No Centralized Test Runner:**
- Each skill defines its own testing approach
- No unified linting or testing framework

**Running Scripts:**
1. Check if script exists in `skills/skill-name/scripts/`
2. Run with `--help` to understand usage: `python scripts/script.py --help`
3. Invoke directly based on help output
- Scripts with `--help` should be invoked directly without reading source
- Examples: webapp-testing (Playwright), docx/xlsx (validation scripts)
- External tools (LibreOffice, Playwright, etc.) documented in skill SKILL.md

## Best Practices

1. **Black Box Usage**: Use `--help` before reading source - scripts designed as black boxes
2. **Self-Containment**: Each skill should work independently
3. **Security First**: Use `defusedxml` for XML, validate inputs, handle file operations safely
4. **Clear Error Messages**: Provide actionable error messages with specific suggestions
5. **Accurate Descriptions**: Skill description must clearly specify trigger conditions
6. **Examples Over Theory**: Show working code examples rather than lengthy explanations
7. **Document Dependencies**: Clearly state external tools required (LibreOffice, Playwright, etc.)
8. **Follow License Terms**: Respect license requirements when modifying existing skills

## Maintenance Guidelines

**Modifying Existing Skills:**
- Check LICENSE.txt in skill directory for terms
- Apache 2.0 skills can be freely modified
- Proprietary skills have specific terms - review carefully
- Document significant changes in skill instructions

**Creating New Skills:**
- Follow template structure; test thoroughly before committing
- Ensure trigger conditions are clear and accurate
- Document all dependencies and requirements

**General Maintenance:**
- Update descriptions when skill behavior changes
- Keep dependency versions up-to-date when needed
- Review and remove unused or outdated skills
- Maintain consistency with existing skill patterns

## License Information

**Most Skills**: Apache 2.0 License - free to modify and redistribute, must retain attribution

**Proprietary Skills**: docx, pdf, pptx, xlsx - source-available, not open source, check LICENSE.txt for specific terms

**When Modifying Skills**: Always check and follow original license terms. For Apache 2.0, modifications inherit same license. For proprietary, review specific terms before making changes.

## Common Patterns

- **Document Processing Skills**: Unpack → Modify → Repack workflow
- **Web Testing Skills**: Reconnaissance (inspect DOM) → Action pattern
- **Artifact Creation Skills**: Use bundled scripts as black boxes
- **API Integration Skills**: Read language-specific docs from subdirectories
