import base64
import re
import textwrap
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from proxy_lite.environments.environment_base import Action, Observation
from proxy_lite.recorder import Run


def create_run_gif(
    run: Run, output_path: str, white_panel_width: int = 300, duration: int = 1500, resize_factor: int = 4
) -> None:
    """
    Generate a gif from the Run object's history.

    For each Observation record, the observation image is decoded from its base64
    encoded string. If the next record is an Action, its text is drawn onto a
    white panel. The observation image and the white panel are then concatenated
    horizontally to produce a frame.

    Parameters:
        run (Run): A Run object with its history containing Observation and Action records.
        output_path (str): The path where the GIF will be saved.
        white_panel_width (int): The width of the white panel for displaying text.
                                 Default increased to 400 for larger images.
        duration (int): Duration between frames in milliseconds.
                        Increased here to slow the FPS (default is 1000ms).
        resize_factor (int): The factor to resize the image down by.
    """
    frames = []
    history = run.history
    i = 0
    while i < len(history):
        if isinstance(history[i], Observation):
            observation = history[i]
            image_data = observation.state.image
            if not image_data:
                i += 1
                continue
            # Decode the base64 image
            image_bytes = base64.b64decode(image_data)
            obs_img = Image.open(BytesIO(image_bytes)).convert("RGB")

            # scale the image down
            obs_img = obs_img.resize((obs_img.width // resize_factor, obs_img.height // resize_factor))

            # Check if the next record is an Action and extract its text if available
            action_text = ""
            if i + 1 < len(history) and isinstance(history[i + 1], Action):
                action = history[i + 1]
                if action.text:
                    action_text = action.text

            # extract observation and thinking from tags in the action text
            observation_match = re.search(r"<observation>(.*?)</observation>", action_text, re.DOTALL)
            observation_content = observation_match.group(1).strip() if observation_match else None

            # Extract text between thinking tags if present
            thinking_match = re.search(r"<thinking>(.*?)</thinking>", action_text, re.DOTALL)
            thinking_content = thinking_match.group(1).strip() if thinking_match else None

            if observation_content and thinking_content:
                action_text = f"**OBSERVATION**\n{observation_content}\n\n**THINKING**\n{thinking_content}"

            # Create a white panel (same height as the observation image)
            panel = Image.new("RGB", (white_panel_width, obs_img.height), "white")
            draw = ImageDraw.Draw(panel)
            font = ImageFont.load_default()

            # Wrap the action text if it is too long
            max_chars_per_line = 40  # Adjusted for larger font size
            wrapped_text = textwrap.fill(action_text, width=max_chars_per_line)

            # Calculate text block size and center it on the panel
            try:
                # Use multiline_textbbox if available (returns bounding box tuple)
                bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
                text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                # Fallback for older Pillow versions: compute size for each line
                lines = wrapped_text.splitlines() or [wrapped_text]
                line_sizes = [draw.textsize(line, font=font) for line in lines]
                text_width = max(width for width, _ in line_sizes)
                text_height = sum(height for _, height in line_sizes)
            text_x = (white_panel_width - text_width) // 2
            text_y = (obs_img.height - text_height) // 2
            draw.multiline_text((text_x, text_y), wrapped_text, fill="black", font=font, align="center")

            # Create the combined frame by concatenating the observation image and the panel
            total_width = obs_img.width + white_panel_width
            combined_frame = Image.new("RGB", (total_width, obs_img.height))
            combined_frame.paste(obs_img, (0, 0))
            combined_frame.paste(panel, (obs_img.width, 0))
            frames.append(combined_frame)

            # Skip the Action record since it has been processed with this Observation
            if i + 1 < len(history) and isinstance(history[i + 1], Action):
                i += 2
            else:
                i += 1
        else:
            i += 1

    if frames:
        frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
    else:
        raise ValueError("No frames were generated from the Run object's history.")


# Example usage:
if __name__ == "__main__":
    from proxy_lite.recorder import Run

    dummy_run = Run.load("0abdb4cb-f289-48b0-ba13-35ed1210f7c1")

    num_steps = int(len(dummy_run.history) / 2)
    print(f"Number of steps: {num_steps}")
    output_gif_path = "trajectory.gif"
    create_run_gif(dummy_run, output_gif_path, duration=1000)
    print(f"Trajectory GIF saved to {output_gif_path}")
