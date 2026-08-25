"""
core/tools — Ferramentas do agente.

`build_orchestrator_registry()` monta o que o Nigel vê: os 5 subagentes, mais
suas ferramentas diretas. As ferramentas de especialista (calendário, e-mail,
memória, apps, web) ficam num registro separado que só os subagentes enxergam —
é isso que mantém o contexto do Nigel pequeno.
"""

from __future__ import annotations

from core.agent.registry import ToolRegistry


def build_specialist_registry() -> ToolRegistry:
    """Todas as ferramentas concretas. Consumido pelos subagentes."""
    from core.tools import calendar_tools, email_tools, memory_tools, dynamic_tools, web_tools, chat_tools
    tools = []
    tools += calendar_tools.build_tools()
    tools += email_tools.build_tools()
    tools += memory_tools.build_tools()
    tools += dynamic_tools.build_tools()
    tools += web_tools.build_tools()
    tools += chat_tools.build_tools()
    return ToolRegistry(tools)


def build_orchestrator_registry(llm_factory=None) -> ToolRegistry:
    """O que o Nigel enxerga: subagentes + lembretes + a pergunta de contexto."""
    from core.agent.subagents import build_subagent_tools
    from core.tools import schedule_tools, ask_tools

    if llm_factory is None:
        from core.llm.client import LLMClient
        llm_factory = LLMClient

    specialists = build_specialist_registry()
    tools = build_subagent_tools(specialists, llm_factory)
    tools += schedule_tools.build_tools()
    tools += ask_tools.build_tools()
    return ToolRegistry(tools)
