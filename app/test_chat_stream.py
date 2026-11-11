import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chat_stream  # noqa: E402


def test_system_prompt_is_appended_to_identity():
    messages = [{"role": "system", "content": "identity"},
                {"role": "user", "content": "hi"}]
    out = chat_stream._merge_system(messages, "IDE RULES")
    assert out[0]["role"] == "system"
    assert out[0]["content"] == "identity\n\nIDE RULES"
    assert out[1] == {"role": "user", "content": "hi"}


def test_system_prompt_added_when_no_system_message():
    out = chat_stream._merge_system([{"role": "user", "content": "hi"}], "IDE RULES")
    assert out[0] == {"role": "system", "content": "IDE RULES"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_system_prompt_does_not_mutate_input():
    messages = [{"role": "system", "content": "identity"}]
    chat_stream._merge_system(messages, "IDE RULES")
    assert messages == [{"role": "system", "content": "identity"}]
