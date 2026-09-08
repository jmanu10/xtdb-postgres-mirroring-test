import argparse

from rich.console import Console

from app.cli import use_case
from lib.settings import load_settings

COMMANDS = (use_case,)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mirror",
        description="Reproduce XTDB DirectMirror divergences against PostgreSQL",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in COMMANDS:
        module.configure(subparsers)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.run(args, load_settings(), Console()))
