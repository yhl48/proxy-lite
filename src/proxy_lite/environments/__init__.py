from typing import Union

from .environment_base import (
    Action,
    BaseEnvironment,
    BaseEnvironmentConfig,
    Environments,
    Event,
    EventType,
    Observation,
)
from .webbrowser import (
    WebBrowserEnvironment,
    WebBrowserEnvironmentConfig,
)

EnvironmentConfigTypes = Union[*list(Environments._environment_config_registry.values())]
EnvironmentTypes = Union[*list(Environments._environment_registry.values())]


__all__ = [
    "Action",
    "BaseEnvironment",
    "BaseEnvironmentConfig",
    "EnvironmentConfigTypes",
    "Environments",
    "Event",
    "EventType",
    "Observation",
    "WebBrowserEnvironment",
    "WebBrowserEnvironmentConfig",
]
