import asyncio
import logging
import platform
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Literal, Optional, Self

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright_stealth import StealthConfig, stealth_async
from pydantic import Field
from tenacity import before_sleep_log, retry, stop_after_delay, wait_exponential

from proxy_lite.browser.bounding_boxes import POI, BoundingBox, Point, annotate_bounding_boxes
from proxy_lite.logger import logger

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
    """Return a text representation of all elements on the page."""
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

    # sub-out line breaks so elements are easier to distinguish
    attributes = re.sub(r"\r\n|\r|\n", "⏎", attributes)
    text = re.sub(r"\r\n|\r|\n", "⏎", text)

    if tag in SELF_CONTAINED_TAGS:
        if text:
            logger.warning(
                f"Got self-contained element '{tag}' which contained text '{text}'.",
            )
        else:
            return f"- [{mark_id}] <{tag}{attributes}/>"
    return f"- [{mark_id}] <{tag}{attributes}>{text}</{tag}>"


class BrowserSession:
    def __init__(
        self,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        headless: bool = True,
    ):
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.headless = headless
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self._exit_stack: AsyncExitStack | None = None

        self.poi_elements: list = Field(default_factory=list)
        self.poi_centroids: list[Point] = Field(default_factory=list)
        self.bounding_boxes: list[BoundingBox] = Field(default_factory=list)
        self.pois: list[POI] = Field(default_factory=list)

    async def __aenter__(self) -> Self:
        self._exit_stack = AsyncExitStack()
        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
        )
        await self.context.new_page()
        self.context.set_default_timeout(60_000)
        self.current_page.set_default_timeout(60_000)
        await stealth_async(self.current_page, StealthConfig(navigator_user_agent=False))
        await self.context.add_init_script(
            path=Path(__file__).with_name("add_custom_select.js"),
        )
        await self.context.add_init_script(
            path=Path(__file__).with_name("find_pois.js"),
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self._exit_stack:
            await self._exit_stack.aclose()

    @property
    def current_page(self) -> Optional[Page]:
        if self.context.pages:
            return self.context.pages[-1]
        return None

    @property
    def current_url(self) -> Optional[str]:
        if self.current_page:
            return self.current_page.url
        return None

    # re-run for cases of mid-run redirects
    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_delay(5),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.ERROR),
    )
    async def process_iframe(self, iframe) -> Optional[tuple[dict, dict]]:
        try:
            # Check iframe visibility and size
            bounding_box = await iframe.bounding_box()
            if not bounding_box:
                return None  # Skip if iframe is not visible

            width, height = bounding_box["width"], bounding_box["height"]
            if width < 50 or height < 50:
                return None

            frame = await iframe.content_frame()
            if not frame:
                return None

            poi = await frame.evaluate(
                """() => {
                    overwriteDefaultSelectConvergence();
                    return findPOIsConvergence();
                }""",
            )
            if not poi:
                return None

            iframe_offset = {"x": round(bounding_box["x"]), "y": round(bounding_box["y"])}
            return poi, iframe_offset
        except Exception as e:
            logger.error(f"Error processing iframe: {e}")
            return None

    # re-run for cases of mid-run redirects
    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_delay(5),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.ERROR),
    )
    async def update_poi(self) -> None:
        try:
            await self.current_page.wait_for_load_state(timeout=60000)
        except PlaywrightTimeoutError:
            logger.error(f"Timeout waiting for website load state: {self.current_url}")
        await self.current_page.wait_for_selector("body", timeout=60000, state="visible")
        # Run the bounding box javascript code to highlight the points of interest on the page
        page_info = await self.current_page.evaluate(
            """() => {
                overwriteDefaultSelectConvergence();
                return findPOIsConvergence();
            }""",
        )
        # Get the points of interest on the page
        self.poi_elements = page_info["element_descriptions"]
        element_centroids = page_info["element_centroids"]
        try:
            # Select all iframes on the page
            iframes = await self.current_page.query_selector_all("iframe")

            max_iframes = 10

            # Define an asynchronous function to process and filter each iframe

            tasks = [asyncio.create_task(self.process_iframe(iframe)) for iframe in iframes[:max_iframes]]

            results = await asyncio.gather(*tasks)

            filtered_results = [result for result in results if result is not None]

            iframes_pois = []
            iframe_offsets = []

            for poi, offset in filtered_results:
                iframes_pois.append(poi)
                iframe_offsets.append(offset)

            # Combine the points of interest from the iframes with the main page and adjust the centroids
            for index, iframe_poi in enumerate(iframes_pois):
                self.poi_elements.extend(iframe_poi["element_descriptions"])
                for centroid in iframe_poi["element_centroids"]:
                    centroid["x"] += iframe_offsets[index]["x"]
                    centroid["y"] += iframe_offsets[index]["y"]
                    centroid["left"] += iframe_offsets[index]["x"]
                    centroid["top"] += iframe_offsets[index]["y"]
                    centroid["right"] += iframe_offsets[index]["x"]
                    centroid["bottom"] += iframe_offsets[index]["y"]
                element_centroids.extend(iframe_poi["element_centroids"])

        except Exception as e:
            logger.error(f"Error in finding iframes: {e}")

        # Get the centroids of the points of interest
        self.poi_centroids = [Point(x=xy["x"], y=xy["y"]) for xy in element_centroids]
        self.bounding_boxes = [BoundingBox(**xy, label=str(i)) for i, xy in enumerate(element_centroids)]
        self.pois = [
            POI(info=info, element_centroid=centroid, bounding_box=bbox)
            for info, centroid, bbox in zip(
                self.poi_elements,
                self.poi_centroids,
                self.bounding_boxes,
                strict=False,
            )
        ]

    @property
    def poi_text(self) -> str:
        # Get all points of interest on the page as text
        texts = [element_as_text(mark_id=i, **element) for i, element in enumerate(self.poi_elements)]
        # Return formatted text of points of interest on page
        return "\n".join([txt for txt in texts if txt])

    async def screenshot(
        self,
        delay: float = 0.0,
        quality: int = 70,
        type: str = "jpeg",
        scale: str = "css",
    ) -> tuple[bytes, bytes]:
        if delay > 0.0:
            await asyncio.sleep(delay)
        await self.update_poi()
        old_poi_positions = [tuple(point) for point in self.poi_centroids]
        img = await self.current_page.screenshot(type=type, quality=quality, scale=scale)
        annotated_img = annotate_bounding_boxes(image=img, bounding_boxes=self.bounding_boxes)
        # check page has not changed since the screenshot was taken
        await self.update_poi()
        new_poi_positions = [tuple(point) for point in self.poi_centroids]
        if new_poi_positions != old_poi_positions:
            # if it has changed, take another
            img = await self.current_page.screenshot(type=type, quality=quality, scale=scale)
            await self.update_poi()
            annotated_img = annotate_bounding_boxes(image=img, bounding_boxes=self.bounding_boxes)
        return img, annotated_img

    async def goto(self, url: str) -> None:
        await self.current_page.goto(url, wait_until="domcontentloaded")

    async def reload(self) -> None:
        await self.current_page.reload(wait_until="domcontentloaded")

    async def click_tab(self, mark_id: int) -> None:
        point: Point = self.poi_centroids[mark_id]
        await self.hover(point)
        await self.current_page.mouse.click(*point, button="middle")

    async def click(self, mark_id: int) -> None:
        point: Point = self.poi_centroids[mark_id]
        await self.hover(point)
        await self.current_page.mouse.click(*point)

    async def enter_text(self, mark_id: int, text: str, submit: bool = False) -> None:
        await self.clear_text_field(mark_id)
        await self.click(mark_id)
        await self.current_page.keyboard.type(text)

        if submit:
            await self.current_page.keyboard.press("Enter")

    async def scroll(
        self,
        direction: Literal["up", "down", "left", "right"],
        mark_id: Optional[int] = None,
    ) -> None:
        if mark_id is None:
            point = Point(x=-1, y=-1)
            max_scroll_x = self.viewport_width
            max_scroll_y = self.viewport_height
        else:
            point: Point = self.poi_centroids[mark_id]
            bbox: BoundingBox = self.bounding_boxes[mark_id]
            max_scroll_x = bbox.right - bbox.left
            max_scroll_y = bbox.bottom - bbox.top

        await self.hover(point=point)
        scroll_x = int(max_scroll_x * 0.8)
        scroll_y = int(max_scroll_y * 0.8)
        is_vertical = direction in ("up", "down")
        reverse_scroll = direction in ("up", "left")
        await self.current_page.mouse.wheel(
            scroll_x * (-1 if reverse_scroll else 1) * (not is_vertical),
            scroll_y * (-1 if reverse_scroll else 1) * is_vertical,
        )

    async def go_back(self) -> None:
        # If there is no tab open then return
        if not self.current_page:
            return

        await self.current_page.go_back(wait_until="domcontentloaded")
        if self.current_page.url == "about:blank":
            if not len(self.context.pages) > 1:
                await self.current_page.go_forward(wait_until="domcontentloaded")
                raise Exception("There is no previous page to go back to.")
            await self.current_page.close()

    async def hover(self, point: Point) -> None:
        await self.current_page.mouse.move(*point)

    async def focus(self, point: Point) -> None:
        # Focus on the element on the page at point (x, y)
        await self.current_page.evaluate(
            """
            ([x, y]) => {
                const element = document.elementFromPoint(x, y);
                if (element && element.focus) {
                    element.focus();
                }
            }""",
            tuple(point),
        )

    async def get_text(self, mark_id: int) -> str:
        return await self.current_page.evaluate(
            """
            (mark_id) => {
                const element = marked_elements_convergence[mark_id];
                if (element && (element.value !== undefined || element.textContent !== undefined)) {
                    return element.value || element.textContent;
                }
                return '';
            }
            """,
            (mark_id,),
        )

    async def clear_text_field(self, mark_id: int) -> None:
        existing_text = await self.get_text(mark_id)
        if existing_text.strip():
            # Clear existing text only if it exists
            await self.click(mark_id)
            if platform.system() == "Darwin":  # selecting all text is OS-specific
                await self.click(mark_id)
                await self.current_page.keyboard.press("Meta+a")
                await self.current_page.keyboard.press("Backspace")
            else:
                await self.current_page.keyboard.press("Control+Home")
                await self.current_page.keyboard.press("Control+Shift+End")
            await self.current_page.keyboard.press("Backspace")


if __name__ == "__main__":

    async def dummy_test():
        async with BrowserSession(headless=False) as s:
            page = await s.context.new_page()
            await page.goto("http://google.co.uk")
            await asyncio.sleep(5)
            await page.screenshot(path="example.png")
            await s.update_poi()
            _, annotated_image = await s.screenshot()
            with open("output.png", "wb") as f:
                f.write(annotated_image)

    asyncio.run(dummy_test())
