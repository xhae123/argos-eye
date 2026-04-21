"""CLI entry point — `argos-eye init` installs the skill into Claude Code."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from importlib import resources
from pathlib import Path


SKILL_NAME = "argos-eye"


def default_skills_dir() -> Path:
    override = os.environ.get("CLAUDE_SKILLS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "skills"


def skill_source_dir() -> Path:
    with resources.as_file(resources.files("argos_eye").joinpath("skill_files")) as src:
        return Path(src)


def cmd_init(args: argparse.Namespace) -> int:
    skills_dir = Path(args.skills_dir).expanduser() if args.skills_dir else default_skills_dir()
    target = skills_dir / SKILL_NAME
    source = skill_source_dir()

    if not source.exists():
        print(f"error: packaged skill files not found at {source}", file=sys.stderr)
        return 1

    skills_dir.mkdir(parents=True, exist_ok=True)

    if target.exists():
        if not args.force:
            print(f"{target} already exists. Use --force to overwrite.", file=sys.stderr)
            return 1
        shutil.rmtree(target)

    shutil.copytree(source, target)
    print(f"installed argos-eye skill at {target}")
    print("restart Claude Code, then try:  /argos-eye")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    skills_dir = Path(args.skills_dir).expanduser() if args.skills_dir else default_skills_dir()
    target = skills_dir / SKILL_NAME
    if not target.exists():
        print(f"nothing to remove at {target}")
        return 0
    shutil.rmtree(target)
    print(f"removed {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos-eye",
        description="Install and manage the argos-eye Claude Code skill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Install the skill into Claude Code.")
    init_p.add_argument("--skills-dir", help="Override the Claude skills directory.")
    init_p.add_argument("--force", action="store_true", help="Overwrite an existing install.")
    init_p.set_defaults(func=cmd_init)

    un_p = sub.add_parser("uninstall", help="Remove the skill from Claude Code.")
    un_p.add_argument("--skills-dir", help="Override the Claude skills directory.")
    un_p.set_defaults(func=cmd_uninstall)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
