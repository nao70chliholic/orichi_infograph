
"""
Core module for generating the Orochi Infograph image.

This module provides functions to parse raw text metrics and build a visual
infographic image using Pillow, suitable for Discord posting.
"""

import io
import os
import re
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont

# --- Constants ---

WIDTH = 768  # Width of the generated image
HEIGHT = 768 # Height of the generated image
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc" # Path to the system font for text rendering
ASSETS_DIR = Path(__file__).parent / "assets"

# --- 配色とイラスト ---
# 環境変数を設定しなければ既定値（開運オロチ）で動く。
# コミュニティごとにテーマを変えたいときだけ、呼び出し側で環境変数を渡す。
BG_COLOR = os.getenv("INFOGRAPH_BG_COLOR", "#B6E18D")       # 背景
PANEL_COLOR = os.getenv("INFOGRAPH_PANEL_COLOR", "#FAFAE6") # 指標パネル
TEXT_COLOR = os.getenv("INFOGRAPH_TEXT_COLOR", "#333366")   # パネル内の見出し・数値
# タイトルと日時は背景の上に載るので、濃い背景を使うときはここだけ明るくする
TITLE_COLOR = os.getenv("INFOGRAPH_TITLE_COLOR", "") or TEXT_COLOR
UP_COLOR = os.getenv("INFOGRAPH_UP_COLOR", "green")         # プラスの差分／買い
DOWN_COLOR = os.getenv("INFOGRAPH_DOWN_COLOR", "blue")      # マイナスの差分／売り

# 右下のイラスト。assets/ 配下のファイル名か、絶対パスで指定する
_character_raw = os.getenv("INFOGRAPH_CHARACTER", "plush_orochi.png")
CHARACTER_PATH = Path(_character_raw) if os.path.isabs(_character_raw) else ASSETS_DIR / _character_raw
OROCHI_PATH = CHARACTER_PATH  # 後方互換のための別名

# NFTのPFPのように背景が白い正方形の画像は、そのまま貼ると白い四角になる。
# "circle" を指定すると円形に切り抜いてアイコンとして置く。
CHARACTER_SHAPE = os.getenv("INFOGRAPH_CHARACTER_SHAPE", "none")
CHARACTER_SIZE = int(os.getenv("INFOGRAPH_CHARACTER_SIZE", "300"))
# 透過PNGをJPGに変換すると、透過部分が黒（や白）で塗り潰される。
# "1" を指定すると、四隅から連結している均一な背景を透過に戻す。
CHARACTER_STRIP_BG = os.getenv("INFOGRAPH_CHARACTER_STRIP_BG", "") == "1"
# タイトルを2行に折るときの区切り文字（見つからなければ自動で縮小する）
TITLE_SPLIT = os.getenv("INFOGRAPH_TITLE_SPLIT", "トークン")

# --- Public Functions ---

DEFAULT_TARGET_KEYS: tuple[str, ...] = ("メンバー数", "トークン価格", "24時間の売買")
WEEKLY_TARGET_KEYS: tuple[str, ...] = ("メンバー数", "トークン価格", "今週の売買")


def _parse_breakdown(text: str) -> list[tuple[str, str]]:
    """
    「買い 1,775枚／売り 2,473枚」を [("買い", "1,775枚"), ("売り", "2,473枚")] にします。
    """
    items: list[tuple[str, str]] = []
    for part in re.split(r"[／/、]", text):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(?P<name>\D+?)\s*(?P<value>[\d\.,]+\s*\S*)$", part)
        if m:
            items.append((m.group("name").strip(), m.group("value").strip()))
    return items


