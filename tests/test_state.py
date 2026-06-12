from pathlib import Path

from dayzops.state import StateManager


def test_save_and_load(tmp_path: Path):
    state = StateManager(tmp_path)

    state.save(
        "test.json",
        {
            "hello": "world"
        }
    )

    result = state.load("test.json")

    assert result["hello"] == "world"