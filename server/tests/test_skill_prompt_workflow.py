from server.prompts.prompt_variants import get_prompt_components
from server.prompts.prompts import get_unified_agent_prompt_compact


def test_prompt_variants_include_skill_workflow_rules_for_default_and_gpt() -> None:
    default_components = get_prompt_components()
    gpt_components = get_prompt_components("gpt-5.4")

    assert "skill_workflow_rules" in default_components
    assert "skill_workflow_rules" in gpt_components
    assert "search_enabled_skills" in default_components["skill_workflow_rules"]


def test_unified_prompt_includes_skill_workflow_section() -> None:
    prompt = get_unified_agent_prompt_compact(database_schemas=None, model="gpt-5.4")

    assert "<skill_workflow_rules>" in prompt
    assert "SKILL DISCOVERY WORKFLOW" in prompt
