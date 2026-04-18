#!/usr/bin/env python3
"""Repository-local skill source manager.

This CLI is the control plane for the skills registry in this repository.
It is designed to be called by both humans and agents, so every read command
supports `--json` and returns stable top-level keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "registry" / "registry.json"
LOCK_PATH = REPO_ROOT / "registry" / "locks.json"
EXPORT_ROOT = REPO_ROOT / "exports"
RESTORE_ROOT = REPO_ROOT / "restores"
CACHE_ROOT = REPO_ROOT / ".skillctl" / "sources"
COPY_IGNORE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "node_modules",
}


class SkillCtlError(RuntimeError):
    """User-facing error with a stable exit path."""


@dataclass
class Registry:
    """In-memory registry model."""

    data: dict[str, Any]

    @property
    def version(self) -> int:
        return int(self.data.get("version", 1))

    @property
    def sources(self) -> list[dict[str, Any]]:
        return list(self.data.get("sources", []))

    @property
    def skills(self) -> list[dict[str, Any]]:
        return list(self.data.get("skills", []))

    def source_map(self) -> dict[str, dict[str, Any]]:
        return {source["id"]: source for source in self.sources}

    def skill_map(self) -> dict[str, dict[str, Any]]:
        return {skill["id"]: skill for skill in self.skills}

    def get_source(self, source_id: str) -> dict[str, Any]:
        source = self.source_map().get(source_id)
        if source is None:
            raise SkillCtlError(f"unknown source: {source_id}")
        return source

    def get_skill(self, skill_id: str) -> dict[str, Any]:
        skill = self.skill_map().get(skill_id)
        if skill is None:
            raise SkillCtlError(f"unknown skill: {skill_id}")
        return skill

    def save(self) -> None:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_PATH.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_registry() -> Registry:
    if not REGISTRY_PATH.exists():
        raise SkillCtlError(f"registry not found: {REGISTRY_PATH}")
    return Registry(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))


def _slug(value: str) -> str:
    chars: list[str] = []
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-") or "skill"


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SkillCtlError(proc.stderr.strip() or proc.stdout.strip() or "git failed")
    return proc.stdout.strip()


def _run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, check=False)
    return {
        "command": command,
        "cwd": _display_path(cwd),
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _read_frontmatter(skill_file: Path) -> dict[str, Any]:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    lines = text.splitlines()
    fields: dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    return fields


def _rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def _display_path(path: Path) -> str:
    try:
        return _rel(path)
    except ValueError:
        return str(path)


def _source_root(source: dict[str, Any]) -> Path:
    return REPO_ROOT / source["local_path"]


def _skill_dir(source: dict[str, Any], skill: dict[str, Any]) -> Path:
    return (_source_root(source) / skill["relative_path"]).resolve()


def _classify_license(source: dict[str, Any], discovery: dict[str, Any]) -> str:
    skill_root = _source_root(source) / discovery["relative_path"]
    frontmatter_license = discovery.get("license", "").lower()
    if discovery["id"] in {"docx", "pdf", "pptx", "xlsx"}:
        return "restricted"
    license_file = skill_root / "LICENSE.txt"
    if "proprietary" in frontmatter_license:
        return "restricted"
    if license_file.exists():
        text = license_file.read_text(encoding="utf-8", errors="ignore").lower()
        if "additional restrictions" in text or "all rights reserved" in text:
            return "restricted"
        if "apache license" in text:
            return "apache"
    if "apache" in frontmatter_license:
        return "apache"
    if source["origin"] == "custom":
        return "custom"
    return "unknown"


def _runtime_from_dependencies(dependency_files: list[str], entry_files: list[str]) -> str:
    if "package.json" in dependency_files:
        return "node"
    if "requirements.txt" in dependency_files or "python" in entry_files:
        return "python"
    if "scripts" in entry_files:
        return "mixed"
    return "none"


def _skill_record_from_discovery(
    source: dict[str, Any],
    discovery: dict[str, Any],
    *,
    enabled: bool,
    skill_id: str | None = None,
) -> dict[str, Any]:
    license_class = _classify_license(source, discovery)
    return {
        "id": skill_id or discovery["id"],
        "source_id": source["id"],
        "relative_path": discovery["relative_path"],
        "enabled": enabled,
        "license_class": license_class,
        "export_policy": "local_only" if license_class == "restricted" else "allowed",
        "runtime": _runtime_from_dependencies(discovery["dependency_files"], discovery["entry_files"]),
        "dependency_files": discovery["dependency_files"],
        "entry_files": discovery["entry_files"],
        "tags": [source["origin"]],
    }


def _discover_skills(source: dict[str, Any]) -> list[dict[str, Any]]:
    root = _source_root(source)
    layout = source["repo_layout"]
    include_paths = set(source.get("include_paths", []))
    discoveries: list[dict[str, Any]] = []

    candidates: list[Path] = []
    if layout == "direct_children":
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if include_paths and child.name not in include_paths:
                continue
            if (child / "SKILL.md").exists():
                candidates.append(child)
    elif layout == "single_skill":
        if (root / "SKILL.md").exists():
            candidates.append(root)
    elif layout == "monorepo_skills":
        skills_root = root / source["skills_root"]
        for child in sorted(skills_root.iterdir()):
            if not child.is_dir():
                continue
            if include_paths and child.name not in include_paths:
                continue
            if (child / "SKILL.md").exists():
                candidates.append(child)
    else:
        raise SkillCtlError(f"unsupported repo_layout: {layout}")

    for candidate in candidates:
        skill_file = candidate / "SKILL.md"
        frontmatter = _read_frontmatter(skill_file)
        relative_path = candidate.relative_to(root).as_posix() if candidate != root else "."
        dependency_files = [
            name
            for name in ("requirements.txt", "package.json")
            if (candidate / name).exists()
        ]
        entry_files = ["SKILL.md"]
        for name in ("scripts", "references", "examples", "assets", "python", "typescript"):
            if (candidate / name).exists():
                entry_files.append(name)
        discoveries.append(
            {
                "id": frontmatter.get("name", candidate.name),
                "display_name": frontmatter.get("name", candidate.name),
                "description": frontmatter.get("description", ""),
                "license": frontmatter.get("license", ""),
                "relative_path": relative_path,
                "dependency_files": dependency_files,
                "entry_files": entry_files,
            }
        )
    return discoveries


def _output(payload: Any, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, dict):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(payload)


def _repo_commit() -> str:
    return _run_git(["rev-parse", "HEAD"])


def _tracked_files(path: Path) -> set[str]:
    try:
        rel_path = _rel(path)
    except ValueError:
        return set()
    proc = subprocess.run(
        ["git", "ls-files", rel_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _issue(severity: str, code: str, target_type: str, target_id: str, message: str) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "target_type": target_type,
        "target_id": target_id,
        "message": message,
    }


def cmd_source_list(args: argparse.Namespace) -> None:
    registry = _load_registry()
    items = [
        {
            "id": source["id"],
            "source_kind": source["source_kind"],
            "fetch_strategy": source["fetch_strategy"],
            "repo_layout": source["repo_layout"],
            "origin": source["origin"],
            "status": source["status"],
            "local_path": source["local_path"],
        }
        for source in registry.sources
    ]
    _output({"sources": items}, args.json)


def cmd_source_inspect(args: argparse.Namespace) -> None:
    registry = _load_registry()
    source = registry.get_source(args.source_id)
    discoveries = _discover_skills(source)
    _output({"source": source, "discovered_skills": discoveries}, args.json)


def cmd_source_add(args: argparse.Namespace) -> None:
    registry = _load_registry()
    if args.source_id in registry.source_map():
        raise SkillCtlError(f"source already exists: {args.source_id}")
    if args.source_kind == "external_git" and not args.source_url:
        raise SkillCtlError("external_git sources require --url")
    if args.repo_layout == "monorepo_skills" and not args.skills_root:
        raise SkillCtlError("monorepo_skills sources require --skills-root")

    local_path = args.local_path
    if local_path is None:
        if args.source_kind == "external_git":
            local_path = (CACHE_ROOT / args.source_id).relative_to(REPO_ROOT).as_posix()
        else:
            local_path = f"skills/{args.source_id}"

    source: dict[str, Any] = {
        "id": args.source_id,
        "source_kind": args.source_kind,
        "fetch_strategy": args.fetch_strategy,
        "repo_layout": args.repo_layout,
        "local_path": local_path,
        "origin": args.origin,
        "status": args.status,
    }
    if args.source_url:
        source["source_url"] = args.source_url
    if args.source_ref:
        source["source_ref"] = args.source_ref
    if args.skills_root:
        source["skills_root"] = args.skills_root
    if args.include_path:
        source["include_paths"] = args.include_path

    fetch_result = None
    if args.fetch:
        fetch_result = _fetch_source(source)
    registry.data.setdefault("sources", []).append(source)
    registry.save()
    _output({"source": source, "fetch_result": fetch_result}, args.json)


def _fetch_source(source: dict[str, Any]) -> dict[str, Any]:
    root = _source_root(source)
    if source["source_kind"] != "external_git":
        return {"status": "skipped", "reason": "managed source"}
    if source["fetch_strategy"] == "submodule":
        result = _run_command(["git", "submodule", "update", "--init", "--recursive", source["local_path"]], REPO_ROOT)
        if result["returncode"] != 0:
            raise SkillCtlError(result["stderr"] or result["stdout"] or "submodule update failed")
        return result
    if source["fetch_strategy"] not in {"detached_clone", "mirror_clone"}:
        return {"status": "skipped", "reason": f"unsupported fetch_strategy={source['fetch_strategy']}"}
    if root.exists():
        return {"status": "exists", "path": source["local_path"]}
    root.parent.mkdir(parents=True, exist_ok=True)
    clone_args = ["git", "clone"]
    if source["fetch_strategy"] == "mirror_clone":
        clone_args.append("--mirror")
    clone_args.extend([source["source_url"], str(root)])
    result = _run_command(clone_args, REPO_ROOT)
    if result["returncode"] != 0:
        raise SkillCtlError(result["stderr"] or result["stdout"] or "git clone failed")
    if source.get("source_ref") and source["fetch_strategy"] == "detached_clone":
        checkout = _run_command(["git", "checkout", source["source_ref"]], root)
        if checkout["returncode"] != 0:
            raise SkillCtlError(checkout["stderr"] or checkout["stdout"] or "git checkout failed")
        result["checkout"] = checkout
    return result


def cmd_source_update(args: argparse.Namespace) -> None:
    registry = _load_registry()
    source = registry.get_source(args.source_id)
    result = _update_source(source)
    _output({"source_id": source["id"], "result": result}, args.json)


def _update_source(source: dict[str, Any]) -> dict[str, Any]:
    root = _source_root(source)
    result: dict[str, Any]
    if source["source_kind"] != "external_git":
        result = {"status": "skipped", "reason": "managed source"}
    elif source["fetch_strategy"] == "submodule":
        result = _run_command(["git", "submodule", "update", "--init", "--recursive", source["local_path"]], REPO_ROOT)
    elif source["fetch_strategy"] in {"detached_clone", "mirror_clone"}:
        if not root.exists():
            result = _fetch_source(source)
        else:
            command = ["git", "fetch", "--all", "--tags"] if source["fetch_strategy"] == "detached_clone" else ["git", "remote", "update", "--prune"]
            result = _run_command(command, root)
            if result["returncode"] == 0 and source.get("source_ref") and source["fetch_strategy"] == "detached_clone":
                result["checkout"] = _run_command(["git", "checkout", source["source_ref"]], root)
    else:
        raise SkillCtlError(f"unsupported fetch_strategy: {source['fetch_strategy']}")
    if result.get("returncode", 0) != 0:
        raise SkillCtlError(result.get("stderr") or result.get("stdout") or "source update failed")
    return result


def cmd_source_remove(args: argparse.Namespace) -> None:
    registry = _load_registry()
    source = registry.get_source(args.source_id)
    dependent_skills = [skill for skill in registry.skills if skill["source_id"] == source["id"]]
    if dependent_skills and not args.force:
        raise SkillCtlError(f"source has {len(dependent_skills)} registered skills; use --force to remove")
    registry.data["sources"] = [item for item in registry.sources if item["id"] != source["id"]]
    if args.force:
        registry.data["skills"] = [skill for skill in registry.skills if skill["source_id"] != source["id"]]
    registry.save()
    _output({"removed_source": source["id"], "removed_skills": [skill["id"] for skill in dependent_skills] if args.force else []}, args.json)


def cmd_source_scan(args: argparse.Namespace) -> None:
    registry = _load_registry()
    source = registry.get_source(args.source_id)
    discoveries = _discover_skills(source)
    registered = [skill for skill in registry.skills if skill["source_id"] == source["id"]]
    registered_by_path = {skill["relative_path"]: skill for skill in registered}
    registered_by_id = {skill["id"]: skill for skill in registered}

    unregistered: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []

    registered_new: list[dict[str, Any]] = []
    all_skill_ids = set(registry.skill_map())

    for item in discoveries:
        current = registered_by_path.get(item["relative_path"])
        if current is None:
            if args.register:
                new_id = item["id"]
                if new_id in all_skill_ids:
                    new_id = f"{source['id']}-{_slug(item['id'])}"
                record = _skill_record_from_discovery(source, item, enabled=not args.disabled, skill_id=new_id)
                registry.data.setdefault("skills", []).append(record)
                registered_new.append(record)
                all_skill_ids.add(new_id)
            else:
                unregistered.append(item)
            continue
        matched.append(
            {
                "id": current["id"],
                "relative_path": current["relative_path"],
                "status": "matched",
            }
        )
        if current["id"] != item["id"]:
            conflicts.append(
                {
                    "type": "frontmatter_name_mismatch",
                    "registered_id": current["id"],
                    "detected_id": item["id"],
                    "relative_path": item["relative_path"],
                }
            )

    for skill in registered:
        if skill["relative_path"] not in {item["relative_path"] for item in discoveries}:
            conflicts.append(
                {
                    "type": "registered_path_missing",
                    "registered_id": skill["id"],
                    "relative_path": skill["relative_path"],
                }
            )
        if skill["id"] in registered_by_id and skill["id"] != registered_by_id[skill["id"]]["id"]:
            conflicts.append({"type": "duplicate_skill_id", "registered_id": skill["id"]})

    if registered_new:
        registry.save()

    _output(
        {
            "source_id": source["id"],
            "discovered": discoveries,
            "registered": matched,
            "registered_new": registered_new,
            "unregistered": unregistered,
            "conflicts": conflicts,
        },
        args.json,
    )


def cmd_sync(args: argparse.Namespace) -> None:
    registry = _load_registry()
    source_ids = args.sources or [source["id"] for source in registry.sources]
    results: list[dict[str, Any]] = []
    for source_id in source_ids:
        source = registry.get_source(source_id)
        update_result = None
        if args.update_sources:
            try:
                update_result = _update_source(source)
            except SkillCtlError as exc:
                update_result = {"status": "failed", "error": str(exc)}
                if not args.keep_going:
                    raise
        discoveries = _discover_skills(source)
        existing_paths = {
            skill["relative_path"]
            for skill in registry.skills
            if skill["source_id"] == source_id
        }
        results.append(
            {
                "source_id": source_id,
                "update": update_result,
                "discovered_count": len(discoveries),
                "unregistered_count": len([item for item in discoveries if item["relative_path"] not in existing_paths]),
            }
        )
    _output({"results": results}, args.json)


def cmd_skill_list(args: argparse.Namespace) -> None:
    registry = _load_registry()
    items = [
        {
            "id": skill["id"],
            "source_id": skill["source_id"],
            "enabled": skill["enabled"],
            "license_class": skill["license_class"],
            "export_policy": skill["export_policy"],
            "runtime": skill["runtime"],
            "relative_path": skill["relative_path"],
        }
        for skill in registry.skills
    ]
    _output({"skills": items}, args.json)


def cmd_skill_inspect(args: argparse.Namespace) -> None:
    registry = _load_registry()
    skill = registry.get_skill(args.skill_id)
    source = registry.get_source(skill["source_id"])
    skill_path = _skill_dir(source, skill)
    frontmatter = _read_frontmatter(skill_path / "SKILL.md") if (skill_path / "SKILL.md").exists() else {}
    _output(
        {
            "skill": skill,
            "source": source,
            "resolved_path": _display_path(skill_path),
            "frontmatter": frontmatter,
        },
        args.json,
    )


def _set_skill_enabled(skill_id: str, enabled: bool) -> dict[str, Any]:
    registry = _load_registry()
    skill = registry.get_skill(skill_id)
    skill["enabled"] = enabled
    registry.save()
    return skill


def cmd_skill_enable(args: argparse.Namespace) -> None:
    skill = _set_skill_enabled(args.skill_id, True)
    _output({"skill": skill}, args.json)


def cmd_skill_disable(args: argparse.Namespace) -> None:
    skill = _set_skill_enabled(args.skill_id, False)
    _output({"skill": skill}, args.json)


def _install_plan_for_skill(registry: Registry, skill: dict[str, Any]) -> dict[str, Any]:
    source = registry.get_source(skill["source_id"])
    skill_path = _skill_dir(source, skill)
    commands: list[list[str]] = []
    for dep in skill.get("dependency_files", []):
        if dep == "requirements.txt":
            commands.append(["python3", "-m", "pip", "install", "-r", dep])
        elif dep == "package.json":
            commands.append(["npm", "install"])
    return {
        "skill_id": skill["id"],
        "cwd": _display_path(skill_path),
        "commands": commands,
    }


def cmd_install(args: argparse.Namespace) -> None:
    registry = _load_registry()
    if not args.all and not args.skills:
        raise SkillCtlError("install requires skill ids or --all")
    skills = registry.skills if args.all else [registry.get_skill(skill_id) for skill_id in args.skills]
    plans = [_install_plan_for_skill(registry, skill) for skill in skills]
    results: list[dict[str, Any]] = []
    if args.execute:
        for plan in plans:
            cwd = REPO_ROOT / plan["cwd"]
            command_results = []
            for command in plan["commands"]:
                command_results.append(_run_command(command, cwd))
            results.append({"skill_id": plan["skill_id"], "commands": command_results})
    _output({"execute": args.execute, "plans": plans, "results": results}, args.json)


def cmd_doctor(args: argparse.Namespace) -> None:
    registry = _load_registry()
    issues: list[dict[str, str]] = []
    source_ids = set()
    skill_ids = set()

    for source in registry.sources:
        source_id = source["id"]
        if source_id in source_ids:
            issues.append(_issue("error", "duplicate_source_id", "source", source_id, "duplicate source id"))
        source_ids.add(source_id)
        root = _source_root(source)
        if not root.exists():
            issues.append(_issue("error", "missing_source_path", "source", source_id, f"path not found: {source['local_path']}"))
            continue
        if source["source_kind"] == "external_git" and not source.get("source_ref"):
            issues.append(_issue("warning", "missing_source_ref", "source", source_id, "external source is not pinned"))
        if source["source_kind"] == "external_git" and source["fetch_strategy"] == "submodule":
            submodule_lines = _run_git(["submodule", "status", "--cached"]).splitlines()
            if source["local_path"] not in " ".join(submodule_lines):
                issues.append(_issue("warning", "submodule_not_registered", "source", source_id, "registry says submodule but .gitmodules does not include the path"))

    for skill in registry.skills:
        skill_id = skill["id"]
        if skill_id in skill_ids:
            issues.append(_issue("error", "duplicate_skill_id", "skill", skill_id, "duplicate skill id"))
        skill_ids.add(skill_id)
        try:
            source = registry.get_source(skill["source_id"])
        except SkillCtlError:
            issues.append(_issue("error", "missing_source", "skill", skill_id, f"unknown source_id: {skill['source_id']}"))
            continue
        skill_path = _skill_dir(source, skill)
        if not skill_path.exists():
            issues.append(_issue("error", "missing_skill_path", "skill", skill_id, f"path not found: {_rel(skill_path)}"))
            continue
        if not (skill_path / "SKILL.md").exists():
            issues.append(_issue("error", "missing_skill_md", "skill", skill_id, "SKILL.md not found"))
        frontmatter = _read_frontmatter(skill_path / "SKILL.md") if (skill_path / "SKILL.md").exists() else {}
        if frontmatter.get("name") and frontmatter["name"] != skill["id"]:
            issues.append(_issue("warning", "frontmatter_name_mismatch", "skill", skill_id, f"frontmatter name is {frontmatter['name']}"))
        if skill["license_class"] == "restricted" and skill["export_policy"] != "local_only":
            issues.append(_issue("error", "restricted_export_policy", "skill", skill_id, "restricted skills must use export_policy=local_only"))
        declared_deps = set(skill.get("dependency_files", []))
        for dep in ("requirements.txt", "package.json"):
            if (skill_path / dep).exists() and dep not in declared_deps:
                issues.append(_issue("warning", "undeclared_dependency_file", "skill", skill_id, f"{dep} exists but is not listed in dependency_files"))
        tracked = _tracked_files(skill_path)
        if any(part.endswith("/node_modules") or "/node_modules/" in part for part in tracked):
            issues.append(_issue("warning", "tracked_runtime_assets", "skill", skill_id, "tracked node_modules detected; export skips runtime assets"))

    for source in registry.sources:
        try:
            scan = _discover_skills(source)
        except Exception as exc:  # noqa: BLE001
            issues.append(_issue("error", "scan_failed", "source", source["id"], str(exc)))
            continue
        registered_paths = {skill["relative_path"] for skill in registry.skills if skill["source_id"] == source["id"]}
        for item in scan:
            if item["relative_path"] not in registered_paths:
                issues.append(_issue("warning", "unregistered_skill", "source", source["id"], f"discovered skill not in registry: {item['relative_path']}"))

    payload = {"generated_at": _iso_now(), "issues": issues}
    _output(payload, args.json)


def cmd_lock(args: argparse.Namespace) -> None:
    registry = _load_registry()
    payload: dict[str, Any] = {
        "generated_at": _iso_now(),
        "repo_commit": _repo_commit(),
        "sources": [],
        "skills": [],
    }

    for source in registry.sources:
        source_entry = {
            "id": source["id"],
            "source_kind": source["source_kind"],
            "fetch_strategy": source["fetch_strategy"],
            "local_path": source["local_path"],
            "status": source["status"],
        }
        root = _source_root(source)
        if root.exists():
            if source["source_kind"] == "external_git":
                try:
                    source_entry["resolved_ref"] = _run_git(["-C", str(root), "rev-parse", "HEAD"])
                except SkillCtlError as exc:
                    source_entry["resolved_ref_error"] = str(exc)
            else:
                source_entry["resolved_ref"] = _repo_commit()
        payload["sources"].append(source_entry)

    for skill in registry.skills:
        source = registry.get_source(skill["source_id"])
        skill_path = _skill_dir(source, skill)
        payload["skills"].append(
            {
                "id": skill["id"],
                "source_id": skill["source_id"],
                "enabled": skill["enabled"],
                "relative_path": skill["relative_path"],
                "sha256": _hash_tree(skill_path) if skill_path.exists() else None,
            }
        )

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _output({"lock_path": _rel(LOCK_PATH), "sources": payload["sources"], "skills": payload["skills"]}, args.json)


def _ignore_copy(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name in COPY_IGNORE_DIRS}


def _hash_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        if any(part in COPY_IGNORE_DIRS for part in file_path.relative_to(path).parts):
            continue
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(file_path.read_bytes()).digest())
    return digest.hexdigest()


def _checksum_manifest(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for file_path in sorted(p for p in root.rglob("*") if p.is_file()):
        checksums[file_path.relative_to(root).as_posix()] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return checksums


def cmd_export(args: argparse.Namespace) -> None:
    registry = _load_registry()
    selected_ids = args.skills
    selected_skills = [registry.get_skill(skill_id) for skill_id in selected_ids]
    bundle_name = args.name or f"skills-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    bundle_root = (REPO_ROOT / args.output / bundle_name).resolve()
    if bundle_root.exists():
        raise SkillCtlError(f"export path already exists: {bundle_root}")
    bundle_root.mkdir(parents=True)

    exported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    bundle_skills_root = bundle_root / "skills"
    bundle_skills_root.mkdir()

    for skill in selected_skills:
        source = registry.get_source(skill["source_id"])
        skill_path = _skill_dir(source, skill)
        entry = {
            "id": skill["id"],
            "source_id": skill["source_id"],
            "export_policy": skill["export_policy"],
            "license_class": skill["license_class"],
        }
        if skill["export_policy"] != "allowed":
            skipped.append({**entry, "reason": f"export_policy={skill['export_policy']}"})
            continue
        if not skill_path.exists():
            skipped.append({**entry, "reason": "skill path missing"})
            continue
        shutil.copytree(skill_path, bundle_skills_root / skill["id"], ignore=_ignore_copy)
        exported.append(entry)

    manifest = {
        "generated_at": _iso_now(),
        "registry_version": registry.version,
        "skills": [skill["id"] for skill in selected_skills],
        "exported": exported,
        "skipped": skipped,
    }
    (bundle_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    source_ids = {skill["source_id"] for skill in selected_skills}
    sources_payload = [registry.get_source(source_id) for source_id in sorted(source_ids)]
    (bundle_root / "sources.json").write_text(json.dumps({"sources": sources_payload}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    skills_payload = [skill for skill in registry.skills if skill["id"] in selected_ids]
    (bundle_root / "skills.json").write_text(json.dumps({"skills": skills_payload}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not LOCK_PATH.exists():
        cmd_lock(argparse.Namespace(json=False))
    shutil.copy2(LOCK_PATH, bundle_root / "sources.lock.json")

    checksums = _checksum_manifest(bundle_root)
    (bundle_root / "checksums.json").write_text(json.dumps(checksums, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    install_text = (
        "# Skill Export Bundle\n\n"
        "1. Copy the bundle to the target machine.\n"
        "2. Inspect `sources.json` and `skills.json`.\n"
        "3. Run `./skillctl restore <bundle-dir>` in a compatible checkout.\n"
        "4. Reinstall per-skill dependencies using the recorded dependency files.\n"
    )
    (bundle_root / "INSTALL.md").write_text(install_text, encoding="utf-8")

    _output(
        {
            "bundle_path": _rel(bundle_root),
            "exported": exported,
            "skipped": skipped,
        },
        args.json,
    )


def cmd_restore(args: argparse.Namespace) -> None:
    bundle_root = (REPO_ROOT / args.bundle).resolve() if not Path(args.bundle).is_absolute() else Path(args.bundle)
    if not bundle_root.exists():
        raise SkillCtlError(f"bundle not found: {bundle_root}")
    destination = (REPO_ROOT / args.dest).resolve() if not Path(args.dest).is_absolute() else Path(args.dest)
    if destination.exists() and any(destination.iterdir()):
        raise SkillCtlError(f"restore destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    for name in ("manifest.json", "sources.json", "skills.json", "sources.lock.json", "checksums.json", "INSTALL.md"):
        source_file = bundle_root / name
        if source_file.exists():
            shutil.copy2(source_file, destination / name)

    skills_dir = bundle_root / "skills"
    restored: list[str] = []
    if skills_dir.exists():
        target_skills = destination / "skills"
        target_skills.mkdir(exist_ok=True)
        for child in skills_dir.iterdir():
            if child.is_dir():
                shutil.copytree(child, target_skills / child.name, ignore=_ignore_copy)
                restored.append(child.name)

    _output({"destination": str(destination), "restored_skills": restored}, args.json)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillctl", description="Skill source manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    source = subparsers.add_parser("source", help="Manage skill sources")
    source_sub = source.add_subparsers(dest="source_command", required=True)

    p = source_sub.add_parser("list", help="List sources")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source_list)

    p = source_sub.add_parser("add", help="Add a source to the registry")
    p.add_argument("source_id")
    p.add_argument("--kind", dest="source_kind", choices=["managed", "external_git"], default="external_git")
    p.add_argument("--url", dest="source_url")
    p.add_argument("--ref", dest="source_ref")
    p.add_argument("--fetch-strategy", choices=["none", "submodule", "detached_clone", "mirror_clone"], default="detached_clone")
    p.add_argument("--layout", dest="repo_layout", choices=["direct_children", "single_skill", "monorepo_skills"], default="single_skill")
    p.add_argument("--skills-root")
    p.add_argument("--local-path")
    p.add_argument("--origin", choices=["anthropic", "custom", "third_party"], default="third_party")
    p.add_argument("--status", choices=["active", "archived", "experimental"], default="active")
    p.add_argument("--include-path", action="append")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source_add)

    p = source_sub.add_parser("inspect", help="Inspect one source")
    p.add_argument("source_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source_inspect)

    p = source_sub.add_parser("scan", help="Discover skills in a source")
    p.add_argument("source_id")
    p.add_argument("--register", action="store_true", help="Register discovered unregistered skills")
    p.add_argument("--disabled", action="store_true", help="Register new skills as disabled")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source_scan)

    p = source_sub.add_parser("update", help="Fetch or update an external source")
    p.add_argument("source_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source_update)

    p = source_sub.add_parser("remove", help="Remove a source from the registry")
    p.add_argument("source_id")
    p.add_argument("--force", action="store_true", help="Also remove skills registered from this source")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_source_remove)

    skill = subparsers.add_parser("skill", help="Manage skills")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)

    p = skill_sub.add_parser("list", help="List skills")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_skill_list)

    p = skill_sub.add_parser("inspect", help="Inspect one skill")
    p.add_argument("skill_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_skill_inspect)

    p = skill_sub.add_parser("enable", help="Enable a skill")
    p.add_argument("skill_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_skill_enable)

    p = skill_sub.add_parser("disable", help="Disable a skill")
    p.add_argument("skill_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_skill_disable)

    p = subparsers.add_parser("sync", help="Inspect sources and report unregistered skills")
    p.add_argument("--sources", nargs="+")
    p.add_argument("--update-sources", action="store_true")
    p.add_argument("--keep-going", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sync)

    p = subparsers.add_parser("install", help="Plan or execute per-skill dependency installs")
    p.add_argument("skills", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_install)

    p = subparsers.add_parser("doctor", help="Run consistency checks")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = subparsers.add_parser("lock", help="Write lock data")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_lock)

    p = subparsers.add_parser("export", help="Export selected skills")
    p.add_argument("--skills", nargs="+", required=True)
    p.add_argument("--output", default="exports")
    p.add_argument("--name")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_export)

    p = subparsers.add_parser("restore", help="Restore a bundle into a safe destination")
    p.add_argument("bundle")
    p.add_argument("--dest", default=str(RESTORE_ROOT / "latest"))
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_restore)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except SkillCtlError as exc:
        payload = {"error": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
