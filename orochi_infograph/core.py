
"""
Core module for generating the Orochi Infograph image.

This module provides functions to parse raw text metrics and build a visual
infographic image using Pillow, suitable for Discord posting.
"""

import io
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- Constants ---

WIDTH = 768  # Width of the generated image
HEIGHT = 768 # Height of the generated image
BG_COLOR = "#B6E18D"  # Background color of the image
PANEL_COLOR = "#FAFAE6" # Color of the metric panels
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc" # Path to the system font for text rendering
OROCHI_PATH = Path(__file__).parent / "assets" / "plush_orochi.png" # Path to the Orochi illustration

# --- Public Functions ---

def parse_metrics(raw_txt: str) -> tuple[dict, str, str]:
    """
    Parses raw text data to extract metrics, title, and timestamp.

    Args:
        raw_txt (str): The raw text string containing the metrics and title.
                       Expected format:
                       ◆Title (Timestamp)
                       ・Metric Name Value Unit (前日比 DiffValue Unit)

    Returns:
        tuple[dict, str, str]: A tuple containing:
            - metrics (dict): A dictionary where keys are metric names and values
                              are dictionaries with 'val', 'unit', and 'diff'.
            - title (str): The extracted title without the '◆' prefix.
            - title_timestamp (str): The extracted timestamp from the title.
    """
    metrics = {}
    title = ""
    title_timestamp = ""
    lines = raw_txt.strip().split("\n")

    # Regex for metric lines: captures key, value, unit, and difference
    metric_pattern = re.compile(r"^\s*・(.+?)\s+([\d\.,]+)(.*?)\s*（前日比\s*([+-]?[\d\.,]+[^）]*)）")
    # Regex for title line: captures the main title and its timestamp
    title_pattern = re.compile(r"^(◆.+?)\s*（(.+?)時点）")

    for line in lines:
        if line.startswith("◆"): # Check if the line is the title line
            title_match = title_pattern.match(line)
            if title_match:
                # Extract title and remove '◆' prefix
                title = title_match.group(1).strip().replace("◆", "")
                # Extract timestamp and re-add "時点"
                title_timestamp = title_match.group(2).strip() + "時点"
            continue # Skip title line for metrics parsing

        metric_match = metric_pattern.match(line)
        if metric_match:
            key, val, unit, diff = metric_match.groups()
            metrics[key.strip()] = {
                "val": val.strip(),
                "unit": unit.strip(),
                "diff": diff.strip(),
            }
    return metrics, title, title_timestamp

def build_image(metrics: dict, title: str, title_timestamp: str) -> io.BytesIO:
    """
    Builds an infographic image based on the provided metrics, title, and timestamp.

    Args:
        metrics (dict): A dictionary of parsed metrics.
        title (str): The main title for the infographic.
        title_timestamp (str): The timestamp to display at the bottom of the image.

    Returns:
        io.BytesIO: A BytesIO object containing the generated PNG image data.
    """
    # --- Image Setup ---
    img = Image.new("RGB", (WIDTH, HEIGHT), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- Font Setup ---
    # Load fonts with specific sizes and weights (index=1 for regular, index=2 for bolder)
    try:
        font_metric_name = ImageFont.truetype(FONT_PATH, size=35, index=1) # Smaller for metric names
        font_metric_value = ImageFont.truetype(FONT_PATH, size=55, index=2) # Larger for metric values
        font_small = ImageFont.truetype(FONT_PATH, size=28, index=1) # For diff and timestamp
        font_title = ImageFont.truetype(FONT_PATH, size=48, index=2) # For title
    except IOError:
        # Fallback to default font if custom font is not found or fails to load
        font_metric_name = ImageFont.load_default()
        font_metric_value = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_title = ImageFont.load_default()

    # --- Draw Title ---
    if title:
        # Split the title into two lines for better layout
        split_point = "トークン"
        if split_point in title:
            parts = title.split(split_point, 1)
            line1_text = parts[0] + split_point
            line2_text = parts[1]
        else:
            line1_text = title
            line2_text = ""

        # Draw the first line of the title, centered
        line1_bbox = draw.textbbox((0,0), line1_text, font=font_title)
        line1_width = line1_bbox[2] - line1_bbox[0]
        line1_height = line1_bbox[3] - line1_bbox[1]
        line1_x = (WIDTH - line1_width) / 2
        draw.text((line1_x, 30), line1_text, font=font_title, fill="#333366")

        # Draw the second line of the title if it exists, centered below the first line
        if line2_text:
            line2_bbox = draw.textbbox((0,0), line2_text, font=font_title)
            line2_width = line2_bbox[2] - line2_bbox[0]
            line2_height = line2_bbox[3] - line2_bbox[1]
            line2_x = (WIDTH - line2_width) / 2
            # Position line2 below line1 with some padding
            draw.text((line2_x, 30 + line1_height + 10), line2_text, font=font_title, fill="#333366")
            # Adjust initial Y offset for panels to accommodate two lines of title
            initial_y_offset = 30 + line1_height + 10 + line2_height + 30
        else:
            # Adjust initial Y offset for panels for a single line title
            initial_y_offset = 30 + line1_height + 20

    else:
        # Default initial Y offset if no title is provided
        initial_y_offset = 50

    # --- Draw Panels and Text ---
    y_offset = initial_y_offset
    for key, data in metrics.items():
        # Draw the background rectangle for each metric panel
        draw.rectangle([50, y_offset, WIDTH - 50, y_offset + 100], fill=PANEL_COLOR)

        # Draw the metric name (e.g., "メンバー数")
        draw.text((80, y_offset + 5), key, font=font_metric_name, fill="#333366")

        # Draw the metric value and unit (e.g., "21,826人")
        val_unit = f"{data['val']} {data['unit']}"
        draw.text((80, y_offset + 45), val_unit, font=font_metric_value, fill="#333366")

        # Draw the "前日比" label and the difference value
        diff_color = "green" if data['diff'].startswith("+") else "blue" # Color based on positive/negative difference
        draw.text((WIDTH - 320, y_offset + 55), "前日比", font=font_small, fill="#333366")
        draw.text((WIDTH - 220, y_offset + 55), data['diff'], font=font_small, fill=diff_color)

        # Move to the next panel position
        y_offset += 120 # Panel height + padding

    # --- Timestamp ---
    # Draw the timestamp at the bottom of the image
    draw.text((50, HEIGHT - 70), title_timestamp, font=font_small, fill="#333366")

    # --- Orochi Image ---
    # Paste the Orochi illustration onto the image
    if OROCHI_PATH.exists():
        orochi_img = Image.open(OROCHI_PATH).convert("RGBA")
        orochi_img = orochi_img.resize((300, 300)) # Resize the illustration
        # Position the illustration at the bottom-right with some padding
        img.paste(orochi_img, (WIDTH - 300 - 30, HEIGHT - 300 + 20), orochi_img)


    # --- Return as BytesIO ---
    # Save the image to a BytesIO object and return it
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# --- dunder all ---
# Define public API of the module
__all__ = ["parse_metrics", "build_image"]
