#!/usr/bin/env python3
"""Install the personal learning framework as supported LearnHarness prompt overrides.

The app already supports per-segment overrides: files under <data>/prompts that
mirror the source segment layout, activated by boolean switches in
<data>/settings.json under agent.prompts. This script uses that mechanism.

Design rules:
  * Never edit upstream source, locales, graph, planning, assessment, Anki, or UI.
  * The override file is regenerated from the CURRENT upstream source plus a
    personal appendix, so an upstream prompt update is picked up by re-running
    this script instead of resolving a merge conflict.
  * Only the four manifest segments are written, and only their switches are set.
  * Unmanaged or hand-edited override files are never overwritten without --force.

Usage:
    python3 scripts/apply.py
    python3 scripts/apply.py --language ar
    python3 scripts/apply.py --language en --data-dir ~/.config/LearnHarness/data
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PERSONAL_ROOT = Path(__file__).resolve().parent.parent

HEADER_START = "<!-- learnharness-personal: generated file, do not edit by hand."
STATE_NAME = ".learnharness-personal.json"
LANGUAGES = ("auto", "ar", "en")


def log(msg: str = "") -> None:
    print(msg)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli_repo() -> str | None:
    return os.environ.get("LEARNHARNESS_REPO")


def cli_data_dir() -> str | None:
    return os.environ.get("LH_DATA_DIR")


def looks_like_repo(path: Path) -> bool:
    return (
        (path / "src" / "agent" / "prompts").is_dir()
        and (path / "src" / "agent" / "prompt-segments.ts").is_file()
    )


def resolve_repo(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if cli_repo():
        candidates.append(Path(cli_repo()).expanduser())
    candidates.append(Path.home() / "Work" / "LearnHarness")
    candidates.append(Path.cwd())
    for candidate in candidates:
        resolved = candidate.resolve()
        if looks_like_repo(resolved):
            return resolved
    raise SystemExit(
        "Could not find a LearnHarness checkout. Pass --repo /path/to/LearnHarness "
        "or set LEARNHARNESS_REPO."
    )


def resolve_data_dir(explicit: str | None, repo: Path) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if cli_data_dir():
        candidates.append(Path(cli_data_dir()).expanduser())
    candidates.append(repo / "data")
    candidates.append(Path.home() / ".config" / "LearnHarness" / "data")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    # Default to the repo dev data dir and create it (the app creates it too).
    chosen = (repo / "data").resolve()
    chosen.mkdir(parents=True, exist_ok=True)
    return chosen


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


def infer_language(requested: str, settings: dict) -> str:
    if requested != "auto":
        return requested
    general = settings.get("general")
    if isinstance(general, dict):
        lang = general.get("language")
        if lang in ("ar", "en"):
            return lang
    return "ar"


def arabic_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    arabic = sum(1 for ch in letters if "\u0600" <= ch <= "\u06ff")
    return arabic / len(letters)


def choose_source(
    repo: Path, segment_path: str, language: str
) -> tuple[Path, str, str]:
    """Return (path, source_kind, note).

    The app falls back to English when a locale file is missing. A locale file
    that exists but is in the wrong script (the current Arabic tree contains
    Spanish) is rejected for the same reason: wrong-language instructions are
    worse than canonical English instructions. Canonical source is preferred
    whenever the locale is not plausibly in the target language.
    """
    english = repo / "src" / "agent" / "prompts" / Path(segment_path)
    if language == "en":
        return english, "english-canonical", "English mode uses the canonical source."
    locale = repo / "src" / "agent" / "prompts" / "locales" / language / Path(segment_path)
    if locale.is_file():
        text = locale.read_text(encoding="utf-8")
        if language == "ar":
            if arabic_ratio(text) >= 0.35:
                return locale, "locale", f"Using plausibly Arabic locale: {locale.relative_to(repo)}"
            return (
                english,
                "english-fallback",
                f"Locale {locale.relative_to(repo)} exists but is not plausibly Arabic "
                f"(Arabic-letter ratio {arabic_ratio(text):.2f}); using canonical English source.",
            )
        if not re.search(r"[\u0600-\u06ff]", text):
            return locale, "locale", f"Using locale: {locale.relative_to(repo)}"
    return english, "english-fallback", "No usable locale file; using canonical English source."


def composition_header(
    segment_path: str,
    language: str,
    source: Path,
    repo: Path,
    source_kind: str,
    note: str,
    source_sha: str,
) -> str:
    try:
        source_rel = source.relative_to(repo)
    except ValueError:
        source_rel = source
    return (
        f"{HEADER_START}\n"
        f"     segment: {segment_path}\n"
        f"     language: {language}\n"
        f"     source: {source_rel}\n"
        f"     source-kind: {source_kind}\n"
        f"     source-sha256: {source_sha}\n"
        f"     generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"     note: {note}\n"
        "     Regenerate with: python3 scripts/apply.py --language "
        f"{language}\n"
        "     Remove with: python3 scripts/remove.py\n"
        "-->"
    )


def build_override(
    repo: Path, data_dir: Path, segment: dict, language: str
) -> tuple[str, dict, Path, str]:
    segment_path = segment["path"]
    appendix_rel = segment["appendix"]
    appendix = PERSONAL_ROOT / "appendices" / language / Path(appendix_rel)
    if not appendix.is_file():
        raise SystemExit(f"Missing appendix for language {language}: {appendix}")
    source, source_kind, note = choose_source(repo, segment_path, language)
    if not source.is_file():
        raise SystemExit(f"Upstream source segment not found: {source}")
    source_text = source.read_text(encoding="utf-8").strip()
    appendix_text = appendix.read_text(encoding="utf-8").strip()
    source_sha = sha256_text(source_text)
    header = composition_header(
        segment_path, language, source, repo, source_kind, note, source_sha
    )
    content = f"{header}\n\n{source_text}\n\n---\n\n{appendix_text}\n"
    meta = {
        "file": str((data_dir / "prompts" / Path(segment_path)).resolve()),
        "sha256": sha256_text(content),
        "sourcePath": str(source.relative_to(repo)) if source.is_relative_to(repo) else str(source),
        "sourceSha256": source_sha,
        "sourceKind": source_kind,
        "sourceNote": note,
        "appendix": str(appendix.relative_to(PERSONAL_ROOT)),
        "language": language,
    }
    return content, meta, source, language


def previous_switch(settings: dict, segment_path: str) -> bool | None:
    agent = settings.get("agent")
    if not isinstance(agent, dict):
        return None
    prompts = agent.get("prompts")
    if not isinstance(prompts, dict):
        return None
    value = prompts.get(segment_path)
    return value if isinstance(value, bool) else None


def set_switch(settings: dict, segment_path: str, value: bool) -> None:
    agent = settings.setdefault("agent", {})
    if not isinstance(agent, dict):
        raise SystemExit("settings.json has a non-object agent section; refusing to edit.")
    prompts = agent.setdefault("prompts", {})
    if not isinstance(prompts, dict):
        raise SystemExit("settings.json has a non-object agent.prompts section; refusing to edit.")
    prompts[segment_path] = value


def backup_file(path: Path, backup_dir: Path, label: str) -> Path | None:
    if not path.is_file():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{label}-{stamp}{path.suffix}"
    shutil.copy2(path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="LearnHarness checkout (default: LEARNHARNESS_REPO, ~/Work/LearnHarness)")
    parser.add_argument("--data-dir", help="LearnHarness data dir (default: LH_DATA_DIR, <repo>/data, ~/.config/LearnHarness/data)")
    parser.add_argument("--language", choices=LANGUAGES, default="auto", help="Appendix language (default: read settings.json, fallback ar)")
    parser.add_argument("--force", action="store_true", help="Overwrite an unmanaged or hand-edited override (a backup is kept)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    data_dir = resolve_data_dir(args.data_dir, repo)
    settings_path = data_dir / "settings.json"
    settings = read_json(settings_path)
    language = infer_language(args.language, settings)
    state_path = data_dir / STATE_NAME
    state = read_json(state_path)
    state_segments = state.get("segments") if isinstance(state.get("segments"), dict) else {}

    manifest = read_json(PERSONAL_ROOT / "manifest.json")
    segments = manifest.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SystemExit("manifest.json has no segments.")

    backups = data_dir / "backups" / "learnharness-personal"
    changes: list[str] = []
    new_state_segments: dict[str, dict] = dict(state_segments)
    settings_before = json.dumps(settings, sort_keys=True, ensure_ascii=False)

    log(f"repo:      {repo}")
    log(f"data dir:  {data_dir}")
    log(f"language:  {language} (appendix) — overrides apply in every app language")
    log(f"mode:      {'dry run' if args.dry_run else 'apply'}")
    log()

    for segment in segments:
        if not isinstance(segment, dict) or "path" not in segment or "appendix" not in segment:
            raise SystemExit(f"Invalid manifest entry: {segment!r}")
        segment_path = segment["path"]
        content, meta, source, source_lang = build_override(repo, data_dir, segment, language)
        target = data_dir / "prompts" / Path(segment_path)
        state_entry = state_segments.get(segment_path)
        exists = target.is_file()

        if exists and state_entry is None and not args.force:
            raise SystemExit(
                f"Refusing to overwrite unmanaged override: {target}\n"
                "It was not created by this script. Re-run with --force to back it up and replace it."
            )
        if exists and state_entry is not None:
            current_sha = sha256_file(target)
            if current_sha != state_entry.get("sha256") and not args.force:
                raise SystemExit(
                    f"Refusing to overwrite a hand-edited managed override: {target}\n"
                    "Re-run with --force to back it up and regenerate."
                )

        prior = state_entry.get("previousSwitch") if state_entry else previous_switch(settings, segment_path)
        if state_entry is None:
            prior = previous_switch(settings, segment_path)

        log(f"[{segment_path}]")
        log(f"  source:   {meta['sourcePath']} ({meta['sourceKind']})")
        if meta["sourceKind"] == "english-fallback":
            log(f"  note:     {meta['sourceNote']}")
        log(f"  appendix: {meta['appendix']}")
        log(f"  override: {target}")
        log(f"  switch:   agent.prompts[{segment_path!r}] = true (previous: {prior!r})")

        if not args.dry_run:
            if exists:
                backup_file(target, backups, "override-" + segment_path.replace("/", "_"))
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, target)
            new_state_segments[segment_path] = {**meta, "previousSwitch": prior}
            set_switch(settings, segment_path, True)
            changes.append(segment_path)

    if not args.dry_run:
        settings_after = json.dumps(settings, sort_keys=True, ensure_ascii=False)
        if settings_after != settings_before:
            saved = backup_file(settings_path, backups, "settings")
            if saved:
                log(f"\nsettings backup: {saved}")
            write_json_atomic(settings_path, settings)
        new_state = {
            "schema": 1,
            "tool": "learnharness-personal",
            "language": language,
            "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "segments": new_state_segments,
        }
        write_json_atomic(state_path, new_state)
        log(f"\nstate: {state_path}")
        log(f"applied {len(changes)} override(s). Restart a running dev server if it caches prompts.")
    else:
        log("\nDry run: nothing written.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
