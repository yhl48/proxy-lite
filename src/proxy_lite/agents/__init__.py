from typing import Union

from .agent_base import Agents, BaseAgent, BaseAgentConfig
from .proxy_lite_agent import ProxyLiteAgent, ProxyLiteAgentConfig

AgentTypes = Union[*list(Agents._agent_registry.values())]
AgentConfigTypes = Union[*list(Agents._agent_config_registry.values())]


__all__ = [
    "AgentConfigTypes",
    "AgentTypes",
    "Agents",
    "BaseAgent",
    "BaseAgentConfig",
    "ProxyLiteAgent",
    "ProxyLiteAgentConfig",
]
