#!/usr/bin/env python3
"""Render the public-safe canonical site template for a selected site."""

from __future__ import annotations

import argparse
from pathlib import Path


def render(source: Path, destination: Path, site: str) -> None:
    text = source.read_text(encoding="utf-8")
    marker = "  name: example"
    if text.count(marker) != 1:
        raise ValueError(f"template must contain exactly one {marker!r} marker")
    rendered = text.replace(marker, f"  name: {site}", 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("site")
    args = parser.parse_args()
    render(args.source, args.destination, args.site)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
