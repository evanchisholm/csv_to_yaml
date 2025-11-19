"""CLI utility to convert a CSV file into a YAML document."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List, Dict

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a CSV file into a YAML document."
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to the source CSV file.",
    )
    parser.add_argument(
        "yaml_file",
        type=Path,
        help="Destination path for the generated YAML file.",
    )
    return parser.parse_args()


def convert_csv_to_yaml(csv_path: Path, yaml_path: Path) -> None:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError("CSV file is missing a header row.")
        rows: List[Dict[str, str]] = list(reader)

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with yaml_path.open("w", encoding="utf-8") as yaml_file:
        yaml.safe_dump(rows, yaml_file, sort_keys=False)


def main() -> None:
    args = parse_args()
    convert_csv_to_yaml(args.csv_file, args.yaml_file)


if __name__ == "__main__":
    main()
