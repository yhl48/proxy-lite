from __future__ import annotations

import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional, Self

from pydantic import BaseModel, Field

from proxy_lite.environments import EnvironmentConfigTypes
from proxy_lite.environments.environment_base import Action, Observation
from proxy_lite.history import MessageHistory
from proxy_lite.solvers import SolverConfigTypes


class Run(BaseModel):
    run_id: str  # uuid.UUID
    task: str
    created_at: str  # datetime.datetime
    complete: bool = False
    terminated_at: str | None = None  # datetime.datetime
    evaluation: dict[str, Any] | None = None
    history: list[Observation | Action] = Field(default_factory=list)
    solver_history: MessageHistory | None = None
    result: str | None = None
    env_info: dict[str, Any] = Field(default_factory=dict)
    environment: Optional[EnvironmentConfigTypes] = None
    solver: Optional[SolverConfigTypes] = None

    @classmethod
    def initialise(cls, task: str) -> Self:
        run_id = str(uuid.uuid4())
        return cls(
            run_id=run_id,
            task=task,
            created_at=str(datetime.datetime.now(datetime.UTC)),
        )

    @classmethod
    def load(cls, run_id: str) -> Self:
        with open(Path(__file__).parent.parent.parent / "local_trajectories" / f"{run_id}.json", "r") as f:
            return cls(**json.load(f))

    @property
    def observations(self) -> list[Observation]:
        return [h for h in self.history if isinstance(h, Observation)]

    @property
    def actions(self) -> list[Action]:
        return [h for h in self.history if isinstance(h, Action)]

    @property
    def last_action(self) -> Action | None:
        return self.actions[-1] if self.actions else None

    @property
    def last_observation(self) -> Observation | None:
        return self.observations[-1] if self.observations else None

    def record(
        self,
        observation: Optional[Observation] = None,
        action: Optional[Action] = None,
        solver_history: Optional[MessageHistory] = None,
    ) -> None:
        # expect only one of observation and action to be provided in order to handle ordering
        if observation and action:
            raise ValueError("Only one of observation and action can be provided")
        if observation:
            self.history.append(observation)
        if action:
            self.history.append(action)
        if solver_history:
            self.solver_history = solver_history

    def terminate(self) -> None:
        self.terminated_at = str(datetime.datetime.now(datetime.UTC))


class DataRecorder:
    def __init__(self, local_folder: str | None = None):
        self.local_folder = local_folder

    def initialise_run(self, task: str) -> Run:
        self.local_folder = Path(__file__).parent.parent.parent / "local_trajectories"
        os.makedirs(self.local_folder, exist_ok=True)
        return Run.initialise(task)

    async def terminate(
        self,
        run: Run,
        save: bool = True,
    ) -> None:
        run.terminate()
        if save:
            await self.save(run)

    async def save(self, run: Run) -> None:
        json_payload = run.model_dump()
        with open(self.local_folder / f"{run.run_id}.json", "w") as f:
            json.dump(json_payload, f)
