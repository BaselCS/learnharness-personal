#!/usr/bin/env python3
"""Remove the personal learning framework overrides and restore the prior switches.

Only files recorded and hash-verified in <data>/.learnharness-personal.json are
deleted. A hand-edited override is left in place unless --force is given, so a
user edit can never be destroyed silently. Settings are backed up before the
switch map is restored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PERSONAL_ROOT = Path(__file__).resolve().parent.parent
STATE_NAME = ".learnharness-personal.json"


def log(msg: str = "") -> None:
    print(msg)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Refusing to touch malformed JSON: {path}\n  {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Refusing to touch non-object JSON: {path}")
    return value


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")
    os.replace(tmp, path)


def looks_like_repo(path: Path) -> bool:
    return (
        (path / "src" / "agent" / "prompts").is_dir()
        and (path / "src" / "agent" / "prompt-segments.ts").is_file()
    )


def resolve_repo(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("LEARNHARNESS_REPO"):
        candidates.append(Path(os.environ["LEARNHARNESS_REPO"]).expanduser())
    candidates.append(Path.home() / "Work" / "LearnHarness")
    candidates.append(Path.cwd())
    for candidate in candidates:
        resolved = candidate.resolve()
        if looks_like_repo(resolved):
            return resolved
    raise SystemExit("Could not find a LearnHarness checkout. Pass --repo or set LEARNHARNESS_REPO.")


def resolve_data_dir(explicit: str | None, repo: Path) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("LH_DATA_DIR"):
        candidates.append(Path(os.environ["LH_DATA_DIR"]).expanduser())
    candidates.append(repo / "data")
    candidates.append(Path.home() / ".config" / "LearnHarness" / "data")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit("No LearnHarness data dir found. Pass --data-dir or set LH_DATA_DIR.")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_file(path: Path, backup_dir: Path, label: str) -> Path | None:
    if not path.is_file():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{label}-{stamp}{path.suffix}"
    shutil.copy2(path, target)
    return target


def set_switch(settings: dict, segment_path: str, value: bool | None) -> None:
    agent = settings.setdefault("agent", {})
    if not isinstance(agent, dict):
        raise SystemExit("settings.json has a non-object agent section; refusing to edit.")
    prompts = agent.setdefault("prompts", {})
    if not isinstance(prompts, dict):
        raise SystemExit("settings.json has a non-object agent.prompts section; refusing to edit.")
    if value is None:
        prompts.pop(segment_path, None)
    else:
        prompts[segment_path] = value
    if not prompts:
        agent.pop("prompts", None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="LearnHarness checkout")
    parser.add_argument("--data-dir", help="LearnHarness data dir")
    parser.add_argument("--force", action="store_true", help="Delete hand-edited managed overrides (backup kept)")
    parser.add_argument("--keep-switches", action="store_true", help="Leave agent.prompts switches as they are")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    data_dir = resolve_data_dir(args.data_dir, repo)
    state_path = data_dir / STATE_NAME
    state = read_json(state_path)
    segments = state.get("segments")
    if not isinstance(segments, dict) or not segments:
        log(f"No managed state found at {state_path}; nothing to remove.")
        return 0

    settings_path = data_dir / "settings.json"
    settings = read_json(settings_path)
    settings_before = json.dumps(settings, sort_keys=True, ensure_ascii=False)
    backups = data_dir / "backups" / "learnharness-personal"

    log(f"repo:     {repo}")
    log(f"data dir: {data_dir}")
    log(f"mode:     {'dry run' if args.dry_run else 'remove'}")
    log()

    removed = 0
    kept = 0
    for segment_path, entry in segments.items():
        if not isinstance(entry, dict):
            continue
        target = data_dir / "prompts" / Path(segment_path)
        if target.is_file():
            current_sha = sha256_file(target)
            if current_sha != entry.get("sha256") and not args.force:
                log(f"[{segment_path}] hand-edited; kept (use --force to delete, backup kept)")
                kept += 1
            else:
                log(f"[{segment_path}] deleting {target}")
                if not args.dry_run:
                    backup_file(target, backups, "override-" + segment_path.replace("/", "_"))
                    target.unlink()
                removed += 1
        else:
            log(f"[{segment_path}] already absent")
        if not args.keep_switches:
            previous = entry.get("previousSwitch")
            if previous is not None and not isinstance(previous, bool):
                previous = None
            set_switch(settings, segment_path, previous)
            log(f"  switch restored to: {previous!r}")

    if not args.dry_run:
        if not args.keep_switches:
            settings_after = json.dumps(settings, sort_keys=True, ensure_ascii=False)
            if settings_after != settings_before:
                saved = backup_file(settings_path, backups, "settings")
                if saved:
                    log(f"\nsettings backup: {saved}")
                write_json_atomic(settings_path, settings)
        # Prune empty generated directories (never the data/prompts root).
        for directory in sorted(
            {p.parent for p in (data_dir / "prompts").rglob("*") if p.is_file()},
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        state_path.unlink(missing_ok=True)
        log(f"\nremoved {removed} override(s); kept {kept} hand-edited.")
        log(f"state removed: {state_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
