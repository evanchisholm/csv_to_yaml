"""CLI utility to convert a CSV file into YAML plus a JSON Schema."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a CSV file into a YAML document and JSON Schema."
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
    parser.add_argument(
        "--schema",
        type=Path,
        help="Optional output path for the JSON Schema (defaults next to YAML).",
    )
    return parser.parse_args()


def convert_csv_to_yaml(csv_path: Path, yaml_path: Path) -> Tuple[List[Dict[str, str]], Sequence[str]]:
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

    return rows, reader.fieldnames


def derive_schema_path(yaml_path: Path) -> Path:
    return yaml_path.with_name(f"{yaml_path.stem}.schema.json")


def build_schema(fieldnames: Iterable[str]) -> Dict[str, object]:
    properties = {
        name: {"type": "string"}
        for name in fieldnames
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "CSV Row",
        "type": "array",
        "items": {
            "type": "object",
            "properties": properties,
            "required": list(fieldnames),
            "additionalProperties": False,
        },
    }


def write_schema(schema: Dict[str, object], schema_path: Path) -> None:
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    _, fieldnames = convert_csv_to_yaml(args.csv_file, args.yaml_file)
    schema_path = args.schema or derive_schema_path(args.yaml_file)
    schema = build_schema(fieldnames)
    write_schema(schema, schema_path)


if __name__ == "__main__":
    main()
