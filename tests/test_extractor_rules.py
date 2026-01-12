from codex_mem.config import Settings
from codex_mem.extractor import extract_memories
from codex_mem.models import TurnEvent


def test_rule_based_extraction():
    payload = {
        "thread-id": "t1",
        "turn-id": "1",
        "cwd": "/tmp/project",
        "input-messages": ["I prefer snake_case. Next: add tests."],
        "last-assistant-message": "We will use Typer CLI. TODO add export command.",
    }
    settings = Settings.from_env()
    turn = TurnEvent.from_event_payload(payload)
    memories = extract_memories(turn, settings)
    kinds = {m.kind.value for m in memories}
    assert "preference" in kinds
    assert "decision" in kinds
    assert "todo" in kinds
