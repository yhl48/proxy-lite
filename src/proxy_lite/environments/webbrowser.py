import base64
import json
from functools import cached_property
from typing import Any, Literal, Optional, Self

from proxy_lite.browser.browser import BrowserSession
from proxy_lite.environments.environment_base import (
    Action,
    BaseEnvironment,
    BaseEnvironmentConfig,
    Environments,
    Observation,
    State,
    ToolCall,
)
from proxy_lite.tools import BrowserTool, ReturnValueTool, StructuredDataTool, Tool, ToolExecutionResponse


@Environments.register_environment_config("webbrowser")
class WebBrowserEnvironmentConfig(BaseEnvironmentConfig):
    name: Literal["webbrowser"] = "webbrowser"
    homepage: str = "https://google.com"
    annotate_image: bool = True
    screenshot_delay: float = 1.0  # seconds
    include_html: bool = True
    include_poi_text: bool = True
    record_pois: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720
    browserbase_timeout: int = 7200
    headless: bool = True
    keep_original_image: bool = False
    no_pois_in_image: bool = False


@Environments.register_environment("webbrowser")
class WebBrowserEnvironment(BaseEnvironment):
    config: WebBrowserEnvironmentConfig
    browser: Optional[BrowserSession] = None
    cancelled_last_action: bool = False

    class Config:
        arbitrary_types_allowed = True

    async def __aenter__(self) -> Self:
        # Initialize the BrowserSession
        self.browser = self.browser_session(
            viewport_width=self.config.viewport_width,
            viewport_height=self.config.viewport_height,
            headless=self.config.headless,
        )
        await self.browser.__aenter__()
        # Initialize other resources if necessary
        if self.cookies:
            await self.browser.context.add_cookies(self.cookies)
        self.logger.info("🌐 [bold blue]Browser session started.[/]")
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        # Clean up the BrowserSession
        await self.browser.__aexit__(exc_type, exc_value, traceback)

    @property
    def info_for_user(self) -> str:
        return "This is a web browser environment. You can navigate the web, search the web, and perform actions on the web."  # noqa: E501

    @cached_property
    def tools(self) -> list[Tool]:
        tools_list = [
            BrowserTool(session=self.browser),
            ReturnValueTool(),
            StructuredDataTool(session=self.browser),
        ]
        print(f"DEBUG: Registered tools: {[tool.__class__.__name__ for tool in tools_list]}")
        return tools_list

    @cached_property
    def browser_session(self) -> type[BrowserSession]:
        return BrowserSession

    @property
    def cookies(self) -> list[dict]:
        return []

    async def initialise(self) -> Observation:
        await self.browser.goto(self.config.homepage)
        original_img, annotated_img = await self.browser.screenshot(
            delay=self.config.screenshot_delay,
        )
        if self.config.no_pois_in_image:
            base64_image = base64.b64encode(original_img).decode("utf-8")
        else:
            base64_image = base64.b64encode(annotated_img).decode("utf-8")

        html_content = await self.browser.current_page.content() if self.config.include_html else None

        info = {"url": self.browser.current_url}
        if self.config.record_pois:
            info["pois"] = self.browser.pois
        if self.config.keep_original_image:
            info["original_image"] = base64.b64encode(original_img).decode("utf-8")

        return Observation(
            state=State(
                text=f"URL: {self.browser.current_url}"
                + (f"\n{self.browser.poi_text}" if self.config.include_poi_text else ""),
                image=base64_image,
                html=html_content,
            ),
            terminated=False,
            reward=None,
            info=info,
        )

    async def should_perform_action(self) -> bool:
        # if cancelled last action, run the action without updating POIs
        if self.cancelled_last_action:
            self.cancelled_last_action = False
            return True

        # check for page changes
        old_points = [tuple(point) for point in self.browser.poi_centroids]
        await self.browser.update_poi()
        new_points = [tuple(point) for point in self.browser.poi_centroids]
        page_changed_mid_action = old_points != new_points

        # record if the last action was cancelled
        if page_changed_mid_action:
            self.cancelled_last_action = True
            return False
        return True

    async def execute_action(self, action: Action) -> Observation:
        responses = []
        cancelled_tools_flag = False
        
        if await self.should_perform_action():
            # Check if tables are present in the full DOM
            table_elements = await self.browser.current_page.evaluate("""
                () => {
                    const tables = document.querySelectorAll('table');
                    const tableInfo = [];
                    tables.forEach((table, index) => {
                        const rect = table.getBoundingClientRect();
                        tableInfo.push({
                            index: index,
                            tag: 'table',
                            rect: {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            }
                        });
                    });
                    return tableInfo;
                }
            """)
            
            if table_elements:
                # Check if any tool call is extract_table
                extract_table_called = False
                if action.tool_calls:
                    for tool_call in action.tool_calls:
                        if tool_call.function["name"] == "extract_table":
                            extract_table_called = True
                            break
                
                # If tables exist but extract_table wasn't called, FORCE the use of extract_table
                if not extract_table_called:
                    self.logger.warning("🔴 Tables detected but extract_table tool not used - forcing table extraction!")
                    
                    # Use the first table found in the DOM
                    first_table = table_elements[0]
                    
                    # Create tool call dictionary
                    tool_call_dict = {
                        "id": "forced_extract_table",
                        "type": "function",
                        "function": {
                            "name": "extract_table",
                            "arguments": json.dumps({  # Convert arguments to JSON string
                                "mark_id": first_table["index"],
                                "format": "json"
                            })
                        }
                    }
                    
                    # Create proper tool call object
                    tool_call = ToolCall(**tool_call_dict)
                    
                    # Add the extract_table call to the beginning of the tool calls
                    if not action.tool_calls:
                        action.tool_calls = [tool_call]
                    else:
                        action.tool_calls.insert(0, tool_call)
                    
                    self.logger.info(f"🔄 Forcing extract_table tool call for table at index {first_table['index']}")

            # Execute all tool calls in order
            for tool_call in action.tool_calls:
                try:
                    tool_response = await self.execute_tool(tool_call)
                    tool_response.id = tool_call.id
                    responses.append(tool_response)
                    self.logger.info(f"✅ Tool {tool_call.function['name']} executed successfully")
                    
                    # Debug extract_table output
                    if tool_call.function["name"] == "extract_table":
                        self.logger.info(f"📊 Extract table output: {tool_response.content[:500]}...")  # Show first 500 chars
                        
                        try:
                            # Try to parse as JSON to show structured data
                            table_data = json.loads(tool_response.content)
                            self.logger.info(f"📋 Parsed table data (first 2 rows): {table_data[:2]}")
                        except json.JSONDecodeError:
                            # If not JSON, just show as is
                            self.logger.info("Table data is not in JSON format")
                            
                except Exception as e:
                    self.logger.warning("🌐 An error occurred taking action: %s", str(e), exc_info=False)
                    tool_response = ToolExecutionResponse(content=str(e), id=tool_call.id)
                    responses.append(tool_response)
        else:
            self.logger.warning("🌐 Page changed since last observation, cancelling action.")
            self.cancelled_last_action = True
            for tool_call in action.tool_calls:
                tool_response = ToolExecutionResponse(
                    content="The page changed before the action could be executed, instead of being ran it was cancelled.",  # noqa: E501
                    id=tool_call.id,
                )
                responses.append(tool_response)
                cancelled_tools_flag = True
        original_img, annotated_img = await self.browser.screenshot(
            delay=self.config.screenshot_delay,
        )

        base64_image = base64.b64encode(annotated_img).decode("utf-8")

        info = {"url": self.browser.current_url, "cancelled_tools": cancelled_tools_flag}
        if self.config.record_pois:
            info["pois"] = self.browser.pois
        if self.config.keep_original_image:
            info["original_image"] = base64.b64encode(original_img).decode("utf-8")

        html_content = await self.browser.current_page.content() if self.config.include_html else None
        return Observation(
            state=State(
                text=f"URL: {self.browser.current_url}"
                + (f"\n{self.browser.poi_text}" if self.config.include_poi_text else ""),
                image=base64_image,
                html=html_content,
                tool_responses=responses,
            ),
            terminated=False,
            reward=None,
            info=info,
        )

    async def observe(self) -> Observation:
        return await self.browser.observe()

    async def evaluate(self, **kwargs: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def get_info(self) -> dict[str, Any]:
        info = {}
        return info
