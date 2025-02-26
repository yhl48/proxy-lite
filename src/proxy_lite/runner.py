import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal, Self
import json

from omegaconf import OmegaConf
from pydantic import BaseModel

from proxy_lite.environments import (
    Action,
    BaseEnvironment,
    EnvironmentConfigTypes,
    Environments,
    EventType,
    Observation,
)
from proxy_lite.logger import create_logger
from proxy_lite.recorder import DataRecorder, Run
from proxy_lite.solvers import (
    BaseSolver,
    SolverConfigTypes,
    Solvers,
)


@asynccontextmanager
async def async_timeout(timeout: float, task_name: str = "timeout"):
    try:
        async with asyncio.TaskGroup() as tg:

            async def timeout_task():
                await asyncio.sleep(timeout)
                raise TimeoutError(
                    f"Operation {task_name} timed out after {timeout} seconds",
                )

            # Create the timeout task
            timeout_handle = tg.create_task(timeout_task())

            try:
                yield
            finally:
                timeout_handle.cancel()
    except* asyncio.TimeoutError as eg:
        for e in eg.exceptions:
            raise e
    except* Exception as eg:
        for e in eg.exceptions:
            raise e


class RunnerConfig(BaseModel):
    environment: EnvironmentConfigTypes
    solver: SolverConfigTypes

    save_every_step: bool = True
    max_steps: int = 50
    action_timeout: float = 60.0
    environment_timeout: float = 30.0
    task_timeout: float = 1800.0
    logger_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    detailed_logger_name: bool = False

    @classmethod
    def from_dict(cls, config_dict: dict) -> Self:
        conf = OmegaConf.create(config_dict)
        config_dict = OmegaConf.to_container(conf, resolve=True)
        return cls(**config_dict)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> Self:
        conf = OmegaConf.load(yaml_path)
        config_dict = OmegaConf.to_container(conf, resolve=True)
        return cls(**config_dict)


