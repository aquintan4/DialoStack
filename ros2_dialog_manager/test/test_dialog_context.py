"""Unit tests for DialogContext: prompt block rendering for domain, resources,
and user emotional state, plus thread-safe state updates."""

import time
import threading

from ros2_dialog_manager.dialog_context import DialogContext, Resource, UserState

# ==== EMPTY CONTEXT ====


def test_empty_context_no_block():
    assert DialogContext().to_prompt_block() == ""


# ==== DOMAIN ====


def test_domain_in_block():
    ctx = DialogContext(domain="hospital")
    block = ctx.to_prompt_block()
    assert "hospital" in block
    assert "[CONTEXT]" in block


def test_empty_domain_no_extra_content():
    ctx = DialogContext(domain="")
    assert ctx.to_prompt_block() == ""


# ==== RESOURCES ====


def test_resource_content_appears():
    r = Resource(name="menu", description="del día", content="pizza, pasta")
    block = DialogContext(resources=[r]).to_prompt_block()
    assert "[menu]" in block
    assert "pizza" in block


def test_resource_description_in_header():
    r = Resource(name="menu", description="carta", content="item")
    block = DialogContext(resources=[r]).to_prompt_block()
    assert "carta" in block


def test_resource_no_description():
    r = Resource(name="data", description="", content="stuff")
    block = DialogContext(resources=[r]).to_prompt_block()
    assert "[data]" in block
    assert "stuff" in block


def test_multiple_resources_both_present():
    r1 = Resource(name="a", description="", content="content_a")
    r2 = Resource(name="b", description="", content="content_b")
    block = DialogContext(resources=[r1, r2]).to_prompt_block()
    assert "content_a" in block
    assert "content_b" in block


def test_block_has_context_tags():
    r = Resource(name="x", description="", content="y")
    block = DialogContext(resources=[r]).to_prompt_block()
    assert block.startswith("[CONTEXT]")
    assert "[/CONTEXT]" in block


# ==== USER STATE ====


def test_notable_emotion_appears():
    ctx = DialogContext()
    ctx.update_user_state(UserState(emotion="frustrated", confidence=0.9, source="audio"))
    assert "frustrated" in ctx.to_prompt_block()


def test_low_confidence_emotion_hidden():
    ctx = DialogContext()
    ctx.update_user_state(UserState(emotion="frustrated", confidence=0.3, source="audio"))
    assert "frustrated" not in ctx.to_prompt_block()


def test_neutral_emotion_always_hidden():
    ctx = DialogContext()
    ctx.update_user_state(UserState(emotion="neutral", confidence=0.99, source="audio"))
    assert "neutral" not in ctx.to_prompt_block()


def test_expired_emotion_hidden():
    ctx = DialogContext()
    old_state = UserState(
        emotion="angry",
        confidence=0.9,
        source="vision",
        timestamp=time.monotonic() - 60.0,  # 60 s ago, TTL = 30 s
    )
    ctx.update_user_state(old_state)
    assert "angry" not in ctx.to_prompt_block()


def test_recent_notable_emotion_visible():
    ctx = DialogContext()
    ctx.update_user_state(UserState(emotion="happy", confidence=0.8, source="inferred"))
    assert "happy" in ctx.to_prompt_block()


# ==== USER STATE IS_NOTABLE ====


def test_is_notable_true():
    s = UserState(emotion="sad", confidence=0.7, source="audio")
    assert s.is_notable() is True


def test_is_notable_neutral_false():
    s = UserState(emotion="neutral", confidence=0.9, source="audio")
    assert s.is_notable() is False


def test_is_notable_low_confidence_false():
    s = UserState(emotion="angry", confidence=0.4, source="audio")
    assert s.is_notable() is False


def test_is_notable_expired_false():
    s = UserState(
        emotion="happy",
        confidence=0.9,
        source="audio",
        timestamp=time.monotonic() - 60.0,
    )
    assert s.is_notable() is False


# ==== THREAD SAFETY ====


def test_update_user_state_concurrent():
    ctx = DialogContext()
    errors = []

    def writer():
        try:
            for _ in range(200):
                ctx.update_user_state(UserState(emotion="happy", confidence=0.9, source="test"))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
