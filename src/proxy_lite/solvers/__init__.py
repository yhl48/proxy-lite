from __future__ import annotations

from typing import Union

from .simple_solver import SimpleSolver, SimpleSolverConfig
from .solver_base import BaseSolver, BaseSolverConfig, Solvers

SolverConfigTypes = Union[*Solvers._solver_config_registry.values()]
SolverTypes = Union[*Solvers._solver_registry.values()]


__all__ = [
    "BaseSolver",
    "BaseSolverConfig",
    "SimpleSolver",
    "SimpleSolverConfig",
    "SolverConfigTypes",
    "SolverTypes",
    "Solvers",
]