class Runner(BaseModel):
    config: RunnerConfig
    recorder: DataRecorder | None = None
    environment: type[BaseEnvironment] | None = None
    solver: type[BaseSolver] | None = None
    logger: logging.Logger | None = None
    _run: Run | None = None

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        self.environment = Environments.get(self.config.environment.name)
        self.solver = Solvers.get(self.config.solver.name)
        self.recorder = DataRecorder()
        self.logger = create_logger(
            name=f"([bold purple]{self.config.solver.name}[/]-[bold blue]{self.config.environment.name}[/])",
            level=self.config.logger_level,
            detailed_name=self.config.detailed_logger_name,
        )

    def _is_stuck_in_loop(self, run: Run, last_n: int = 3) -> bool:
        """Check if the last N observations and actions are repeating"""
        if len(run.observations) < last_n * 2:
            return False
            
        recent_obs = [o.state.text for o in run.observations[-last_n:]]
        previous_obs = [o.state.text for o in run.observations[-(last_n*2):-last_n]]
        
        return recent_obs == previous_obs

    async def run_generator(self, task: str) -> AsyncIterator[Run]:
        async with (
            async_timeout(self.config.task_timeout, "Task"),
        ):
            if self.config.logger_level is not None:
                self.logger.setLevel(self.config.logger_level)
            run = self.recorder.initialise_run(task)
            run.environment = self.config.environment
            run.solver = self.config.solver
            self.logger.debug(f"Run intialised: {run.run_id}")
            event_queue = asyncio.Queue()
            async with (
                self.environment(
                    config=self.config.environment,
                    logger=self.logger,
                ) as environment,
                self.solver(config=self.config.solver, logger=self.logger) as solver,
            ):
                run.env_info = await environment.get_info()
                await solver.initialise(
                    task,
                    environment.tools,
                    environment.info_for_user,
                )
                self.logger.debug("Solver initialised.")
                run.solver_history = solver.history
                observation: Observation = await environment.initialise()
                await event_queue.put(observation)
                self.logger.debug("Environment initialised.")
                step_count = 0
                consecutive_loops = 0
                while step_count < self.config.max_steps:
                    event = await event_queue.get()
                    self.logger.debug(f"🤖 [bold purple]Processing event:[/] {event.type}")
                    
                    # Check for loops every few steps
                    if step_count > 0 and step_count % 3 == 0:
                        if self._is_stuck_in_loop(run):
                            consecutive_loops += 1
                            if consecutive_loops >= 2:
                                self.logger.warning("Detected action loop - forcing task completion")
                                # Force the agent to return a message about the issue
                                action = Action(
                                    text="Unable to complete task - actions are not having the expected effect",
                                    tool_calls=[{
                                        "function": {
                                            "name": "return_value",
                                            "arguments": json.dumps({
                                                "value": "I was unable to complete the task because my actions were not having the expected effect. This might be due to website limitations or technical issues."
                                            })
                                        }
                                    }]
                                )
                                run.record(action=action)
                                run.complete = True
                                break
                        else:
                            consecutive_loops = 0
                        
                    match event.type:
                        case EventType.OBSERVATION:
                            observation: Observation = event
                            run.record(
                                observation=observation,
                                solver_history=solver.history,
                            )
                            async with async_timeout(
                                self.config.action_timeout,
                                "Action decision",
                            ):
                                action: Action = await solver.act(observation)
                            await event_queue.put(action)
                        case EventType.ACTION:
                            action: Action = event
                            self.logger.debug(f"Tool calls: {action.tool_calls}")
                            run.record(action=action, solver_history=solver.history)
                            run.complete = await solver.is_complete(observation)
                            if self.config.save_every_step:
                                await self.recorder.save(run)
                            if run.complete:
                                run.result = action.text
                                self.logger.info(f"🤖 [bold purple]Task complete.[/] ✨ \n{run.result}")
                                break
                            async with async_timeout(
                                self.config.environment_timeout,
                                "Environment response",
                            ):
                                observation: Observation = await environment.execute_action(action)
                                step_count += 1
                            await event_queue.put(observation)
                    yield run
                if not run.complete:
                    self.logger.warning("🤖 [bold purple]Ran out of steps!")
                await self.recorder.terminate(run, save=True)
        yield run

    async def run(self, task: str) -> Run:
        async for run in self.run_generator(task):
            self._run = run
        return run

    def run_concurrent(self, tasks: list[str]) -> list[Run]:
        async def gather_runs():
            return await asyncio.gather(
                *[self.run(task) for task in tasks],
                return_exceptions=True,
            )

        return asyncio.run(gather_runs())

    @property
    def complete(self) -> bool:
        if self._run is None:
            raise RuntimeError("Run not initialised")
        return self._run.complete

    @property
    def run_id(self) -> str:
        if self._run is None:
            raise RuntimeError("Run not initialised")
        return self._run.run_id

    @property
    def run_result(self) -> str:
        if self._run is None:
            raise RuntimeError("Run not initialised")
        return self._run.result


if __name__ == "__main__":
    from proxy_lite.logger import logger

    config = RunnerConfig.from_dict(
        {
            "environment": {
                "name": "webbrowser",
                "homepage": "https://www.google.com",
                "viewport_width": 1280,
                "viewport_height": 1920,
                "screenshot_delay": 1,
                "headless": False,
            },
            "solver": {
                "name": "simple",
                "agent": {
                    "name": "proxy_lite",
                    "client": {
                        "name": "convergence",
                        "model_id": "convergence-ai/proxy-lite",
                        "api_base": "https://convergence-ai-demo-api.hf.space/v1",
                    },
                },
            },
            "max_steps": 150,
            "action_timeout": 1800,
            "environment_timeout": 1800,
            "task_timeout": 18000,
            "logger_level": "DEBUG",
        },
    )
    logger.info(f"🤖 [bold purple]Config:[/] {config}")

    runner = Runner(config=config)
    result = asyncio.run(runner.run("Tell me the tesla stock price."))
    print(runner.run_result)
    print(runner.complete)
