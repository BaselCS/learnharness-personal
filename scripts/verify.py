#!/usr/bin/env python3
"""Verify the installed personal overrides against upstream source and settings.

Checks, deterministically:
  * every manifest segment has a managed state entry;
  * the override file exists and matches its recorded hash;
  * the override is exactly the documented composition (header + source + --- + appendix)
    when upstream source has not drifted;
  * the agent.prompts switch for each segment is true;
  * no upstream source, locale, or prompt-infrastructure file is modified;
  * data/prompts contains no unexpected files under the managed paths.

Exit codes: 0 = healthy (warnings allowed), 1 = a hard check failed.
Use --strict to treat upstream source drift as a failure (useful after `git pull`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply as installer  # noqa: E402

PERSONAL_ROOT = Path(__file__).resolve().parent.parent


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Malformed JSON: {path}\n  {exc}") from exc
    return value if isinstance(value, dict) else {}


def without_generation_stamp(text: str) -> str:
    """The generated timestamp changes on every rebuild; it is not content."""
    return re.sub(r"^     generated: .*$", "     generated: <stamp>", text, flags=re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo")
    parser.add_argument("--data-dir")
    parser.add_argument("--strict", action="store_true", help="Fail on upstream source drift")
    parser.add_argument("--json", action="store_true", help="Machine-readable report")
    args = parser.parse_args()

    repo = installer.resolve_repo(args.repo)
    data_dir = installer.resolve_data_dir(args.data_dir, repo)
    state_path = data_dir / installer.STATE_NAME
    state = read_json(state_path)
    settings = read_json(data_dir / "settings.json")
    manifest = read_json(PERSONAL_ROOT / "manifest.json")

    report: dict = {
        "repo": str(repo),
        "dataDir": str(data_dir),
        "stateFile": str(state_path),
        "ok": True,
        "segments": [],
        "warnings": [],
        "errors": [],
    }

    if not state:
        report["errors"].append(f"No managed state at {state_path}. Run scripts/apply.py first.")
    segments = manifest.get("segments")
    if not isinstance(segments, list):
        report["errors"].append("manifest.json has no segments list.")
        segments = []

    state_segments = state.get("segments") if isinstance(state.get("segments"), dict) else {}
    language = state.get("language", "ar")
    agent = settings.get("agent") if isinstance(settings.get("agent"), dict) else {}
    switches = agent.get("prompts") if isinstance(agent.get("prompts"), dict) else {}

    for segment in segments:
        segment_path = segment["path"]
        entry = state_segments.get(segment_path)
        item = {"path": segment_path, "ok": True, "notes": []}
        report["segments"].append(item)
        if not isinstance(entry, dict):
            item["ok"] = False
            item["notes"].append("no managed state entry")
            report["errors"].append(f"{segment_path}: no managed state entry")
            continue

        target = data_dir / "prompts" / Path(segment_path)
        if not target.is_file():
            item["ok"] = False
            item["notes"].append("override file missing")
            report["errors"].append(f"{segment_path}: override file missing at {target}")
            continue

        current_sha = installer.sha256_file(target)
        if current_sha != entry.get("sha256"):
            item["ok"] = False
            item["notes"].append("override hash differs from state (hand-edited?)")
            report["errors"].append(f"{segment_path}: hash differs from state; re-run apply.py --force to regenerate")
        else:
            item["notes"].append("hash matches state")

        if switches.get(segment_path) is not True:
            item["ok"] = False
            item["notes"].append("switch is not true")
            report["errors"].append(f"{segment_path}: agent.prompts switch is not true")

        try:
            expected, _meta, _source, _lang = installer.build_override(
                repo, data_dir, segment, language
            )
        except SystemExit as exc:
            item["ok"] = False
            item["notes"].append(str(exc))
            report["errors"].append(f"{segment_path}: {exc}")
            continue

        if entry.get("sourceSha256") != _meta["sourceSha256"]:
            note = (
                "upstream source changed since generation "
                f"({entry.get('sourceSha256', '?')[:12]} -> {_meta['sourceSha256'][:12]}); "
                "re-run scripts/apply.py to rebase the override"
            )
            item["notes"].append(note)
            report["warnings"].append(f"{segment_path}: {note}")
            if args.strict:
                item["ok"] = False
                report["errors"].append(f"{segment_path}: {note}")
        elif without_generation_stamp(target.read_text(encoding="utf-8")) != without_generation_stamp(expected):
            item["ok"] = False
            item["notes"].append("override is not the expected composition")
            report["errors"].append(f"{segment_path}: content is not the expected composition; re-run apply.py")

        if _meta["sourceKind"] == "english-fallback" and language == "ar":
            item["notes"].append(_meta["sourceNote"])

    # The upstream tree must not carry our changes.
    try:
        status = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "status",
                "--porcelain",
                "--",
                "src/agent/prompts",
                "src/agent/prompt-segments.ts",
                "src/agent/teacher-agent.ts",
                "src/store/prompt-overrides.ts",
                "src/core/settings.ts",
                "src/server/chat-handler.ts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        dirty = [line for line in status.stdout.splitlines() if line.strip()]
        if dirty:
            note = "upstream prompt/infrastructure paths are modified:\n  " + "\n  ".join(dirty)
            report["warnings"].append(note)
        else:
            report["upstreamClean"] = True
    except OSError:
        report["warnings"].append("git not available; skipped upstream-clean check")

    # Unexpected files under data/prompts: report, never delete.
    managed = {segment["path"] for segment in segments}
    prompts_root = data_dir / "prompts"
    if prompts_root.is_dir():
        unexpected = [
            str(p.relative_to(prompts_root))
            for p in prompts_root.rglob("*")
            if p.is_file() and str(p.relative_to(prompts_root)) not in managed
        ]
        if unexpected:
            report["warnings"].append(
                "data/prompts also contains unmanaged files (left untouched): "
                + ", ".join(sorted(unexpected))
            )

    report["ok"] = not report["errors"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"repo:     {repo}")
        print(f"data dir: {data_dir}")
        print(f"language: {language} (override content)")
        print()
        for item in report["segments"]:
            mark = "OK  " if item["ok"] else "FAIL"
            print(f"[{mark}] {item['path']}")
            for note in item["notes"]:
                print(f"       - {note}")
        if report["warnings"]:
            print("\nWarnings:")
            for warning in report["warnings"]:
                print(f"  ! {warning}")
        if report["errors"]:
            print("\nErrors:")
            for error in report["errors"]:
                print(f"  x {error}")
        print("\nResult:", "HEALTHY" if report["ok"] else "FAILED")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
