"""PromptBuilder cache prefix: stable instructions first, per-turn data last."""

import os

import yaml

from ros2_dialog_manager.dialog_context import DialogContext
from ros2_dialog_manager.dialog_frame import DialogFrame
from ros2_dialog_manager.prompt_builder import PromptBuilder

_PROMPTS = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.yaml")


def production_builder() -> PromptBuilder:
    with open(_PROMPTS) as f:
        data = yaml.safe_load(f)
    return PromptBuilder(data["dialog_manager_node"]["ros__parameters"]["prompts"])


def frame() -> DialogFrame:
    return DialogFrame.from_slots_json('{"slots": [{"name": "drink", "type": "str"}]}')


def test_prefix_ends_at_paragraph_before_first_data_placeholder():
    pb = PromptBuilder({"t": "Rules in {language}.\n\nMore rules.\n\nUSER: {user_text}\n"})
    p = pb._t("t", user_text="hi")
    assert p[: p.cache_prefix_len] == "Rules in English.\n\nMore rules.\n\n"


def test_template_opening_with_data_has_no_prefix():
    pb = PromptBuilder({"t": 'Task: "{task}"\n\nRules.'})
    assert pb._t("t", task="x").cache_prefix_len == 0


def test_prefix_is_identical_across_turns():
    pb = production_builder()
    f = frame()
    a, _ = pb.extract_slots("a coffee", f)
    b, _ = pb.extract_slots("make it a tea instead", f)
    assert a.cache_prefix_len > 1000
    assert a[: a.cache_prefix_len] == b[: b.cache_prefix_len]
    assert "a coffee" not in a[: a.cache_prefix_len]


def test_context_block_joins_the_cached_prefix():
    pb = production_builder()
    ctx = DialogContext(domain="coffee shop")
    p = pb.generate_response("order a drink", frame(), "hi", [], [], ctx)
    head = p[: p.cache_prefix_len]
    assert head.rstrip().endswith("[/CONTEXT]")
    assert "order a drink" not in head
    assert p[p.cache_prefix_len :].lstrip().startswith("CURRENT TURN")


def test_context_still_leads_templates_without_prefix():
    pb = PromptBuilder({"t": 'Task: "{task}"'})
    p = pb._inject(pb._t("t", task="x"), DialogContext(domain="clinic"))
    assert p.startswith("[CONTEXT]") and p.cache_prefix_len == 0
