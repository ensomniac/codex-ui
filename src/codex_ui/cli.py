"""Thin, portable JSON entry point. Native frameworks load only for desktop work."""
from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from typing import Any

from ._version import __version__
from .config import SCHEMA_VERSION
from .parser import build_parser


def command_schema() -> dict[str, Any]:
    parser = build_parser()
    sub = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    commands = {}
    for name, command in sub.choices.items():
        commands[name] = {
            "description": command.description or next((p.help for p in sub._choices_actions if p.dest == name), ""),
            "arguments": [
                {"name": a.dest, "flags": a.option_strings, "required": a.required,
                 "choices": list(a.choices) if a.choices is not None else None,
                 "nargs": a.nargs, "help": a.help}
                for a in command._actions if a.dest != "help"
            ],
        }
    return {"commands": commands, "global_flags": ["--compact", "--version"],
            "plan_schema": "https://github.com/ensomniac/codex-ui/blob/main/docs/plan.schema.json"}


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "capabilities":
        from .backends.registry import capabilities
        return capabilities()
    if args.command == "schema":
        return command_schema()
    if args.command == "upgrade":
        from .lifecycle import upgrade
        return upgrade(check=args.check)
    if args.command == "skill":
        from .skills import install
        return install(args.agent, args.path)
    from .backends.registry import execute
    return execute(args)


def main(arguments: list[str] | None = None) -> int:
    started = time.perf_counter()
    args = build_parser().parse_args(arguments)
    output: dict[str, Any] = {"ok": True, "command": args.command, "version": __version__,
                              "schema_version": SCHEMA_VERSION}
    try:
        output.update(dispatch(args))
    except Exception as exc:
        output.update(ok=False, error={"type": type(exc).__name__, "message": str(exc)})
        if os.environ.get("CODEX_UI_DEBUG"):
            output["error"]["traceback"] = traceback.format_exc()
    output["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
    print(json.dumps(output, indent=None if args.compact else 2, sort_keys=True))
    return 0 if output["ok"] else 1
