import math
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field, field_validator


class Point(BaseModel):
    x: int
    y: int

    def __iter__(self):
        return iter((self.x, self.y))

    def __getitem__(self, index) -> int:
        return (self.x, self.y)[index]

    def __tuple__(self) -> tuple[int, int]:
        return (self.x, self.y)

    def __repr__(self) -> str:
        return f"Point(x={self.x}, y={self.y})"


class BoundingBox(BaseModel):
    label: str = Field(..., description="The label that's given for this bounding box")
    left: int = Field(..., description="Left coordinate of the bounding box")
    right: int = Field(..., description="Right coordinate of the bounding box")
    top: int = Field(..., description="Top coordinate of the bounding box")
    bottom: int = Field(..., description="Bottom coordinate of the bounding box")

    @field_validator("left", "top", mode="before")
    @classmethod
    def round_down(cls, v):
        return math.floor(float(v))

    @field_validator("right", "bottom", mode="before")
    @classmethod
    def round_up(cls, v):
        return math.ceil(float(v))


class POI(BaseModel):
    info: dict[str, Any]
    element_centroid: Point
    bounding_box: BoundingBox


def calculate_dash_points(start, end, dash_length, gap_length):
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    dist = np.sqrt(dx * dx + dy * dy)

    if dist == 0:
        return []

    unit_x = dx / dist
    unit_y = dy / dist

    dash_points = []
    current_dist = 0
    while current_dist < dist:
        dash_end = min(current_dist + dash_length, dist)
        dash_points.extend(
            [
                (int(x1 + unit_x * current_dist), int(y1 + unit_y * current_dist)),
                (int(x1 + unit_x * dash_end), int(y1 + unit_y * dash_end)),
            ],
        )
        current_dist += dash_length + gap_length

    return dash_points


def draw_dashed_rectangle(
    img,
    bbox: BoundingBox,
    color,
    thickness=1,
    dash_length=10,
    gap_length=5,
):
    # Calculate dash points for all sides
    top_points = calculate_dash_points(
        (bbox.left + 25, bbox.top + 25),
        (bbox.right + 25, bbox.top + 25),
        dash_length,
        gap_length,
    )
    right_points = calculate_dash_points(
        (bbox.right + 25, bbox.top + 25),
        (bbox.right + 25, bbox.bottom + 25),
        dash_length,
        gap_length,
    )
    bottom_points = calculate_dash_points(
        (bbox.right + 25, bbox.bottom + 25),
        (bbox.left + 25, bbox.bottom + 25),
        dash_length,
        gap_length,
    )
    left_points = calculate_dash_points(
        (bbox.left + 25, bbox.bottom + 25),
        (bbox.left + 25, bbox.top + 25),
        dash_length,
        gap_length,
    )

    # Combine all points
    all_points = top_points + right_points + bottom_points + left_points

    # Draw all lines at once
    if all_points:
        all_points = np.array(all_points).reshape((-1, 2, 2))
        cv2.polylines(img, all_points, False, color, thickness)


# @time_it(name='Annotate bounding box')
def annotate_bounding_box(image: bytes, bbox: BoundingBox) -> None:
    # Draw dashed bounding box
    draw_dashed_rectangle(
        image,
        bbox,
        color=(0, 0, 255),
        thickness=1,
        dash_length=10,
        gap_length=5,
    )

    # Prepare label
    font_scale = 0.4 * 4  # Increased by 4x for the larger patch
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 3  # Increased thickness for the larger patch

    # Get text size for the larger patch
    (label_width, label_height), _ = cv2.getTextSize(
        bbox.label,
        font,
        font_scale,
        thickness,
    )

    # Create a larger patch (4x)
    large_label_patch = np.zeros(
        (label_height + 20, label_width + 20, 4),
        dtype=np.uint8,
    )
    large_label_patch[:, :, 0:3] = (0, 0, 255)  # BGR color format: Red background
    large_label_patch[:, :, 3] = 128  # Alpha channel: 50% opacity (128/255 = 0.5)

    # Draw text on the larger patch
    cv2.putText(
        large_label_patch,
        bbox.label,
        (8, label_height + 8),  # Adjusted position for the larger patch
        font,
        font_scale,
        (255, 255, 255, 128),  # White text, 50% opaque (128/255 = 0.5)
        thickness,
    )

    # Scale down the patch to improve anti-aliasing
    label_patch = cv2.resize(
        large_label_patch,
        (label_width // 4 + 5, label_height // 4 + 5),
        interpolation=cv2.INTER_AREA,
    )

    # Calculate position for top-left alignment
    offset = 2  # Small offset to prevent touching the bounding box edge
    x = min(image.shape[1], max(0, int(bbox.left + 25) - offset))
    y = min(image.shape[0], max(0, int(bbox.top + 25) - label_patch.shape[0] - offset))

    # Ensure we're not out of bounds
    x_end = min(image.shape[1], x + label_patch.shape[1])
    y_end = min(image.shape[0], y + label_patch.shape[0])
    label_patch = label_patch[: (y_end - y), : (x_end - x)]

    # Create a mask for the label patch
    alpha_mask = label_patch[:, :, 3] / 255.0
    alpha_mask = np.repeat(alpha_mask[:, :, np.newaxis], 3, axis=2)

    # Blend the label patch with the image
    image_section = image[y:y_end, x:x_end]
    blended = (1 - alpha_mask) * image_section + alpha_mask * label_patch[:, :, 0:3]
    image[y:y_end, x:x_end] = blended.astype(np.uint8)


def annotate_bounding_boxes(image: bytes, bounding_boxes: list[BoundingBox]) -> bytes:
    # Read the image
    nparr = np.frombuffer(image, np.uint8)
    # Decode the image
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    padded_img = cv2.copyMakeBorder(
        img,
        top=25,  # Value chosen based on label size
        bottom=25,  # Value chosen based on label size
        left=25,  # Value chosen based on label size
        right=25,  # Value chosen based on label size
        borderType=cv2.BORDER_CONSTANT,
        value=(255, 255, 255),
    )
    for bounding_box in bounding_boxes:
        # Annotate the image in place with the bounding box and the bounding box label
        annotate_bounding_box(padded_img, bounding_box)
    _, buffer = cv2.imencode(".jpeg", padded_img)
    return buffer.tobytes()
