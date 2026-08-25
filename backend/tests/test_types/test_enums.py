import json

from bioagent.enums import Category, Runtime, TaskStatus

EXPECTED = {
    Category: {"single_gene", "dge", "enrichment", "network", "survival"},
    Runtime: {"python", "r"},
    TaskStatus: {"pending", "running", "completed", "failed"},
}


def test_exhaustive_values() -> None:
    for enum_cls, expected in EXPECTED.items():
        assert {m.value for m in enum_cls} == expected


def test_naming_convention() -> None:
    for enum_cls in EXPECTED:
        assert all(m.value == m.name.lower() for m in enum_cls)


def test_str_enum_json_serializable() -> None:
    assert json.dumps(Category.SINGLE_GENE) == '"single_gene"'
