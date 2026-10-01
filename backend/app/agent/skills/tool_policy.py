"""Fail-closed tool policy helpers shared by all Skill execution paths."""

from typing import Any, Iterable, Set

from app.agent.tool_registry import TOOL_META


def allowed_tool_names_for_skill(
    skill: Any,
    candidate_names: Iterable[str],
) -> Set[str]:
    """Return the candidate tools permitted by a Skill's allow/deny policy."""
    candidates = {str(name) for name in candidate_names if name}
    if skill is None:
        return candidates

    banned = set(getattr(skill, "banned_tools", None) or [])
    allowed = set(getattr(skill, "allowed_tools", None) or [])

    if allowed:
        return (candidates & allowed) - banned

    if getattr(skill, "implementation_status", "planned") == "planned":
        file_tools = {
            name
            for name, metadata in TOOL_META.items()
            if metadata.get("category") == "file_io"
        }
        return (candidates & file_tools) - banned

    # Implemented and partial skills must declare their capability boundary.
    # An empty allowlist is a configuration error and must not expose everything.
    return set()


def filter_tool_schema_for_skill(tools_schema: list, skill: Any) -> list:
    """Filter an OpenAI tool schema without falling back when no tool is allowed."""
    if skill is None:
        return list(tools_schema or [])

    schema = list(tools_schema or [])
    candidate_names = {
        item.get("function", {}).get("name", "")
        for item in schema
    }
    allowed_names = allowed_tool_names_for_skill(skill, candidate_names)
    return [
        item
        for item in schema
        if item.get("function", {}).get("name", "") in allowed_names
    ]
