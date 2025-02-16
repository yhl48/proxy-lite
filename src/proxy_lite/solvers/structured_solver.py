# ruff: noqa: E501

from functools import cached_property
from typing import Literal, Optional

from pydantic import BaseModel, Field

from proxy_lite.agents import AgentConfigTypes, Agents, BaseAgent
from proxy_lite.environments.environment_base import Action, Observation
from proxy_lite.history import (
    MessageHistory,
    MessageLabel,
    SystemMessage,
)
from proxy_lite.tools import Tool

from .solver_base import BaseSolver, BaseSolverConfig, Solvers

WEB_TOOL_TURN = """The browser action has been attempted. Please double check if the action was successful."""
PLAN_USER_PROMPT = "First create a high-level plan to help solve the task on the web."
ACTION_PROMPT = """Now take the most-promising next action in the browser.

Only refer to the latest web elements from the latest screenshot.

Using mark ids from older turns will lead to errors as they are no longer valid.

Only interact with elements visible on the current webpage. Do not make up numbers or elements."""
REASONING_PROMPT = """You will now follow these steps.

1. **Make observations about the state of the webpage**:
   - Consider the previous screenshot, your attempted previous action, and the current screenshot.
   - Describe any changes you observe, and try to determine if the previous action succeeded.
   - For example, if a form is being filled out, check whether the correct information is now displayed.

2. **Write down any helpful facts you have gathered**:
   - Describe any useful information on the webpage that might be helpful for completing the task.
   - For example, if you are viewing a document, you may wish to note down any information you want to refer back to later.

3. **Reason about the system's status**:
   - Have you fully completed the task?

4. **Select one of the following statuses**:
   - "complete": if the task has been completed.
   - "continue": if you are ready to continue without information or help.

5. **Reason through next steps**:
    - If the status is "continue", write down your reasoning for the next action you will take. You can only take one action at a time.
    - If the status is not "continue", return an empty string.

6. **Write a message to the user**:
   - If the status is "complete", write a message to the user. If they asked a question in the task, make sure the answer is here. Otherwise, just provide other useful information about how the task went or if there was a problem in completing it.
   - If the status is not "complete", set this to an empty string.

Tips:
- If you have already provided a response, don't provide it again.
- If you notice you are repeating previous actions, you're likely stuck. Try something different."""


class Reflection(BaseModel):
    observation: str = Field(
        ...,
        description="Observation of the current browser state, including an assessment on the success of the last action (previous actions and observations are often wrong).",
    )
    fact_updates: list[str] = Field(
        "",
        description="List of new information relevant to the task that was found on the page, ignore input fields holding content you wrote.",
    )
    status_reasoning: str = Field(
        ...,
        description="Reasoning about the current state of the task.",
    )
    status: Literal["complete", "continue"] = Field(
        ...,
        description="Choose a system status based on your status reasoning.",
    )
    next_step_reasoning: str = Field(
        ...,
        description='If status is "continue", reason through the next action you will be taking (do not repeat actions over and over). Otherwise set to "".',
    )
    ending_message: str = Field(
        ...,
        description="If status is 'complete', write a message to the user. If they asked a question in the task, make sure the answer is here. Otherwise, just provide other useful information about how the task went or if there was a problem in completing it. If status is 'continue', set to ''.",
    )


@Solvers.register_solver_config("structured")
class StructuredSolverConfig(BaseSolverConfig):
    name: Literal["structured"] = "structured"
    agent: AgentConfigTypes
    start_with_plan: bool = True


@Solvers.register_solver("structured")
class StructuredSolver(BaseSolver):
    task: Optional[str] = None
    complete: bool = False

    @cached_property
    def tools(self) -> list[Tool]:
        return self.env_tools

    @cached_property
    def local_tools(self) -> list[Tool]:
        if self.sandbox:
            return self.sandbox.tools
        return []

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
        self.agent.receive_user_message(
            text=env_info,
            label=MessageLabel.USER_INPUT,
        )
        self.task = task
        self.agent.receive_user_message(
            text=f"Task: {task}",
            label=MessageLabel.USER_INPUT,
        )
        if self.config.start_with_plan:
            self.agent.receive_user_message(text=PLAN_USER_PROMPT, label=MessageLabel.PLAN)
            await self.agent.generate_output(use_tool=False)

    async def act(self, observation: Observation) -> Action:
        if observation.state.tool_responses:
            for tool_response in observation.state.tool_responses:
                await self.agent.receive_tool_message(
                    text=f"{WEB_TOOL_TURN}\n{tool_response.content}",
                    tool_id=tool_response.id,
                    label=MessageLabel.TOOL_RESULT_INDUCTION,
                )

        self.agent.receive_user_message(
            image=observation.state.image,
            text=observation.state.text,
            label=MessageLabel.SCREENSHOT,
            is_base64=True,
        )

        self.agent.receive_user_message(
            text=REASONING_PROMPT,
            label=MessageLabel.REASONING_INDUCTION,
        )

        message = await self.agent.generate_structured_output(model=Reflection)
        self.logger.info(f"🌐 [bold blue]Observation:[/] {message.observation}")

        if message.status == "complete":
            self.complete = True
            return Action(tool_calls=[], text=message.ending_message)

        next_step = message.next_step_reasoning

        self.agent.receive_user_message(
            text=ACTION_PROMPT,
            label=MessageLabel.ACTION,
            is_base64=True,
        )
        message = await self.agent.generate_output(use_tool=True)

        return Action(tool_calls=message.tool_calls, text=next_step)

    async def is_complete(self, observation: Observation) -> bool:
        env_terminated = observation.terminated
        return self.complete or env_terminated
