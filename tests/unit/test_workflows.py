"""Sanity checks for the exported n8n workflows and Make blueprints."""

import json
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).parents[2] / "workflows"
N8N = sorted((WORKFLOWS / "n8n").glob("*.json"))
MAKE = sorted((WORKFLOWS / "make").glob("*.blueprint.json"))


def test_both_flows_exported_for_both_tools() -> None:
    assert [p.name for p in N8N] == ["daily-price-monitor.json", "lead-intake.json"]
    assert [p.name for p in MAKE] == [
        "daily-price-monitor.blueprint.json",
        "lead-intake.blueprint.json",
    ]


@pytest.mark.parametrize("path", N8N, ids=lambda p: p.name)
def test_n8n_connections_point_to_existing_nodes(path: Path) -> None:
    wf = json.loads(path.read_text(encoding="utf-8"))
    names = {n["name"] for n in wf["nodes"]}
    assert len(names) == len(wf["nodes"]), "duplicate node names"
    for source, outputs in wf["connections"].items():
        assert source in names
        for branch in outputs["main"]:
            for link in branch:
                assert link["node"] in names


@pytest.mark.parametrize("path", N8N, ids=lambda p: p.name)
def test_n8n_calls_toolkit_with_api_key_and_no_secrets(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "$env.TOOLKIT_API_URL" in text
    assert "$env.TOOLKIT_API_KEY" in text
    assert "change-me" not in text
    assert "hooks.slack.com/services/T" not in text


@pytest.mark.parametrize("path", MAKE, ids=lambda p: p.name)
def test_make_blueprint_shape(path: Path) -> None:
    bp = json.loads(path.read_text(encoding="utf-8"))
    ids = [m["id"] for m in bp["flow"]]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    assert all(":" in m["module"] for m in bp["flow"])
    assert "YOUR_API_KEY" in path.read_text(encoding="utf-8")  # placeholder, not a real key
