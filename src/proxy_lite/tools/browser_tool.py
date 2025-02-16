import asyncio
from contextlib import AsyncExitStack
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from proxy_lite.browser.browser import BrowserSession
from proxy_lite.logger import logger

from .tool_base import Tool, ToolExecutionResponse, attach_param_schema

SELF_CONTAINED_TAGS = [
    # many of these are non-interactive but keeping them anyway
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
]


def element_as_text(
    mark_id: int,
    tag: Optional[str] = None,
    text: Optional[str] = None,
    **raw_attributes,
) -> str:
    """Return a text representation of all elements on the page"""
    attributes = []
    for k, v in raw_attributes.items():
        if v is None:
            continue
        if isinstance(v, bool):
            if v:
                attributes.append(k)
            # we ignore False bool attributes
        else:
            v = str(v)
            if len(v) > 2500:
                v = v[: 2500 - 1] + "…"
            attributes.append(f'{k}="{v}"')
    attributes = " ".join(attributes)
    attributes = (" " + attributes).rstrip()
    tag = tag.lower()
    if text is None:
        text = ""
    if len(text) > 2500:
        text = text[: 2500 - 1] + "…"
    if tag in SELF_CONTAINED_TAGS:
        if text:
            logger.warning(
                f"Got self-contained element '{tag}' which contained text '{text}'.",
            )
        else:
            return f"<{tag} id={mark_id}{attributes}/>"
    return f"<{tag} id={mark_id}{attributes}>{text}</{tag}>"


class GotoParams(BaseModel):
    url: str = Field(..., description="The web address to visit. Must be a valid URL.")


class GoogleSearchParams(BaseModel):
    query_plan: str = Field(
        ...,
        description="Plan out the query you will make. Re-write queries in a way that will yield the best results.",
    )
    query: str = Field(..., description="The Google search to perform.")


class ClickParams(BaseModel):
    mark_id: int = Field(..., description="Element Mark ID.")


class TypeEntry(BaseModel):
    mark_id: int = Field(..., description="Element Mark ID.")
    content: str = Field(..., description="The text to type into the element.")


class TypeParams(BaseModel):
    entries: List[TypeEntry] = Field(
        ...,
        description="A list of elements and contents to type.",
    )
    submit: bool = Field(
        ...,
        description='Whether to press the "Enter" key after typing in the last entry.',
    )


class ScrollParams(BaseModel):
    direction: Literal["up", "down", "left", "right"] = Field(
        ...,
        description='Direction to scroll. Must be one of "up", "down", "left" or "right".',
    )
    mark_id: int = Field(
        ...,
        description="What to scroll. Use -1 to scroll the whole page otherwise give the mark ID of an element that is `scrollable`.",  # noqa: E501
    )


class BackParams(BaseModel):
    pass


class WaitParams(BaseModel):
    pass


class ReloadParams(BaseModel):
    pass


class DoNothingParams(BaseModel):
    pass


class BrowserTool(Tool):
    def __init__(self, session: BrowserSession) -> None:
        super().__init__()
        self.browser = session

    async def __aenter__(self):
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.enter_async_context(self.browser)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._exit_stack.aclose()

    @property
    def poi_text(self) -> str:
        # Get all points of interest on the page as text
        texts = [element_as_text(mark_id=i, **element) for i, element in enumerate(self.browser.poi_elements)]
        # Return formatted text of points of interest on page
        return "\n".join([txt for txt in texts if txt])

    @attach_param_schema(GotoParams)
    async def goto(self, url: str) -> ToolExecutionResponse:
        """Go directly to a specific web url. Specify the exact URL."""
        await self.browser.goto(url)
        return ToolExecutionResponse()

    @attach_param_schema(GoogleSearchParams)
    async def google_search(self, query_plan: str, query: str) -> ToolExecutionResponse:
        """Perform a generic web search using Google.
        Results may not be relevant. If you see poor results, you can try another query.
        """
        url = f"https://www.google.com/search?q={query}"
        await self.browser.goto(url)
        return ToolExecutionResponse()

    @attach_param_schema(ClickParams)
    async def click(self, mark_id: int) -> ToolExecutionResponse:
        """Click on an element of the page."""
        await self.browser.click(mark_id=mark_id)
        return ToolExecutionResponse()

    @attach_param_schema(TypeParams)
    async def type(self, entries: List[dict], submit: bool) -> ToolExecutionResponse:
        """Type text.
        You can type into one or more elements.
        Note that the text inside an element is cleared before typing.
        """
        for i, entry_dict in enumerate(entries):
            entry = TypeEntry(**entry_dict)
            last_entry = i == len(entries) - 1
            old_poi_positions = [tuple(point) for point in self.browser.poi_centroids]
            await self.browser.enter_text(
                mark_id=entry.mark_id,
                text=entry.content,
                submit=submit and last_entry,
            )
            await self.browser.update_poi()
            new_poi_positions = [tuple(point) for point in self.browser.poi_centroids]
            if not last_entry and old_poi_positions != new_poi_positions:
                logger.error(
                    "POI positions changed mid-typing, cancelling future type entries.",
                )
                break
        return ToolExecutionResponse()

    @attach_param_schema(ScrollParams)
    async def scroll(self, direction: str, mark_id: int) -> ToolExecutionResponse:
        """Scroll the page (or a scrollable element) up, down, left or right."""
        if mark_id == -1:
            mark_id = None
        await self.browser.scroll(direction=direction, mark_id=mark_id)
        return ToolExecutionResponse()

    @attach_param_schema(BackParams)
    async def back(self) -> ToolExecutionResponse:
        """Go back to the previous page."""
        await self.browser.go_back()
        return ToolExecutionResponse()

    @attach_param_schema(WaitParams)
    async def wait(self) -> ToolExecutionResponse:
        """Wait three seconds. Useful when the page appears to still be loading, or if there are any unfinished webpage processes."""  # noqa: E501
        await asyncio.sleep(3)
        return ToolExecutionResponse()

    @attach_param_schema(ReloadParams)
    async def reload(self) -> ToolExecutionResponse:
        """Reload the current page. Useful when the page seems unresponsive, broken, outdated, or if you want to reset the page to its initial state."""  # noqa: E501
        await self.browser.reload()
        return ToolExecutionResponse()

    @attach_param_schema(DoNothingParams)
    async def do_nothing_tool(self) -> ToolExecutionResponse:
        """Do nothing. Use this if you have no need for the browser at this time."""
        return ToolExecutionResponse()