def parse_metrics(raw_txt: str, *, target_keys: tuple[str, ...] | None = None) -> tuple[dict, str, str]:
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

    # Regex for metric lines: captures key, value, unit, and difference.
    # Supports full-width/half-width parentheses and various diff labels (前日比/前週比/前回比).
    metric_pattern = re.compile(
        r"^\s*・\s*(?P<key>.+?)\s+"
        r"(?P<val>[\d\.,]+)\s*(?P<unit>[^（(]+?)\s*"
        r"[（(]\s*(?P<label>前日比|前週比|前回比)\s*(?P<diff>[^）)]+)\s*[）)]\s*$"
    )
    # 「・24時間の売買 4,249枚（買い 1,775枚／売り 2,473枚）」のような内訳つきの行
    breakdown_pattern = re.compile(
        r"^\s*・\s*(?P<key>.+?)\s+"
        r"(?P<val>[\d\.,]+)\s*(?P<unit>[^（(]+?)\s*"
        r"[（(]\s*(?P<breakdown>[^）)]+)\s*[）)]\s*$"
    )
    # 「・時価総額 26,381,054円」のような括弧のない行
    plain_pattern = re.compile(
        r"^\s*・\s*(?P<key>.+?)\s+(?P<val>[\d\.,]+)\s*(?P<unit>[^（()\s]*)\s*$"
    )
    # Regex for title line: captures the main title and its timestamp (anything inside parentheses).
    title_pattern = re.compile(r"^(◆.+?)\s*[（(]\s*(.+?)\s*[）)]\s*$")

    for line in lines:
        if line.startswith("◆"):  # Check if the line is the title line
            title_match = title_pattern.match(line)
            if title_match:
                # Extract title and remove '◆' prefix
                title = title_match.group(1).strip().replace("◆", "")
                # Extract timestamp (keep as-is if it already ends with "時点")
                raw_ts = title_match.group(2).strip()
                title_timestamp = raw_ts if raw_ts.endswith("時点") else raw_ts
            continue # Skip title line for metrics parsing

        metric_match = metric_pattern.match(line)
        if metric_match:
            metrics[metric_match.group("key").strip()] = {
                "val": metric_match.group("val").strip(),
                "unit": metric_match.group("unit").strip(),
                "diff": metric_match.group("diff").strip(),
                "label": metric_match.group("label").strip(),
            }
            continue

        breakdown_match = breakdown_pattern.match(line)
        if breakdown_match:
            metrics[breakdown_match.group("key").strip()] = {
                "val": breakdown_match.group("val").strip(),
                "unit": breakdown_match.group("unit").strip(),
                "breakdown": _parse_breakdown(breakdown_match.group("breakdown")),
            }
            continue

        plain_match = plain_pattern.match(line)
        if plain_match:
            metrics[plain_match.group("key").strip()] = {
                "val": plain_match.group("val").strip(),
                "unit": plain_match.group("unit").strip(),
            }

    if target_keys is not None:
        filtered: dict = {}
        for k in target_keys:
            if k in metrics:
                filtered[k] = metrics[k]
        metrics = filtered

    return metrics, title, title_timestamp

