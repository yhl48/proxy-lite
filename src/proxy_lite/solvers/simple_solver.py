# ruff: noqa: E501
import json
import re
from functools import cached_property
from typing import Literal, Optional

from proxy_lite.agents import AgentConfigTypes, Agents, BaseAgent
from proxy_lite.environments.environment_base import Action, Observation
from proxy_lite.history import (
    MessageHistory,
    MessageLabel,
    SystemMessage,
)
from proxy_lite.solvers.solver_base import BaseSolver, BaseSolverConfig, Solvers
from proxy_lite.tools import ReturnValueTool, Tool

WEB_TOOL_TURN = """The action has been attempted in the computer."""


@Solvers.register_solver_config("simple")
class SimpleSolverConfig(BaseSolverConfig):
    name: Literal["simple"] = "simple"
    agent: AgentConfigTypes


@Solvers.register_solver("simple")
class SimpleSolver(BaseSolver):
    task: Optional[str] = None
    complete: bool = False

    @cached_property
    def tools(self) -> list[Tool]:
        return [ReturnValueTool()] + self.env_tools

    @cached_property
    def agent(self) -> BaseAgent:
        self.logger.debug(f"Tools: {self.tools}")
        return Agents.get(self.config.agent.name)(
            config=self.config.agent,
            env_tools=self.tools,
        )

    @property
    def history(self) -> MessageHistory:
        return MessageHistory(
            messages=[SystemMessage.from_media(text=self.agent.system_prompt)] + self.agent.history.messages,
        )

    async def initialise(self, task: str, env_tools: list[Tool], env_info: str) -> None:
        self.env_tools = env_tools
        self.task = task
        self.agent.receive_user_message(
            text=f"Task: {task}",
            label=MessageLabel.USER_INPUT,
        )
        self.logger.debug(f"Initialised with task: {task}")

    async def act(self, observation: Observation) -> Action:
        self.agent.receive_user_message(
            image=observation.state.image,
            text=observation.state.text,
            label=MessageLabel.SCREENSHOT,
            is_base64=True,
        )

        message = await self.agent.generate_output(use_tool=True)

        self.logger.debug(f"Assistant message generated: {message}")

        # check tool calls for return_value
        if any(tool_call.function["name"] == "return_value" for tool_call in message.tool_calls):
            self.complete = True
            arguments = json.loads(message.tool_calls[0].function["arguments"])
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            return_value = arguments["value"]
            return Action(tool_calls=[], text=return_value)

        text_content = message.content[0].text

        observation_match = re.search(r"<observation>(.*?)</observation>", text_content, re.DOTALL)
        observation_content = observation_match.group(1).strip() if observation_match else ""

        self.logger.info("🌐 [bold blue]Observation:[/]")
        await self.logger.stream_message(observation_content)

        # Extract text between thinking tags if present
        thinking_match = re.search(r"<thinking>(.*?)</thinking>", text_content, re.DOTALL)
        thinking_content = thinking_match.group(1).strip() if thinking_match else text_content

        self.logger.info("🧠 [bold purple]Thinking:[/]")
        await self.logger.stream_message(thinking_content)

        return Action(tool_calls=message.tool_calls, text=text_content)

    async def is_complete(self, observation: Observation) -> bool:
        env_terminated = observation.terminated
        return self.complete or env_terminated
