"""Validate a YAML document against a JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a YAML file against a JSON Schema file."
    )
    parser.add_argument(
        "yaml_file",
        type=Path,
        help="Path to the YAML file to validate.",
    )
    parser.add_argument(
        "schema_file",
        type=Path,
        help="Path to the JSON Schema file.",
    )
    return parser.parse_args()


def load_yaml(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_schema(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Schema file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_yaml(yaml_file: Path, schema_file: Path) -> None:
    data = load_yaml(yaml_file)
    schema = load_schema(schema_file)
    validator = Draft202012Validator(schema)
    validator.validate(data)


def main() -> None:
    args = parse_args()
    try:
        validate_yaml(args.yaml_file, args.schema_file)
    except ValidationError as exc:
        print(f"Validation failed: {exc.message}", file=sys.stderr)
        sys.exit(1)
    print("Validation succeeded.")
if __name__ == "__main__":
    main()