def _strip_flat_background(image: Image.Image, tolerance: int = 24) -> Image.Image:
    """
    四隅から連結している均一な背景を透過にします。

    キャラクターの黒い輪郭まで消さないよう、色で一括指定せず塗りつぶし（floodfill）で
    外側から連結している領域だけを対象にします。
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    marker = (255, 0, 255)  # イラストに含まれない色を目印に使う
    for seed in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        ImageDraw.floodfill(rgb, seed, marker, thresh=tolerance)

    r, g, b = rgb.split()
    is_marker = ImageChops.multiply(
        ImageChops.multiply(
            r.point(lambda v: 255 if v == marker[0] else 0),
            g.point(lambda v: 255 if v == marker[1] else 0),
        ),
        b.point(lambda v: 255 if v == marker[2] else 0),
    )
    result = image.copy()
    result.putalpha(ImageChops.invert(is_marker))
    return result


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_size: int) -> ImageFont.FreeTypeFont:
    """
    max_width に収まる最大のフォントを返します（タイトルのはみ出し防止）。
    """
    for size in range(max_size, 17, -2):
        try:
            font = ImageFont.truetype(FONT_PATH, size=size, index=2)
        except IOError:
            return ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return font


def _circle_crop(image: Image.Image) -> Image.Image:
    """
    正方形の画像を円形に切り抜きます。背景が白いPFP画像をそのまま貼ると
    白い四角が残るため、アイコンとして置きたいときに使います。
    """
    size = image.size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size[0] - 1, size[1] - 1), fill=255)
    # 元画像に透過があれば、それも残す
    mask.paste(Image.new("L", size, 0), (0, 0), Image.eval(image.getchannel("A"), lambda v: 255 - v))
    result = image.copy()
    result.putalpha(mask)
    return result


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
        split_point = TITLE_SPLIT
        if split_point and split_point in title:
            parts = title.split(split_point, 1)
            line1_text = parts[0] + split_point
            line2_text = parts[1]
        else:
            line1_text = title
            line2_text = ""

        # Draw the first line of the title, centered
        max_title_width = WIDTH - 60
        font_title = _fit_font(draw, line1_text, max_title_width, 48)
        if line2_text:
            font_title = min(
                font_title, _fit_font(draw, line2_text, max_title_width, 48), key=lambda f: f.size
            )
        line1_bbox = draw.textbbox((0,0), line1_text, font=font_title)
        line1_width = line1_bbox[2] - line1_bbox[0]
        line1_height = line1_bbox[3] - line1_bbox[1]
        line1_x = (WIDTH - line1_width) / 2
        draw.text((line1_x, 30), line1_text, font=font_title, fill=TITLE_COLOR)

        # Draw the second line of the title if it exists, centered below the first line
        if line2_text:
            line2_bbox = draw.textbbox((0,0), line2_text, font=font_title)
            line2_width = line2_bbox[2] - line2_bbox[0]
            line2_height = line2_bbox[3] - line2_bbox[1]
            line2_x = (WIDTH - line2_width) / 2
            # Position line2 below line1 with some padding
            draw.text((line2_x, 30 + line1_height + 10), line2_text, font=font_title, fill=TITLE_COLOR)
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
        draw.text((80, y_offset + 5), key, font=font_metric_name, fill=TEXT_COLOR)

        # Draw the metric value and unit (e.g., "21,826人")
        val_unit = f"{data['val']} {data['unit']}"
        draw.text((80, y_offset + 45), val_unit, font=font_metric_value, fill=TEXT_COLOR)

        # 右側は、差分がある行は「前日比 +2人」、内訳がある行は「買い/売り」を積む
        if "breakdown" in data:
            for i, (name, value) in enumerate(data["breakdown"][:2]):
                # 買いは緑、売りは青（差分の色分けと揃える）
                item_color = UP_COLOR if i == 0 else DOWN_COLOR
                item_y = y_offset + 20 + i * 40
                draw.text((WIDTH - 320, item_y), name, font=font_small, fill=TEXT_COLOR)
                draw.text((WIDTH - 250, item_y), value, font=font_small, fill=item_color)
        elif "diff" in data:
            diff_prefix = data["diff"][:1]
            diff_color = UP_COLOR if diff_prefix in {"+", "＋"} else DOWN_COLOR  # Color based on positive/negative difference
            diff_label = data.get("label", "前日比")
            draw.text((WIDTH - 320, y_offset + 55), diff_label, font=font_small, fill=TEXT_COLOR)
            draw.text((WIDTH - 220, y_offset + 55), data['diff'], font=font_small, fill=diff_color)

        # Move to the next panel position
        y_offset += 120 # Panel height + padding

    # --- Timestamp ---
    # Draw the timestamp at the bottom of the image
    draw.text((50, HEIGHT - 70), title_timestamp, font=font_small, fill=TITLE_COLOR)

    # --- キャラクターのイラスト ---
    if CHARACTER_PATH.exists():
        character = Image.open(CHARACTER_PATH).convert("RGBA")
        character = character.resize((CHARACTER_SIZE, CHARACTER_SIZE))
        if CHARACTER_STRIP_BG:
            character = _strip_flat_background(character)
        if CHARACTER_SHAPE == "circle":
            character = _circle_crop(character)
            # 円は切れると不自然なので、canvas の内側に収める
            position = (WIDTH - CHARACTER_SIZE - 40, HEIGHT - CHARACTER_SIZE - 40)
        else:
            position = (WIDTH - CHARACTER_SIZE - 30, HEIGHT - CHARACTER_SIZE + 20)
        img.paste(character, position, character)


    # --- Return as BytesIO ---
    # Save the image to a BytesIO object and return it
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# --- dunder all ---
# Define public API of the module
__all__ = ["DEFAULT_TARGET_KEYS", "WEEKLY_TARGET_KEYS", "parse_metrics", "build_image"]
