from pathlib import Path

import yaml

from main import build_schema, convert_csv_to_yaml, derive_schema_path


def write_csv(tmp_path: Path, name: str) -> Path:
    csv_path = tmp_path / name
    csv_path.write_text(
        "id,name\n"
        "1,Alice\n"
        "2,Bob\n",
        encoding="utf-8",
    )
    return csv_path


def test_convert_csv_to_yaml(tmp_path):
    csv_path = write_csv(tmp_path, "records.csv")
    yaml_path = tmp_path / "records.yaml"

    rows, headers = convert_csv_to_yaml(csv_path, yaml_path)

    assert headers == ["id", "name"]
    assert rows == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]

    written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert written == rows


def test_derive_schema_path(tmp_path):
    yaml_path = tmp_path / "output.yaml"
    derived = derive_schema_path(yaml_path)
    assert derived == tmp_path / "output.schema.json"


def test_build_schema_matches_fields():
    fields = ["id", "name"]
    schema = build_schema(fields)

    assert schema["items"]["required"] == fields
    assert set(schema["items"]["properties"].keys()) == set(fields)
    assert schema["items"]["properties"]["id"]["type"] == "string"