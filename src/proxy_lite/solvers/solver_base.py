import logging
from abc import ABC, abstractmethod
from functools import cached_property
from typing import Optional, Self, Type, cast

from pydantic import BaseModel, Field

from proxy_lite.environments.environment_base import Action, Observation
from proxy_lite.tools import Tool


class BaseSolverConfig(BaseModel):
    pass


class BaseSolver(BaseModel, ABC):
    task: Optional[str] = None
    env_tools: list[Tool] = Field(default_factory=list)
    config: BaseSolverConfig
    logger: logging.Logger | None = None

    class Config:
        arbitrary_types_allowed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        pass

    @cached_property
    @abstractmethod
    def tools(self) -> list[Tool]: ...

    @abstractmethod
    async def initialise(
        self,
        task: str,
        env_tools: list[Tool],
        env_info: str,
    ) -> None:
        """
        Initialise the solution with the given task.
        """
        ...

    @abstractmethod
    async def act(self, observation: Observation) -> Action:
        """
        Return an action for interacting with the environment.
        """
        ...

    async def is_complete(self, observation: Observation) -> bool:
        """
        Return a boolean indicating if the task is complete.
        """
        return observation.terminated


class Solvers:
    _solver_registry: dict[str, type[BaseSolver]] = {}
    _solver_config_registry: dict[str, type[BaseSolverConfig]] = {}

    @classmethod
    def register_solver(cls, name: str):
        """
        Decorator to register a Solver class under a given name.

        Example:
            @Solvers.register_solver("my_solver")
            class MySolver(BaseSolver):
                ...
        """

        def decorator(solver_cls: type[BaseSolver]) -> type[BaseSolver]:
            cls._solver_registry[name] = solver_cls
            return solver_cls

        return decorator

    @classmethod
    def register_solver_config(cls, name: str):
        """
        Decorator to register a Solver configuration class under a given name.

        Example:
            @Solvers.register_solver_config("my_solver")
            class MySolverConfig(BaseSolverConfig):
                ...
        """

        def decorator(config_cls: type[BaseSolverConfig]) -> type[BaseSolverConfig]:
            cls._solver_config_registry[name] = config_cls
            return config_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseSolver]:
        """
        Retrieve a registered Solver class by its name.

        Raises:
            ValueError: If no such solver is found.
        """
        try:
            return cast(Type[BaseSolver], cls._solver_registry[name])
        except KeyError:
            raise ValueError(f"Solver '{name}' not found.")

    @classmethod
    def get_config(cls, name: str) -> type[BaseSolverConfig]:
        """
        Retrieve a registered Solver configuration class by its name.

        Raises:
            ValueError: If no such config is found.
        """
        try:
            return cast(Type[BaseSolverConfig], cls._solver_config_registry[name])
        except KeyError:
            raise ValueError(f"Solver config for '{name}' not found.")
