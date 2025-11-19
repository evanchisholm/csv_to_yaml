import json

import pytest

from jsonschema import ValidationError

from main import build_schema, convert_csv_to_yaml
from validate import validate_yaml


def test_validate_yaml_success(tmp_path):
    csv_path = tmp_path / "records.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")
    yaml_path = tmp_path / "records.yaml"
    schema_path = tmp_path / "records.schema.json"

    rows, headers = convert_csv_to_yaml(csv_path, yaml_path)
    schema = build_schema(headers)
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    validate_yaml(yaml_path, schema_path)


def test_validate_yaml_failure(tmp_path):
    csv_path = tmp_path / "records.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")
    yaml_path = tmp_path / "records.yaml"
    schema_path = tmp_path / "records.schema.json"

    rows, headers = convert_csv_to_yaml(csv_path, yaml_path)
    schema = build_schema(headers)
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("- {id: 2}", encoding="utf-8")

    with pytest.raises(ValidationError):
        validate_yaml(invalid_yaml, schema_path)