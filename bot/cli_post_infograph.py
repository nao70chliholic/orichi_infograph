"""
Discord Infograph Bot CLI.

This script fetches metric data from a Discord channel using the Discord API,
generates an infographic image, and posts it back to Discord via Webhook.
"""

import json
import os
import sys
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook

# Add project root to Python path to allow importing local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orochi_infograph import core

# --- Environment Variables ---
load_dotenv() # Load environment variables from .env file

# Debugging: Print loaded environment variables
print(f"DEBUG: DISCORD_BOT_TOKEN loaded: {bool(os.getenv('DISCORD_BOT_TOKEN'))}")
print(f"DEBUG: DISCORD_CHANNEL_ID loaded: {bool(os.getenv('DISCORD_CHANNEL_ID'))}")
webhook_debug_urls = {k: v for k, v in os.environ.items() if k.startswith("DISCORD_WEBHOOK_URL")}
print(f"DEBUG: Found Webhook URLs: {webhook_debug_urls}")


target_channel_ids_env = os.getenv("DISCORD_TARGET_CHANNEL_IDS", "")
target_channel_ids = [cid.strip() for cid in target_channel_ids_env.split(",") if cid.strip()]
print(f"DEBUG: DISCORD_TARGET_CHANNEL_IDS parsed: {target_channel_ids}")


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") # Discord Bot Token (for API access)
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID") # ID of the Discord channel to read from

# Collect all webhook URLs from environment variables
# This will find DISCORD_WEBHOOK_URL, DISCORD_WEBHOOK_URL_2, DISCORD_WEBHOOK_URL_3, etc.
webhook_urls = [
    value for key, value in os.environ.items()
    if key.startswith("DISCORD_WEBHOOK_URL") and value
]
# Keep insertion order, but deduplicate exact URLs (avoid same webhook fired twice)
seen = set()
unique_webhook_urls = []
for url in webhook_urls:
    if url not in seen:
        seen.add(url)
        unique_webhook_urls.append(url)

if len(webhook_urls) != len(unique_webhook_urls):
    print(f"DEBUG: Removed {len(webhook_urls) - len(unique_webhook_urls)} duplicated webhook URLs")

webhook_urls = unique_webhook_urls

# --- Constants ---
MAX_RETRIES = 3
FETCH_RETRY_DELAY = 10  # seconds to wait for source data
POST_RETRY_DELAY = 5    # seconds to wait for network issues
REQUEST_TIMEOUT = 15    # seconds to wait for a response from Discord

# --- Main Logic ---

def main():
    """
    Main function to fetch data, generate image, and post to Discord.
    """
    total_start_time = time.time()
    print(f"--- Script started at {datetime.now()} ---")

    # Validate essential environment variables
    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
        print("Error: DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set in the .env file.")
        sys.exit(1)

    if not webhook_urls and not target_channel_ids:
        print("Error: Configure at least one DISCORD_WEBHOOK_URL... or provide DISCORD_TARGET_CHANNEL_IDS in the .env file.")
        sys.exit(1)

    # Discord API endpoint for fetching channel messages
    API_URL = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    HEADERS = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    MESSAGE_POST_HEADERS = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}"
    }

    # 1. Fetch Raw Text Data from Discord API (with retries)
    start_time = time.time()
    raw_text_data = ""
    
    for attempt in range(MAX_RETRIES):
        try:
            print(f"Fetching messages from Discord... (Attempt {attempt + 1}/{MAX_RETRIES})")
            response = requests.get(API_URL, headers=HEADERS, params={"limit": 20}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            messages = response.json()

            candidates: list[tuple[int, int, str]] = []
            for idx, message in enumerate(messages):
                content = (message.get("content") or "").strip()
                if not content:
                    continue

                metrics, title, title_timestamp = core.parse_metrics(
                    content, target_keys=core.DEFAULT_TARGET_KEYS
                )

                # 日報（現在情報）だけを対象にする（週報は無視）
                if "週報" in content or "週報" in title:
                    continue
                if "現在情報" not in content and "現在情報" not in title:
                    continue
                if "時点" not in content and "時点" not in title_timestamp:
                    continue
                if len(metrics) != len(core.DEFAULT_TARGET_KEYS):
                    continue

                score = len(metrics)

                # Keep the best-scoring candidate; if tie, prefer newer (smaller idx).
                candidates.append((score, -idx, content))

            if candidates:
                candidates.sort(reverse=True)
                raw_text_data = candidates[0][2]
                print(
                    "Selected message "
                    f"(score={candidates[0][0]}): {raw_text_data[:200]}..."
                )
            
            if raw_text_data:
                break  # Success, exit retry loop

            print("Relevant data not found in latest messages.")

        except requests.exceptions.RequestException as e:
            print(f"Error fetching messages from Discord API: {e}")
        
        if attempt < MAX_RETRIES - 1:
            print(f"Retrying in {FETCH_RETRY_DELAY} seconds...")
            time.sleep(FETCH_RETRY_DELAY)
        else:
            print("Failed to fetch data after multiple attempts.")

    print(f"--- 1. Discord API fetch took: {time.time() - start_time:.2f} seconds ---")

    if not raw_text_data:
        print("Error: Could not find relevant data in channel history. Exiting.")
        sys.exit(1)

    # 2. Parse Metrics, Title, and Title Timestamp
    start_time = time.time()
    metrics, title, title_timestamp = core.parse_metrics(
        raw_text_data, target_keys=core.DEFAULT_TARGET_KEYS
    )
    print("Parsed Metrics:", metrics)
    print("Parsed Title:", title)
    print("Parsed Title Timestamp:", title_timestamp)
    print(f"--- 2. Parsing data took: {time.time() - start_time:.2f} seconds ---")

    if not metrics:
        print("Error: Parsed metrics is empty; refusing to post a blank infographic.")
        sys.exit(1)

    # 3. Build Infographic Image
    start_time = time.time()
    image_bytes = core.build_image(metrics, title, title_timestamp)
    image_bytes.seek(0)
    image_data = image_bytes.getvalue()
    print(f"--- 3. Image generation took: {time.time() - start_time:.2f} seconds ---")

    # 4. Post the generated image to Discord via Webhooks (with retries)
    start_time = time.time()
    image_filename = "orochi_infograph.png"

    all_posts_successful = True
    for url in webhook_urls:
        if not url:
            continue

        post_successful = False
        for attempt in range(MAX_RETRIES):
            try:
                webhook = DiscordWebhook(url=url)
                webhook.add_file(file=image_data, filename=image_filename)

                print(f"Sending image to {url[:40]}... (Attempt {attempt + 1}/{MAX_RETRIES})")
                response = webhook.execute()

                if response.status_code in [200, 204]:
                    print(f"Successfully posted to {url[:40]}.")
                    post_successful = True
                    break
                else:
                    print(f"Error posting to {url[:40]}: {response.status_code} {response.reason}")
                    print(response.content)

            except requests.exceptions.RequestException as e:
                print(f"Network error posting to {url[:40]}: {e}")

            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {POST_RETRY_DELAY} seconds...")
                time.sleep(POST_RETRY_DELAY)
        
        if not post_successful:
            print(f"Failed to post to {url[:40]} after {MAX_RETRIES} attempts.")
            all_posts_successful = False

    for channel_id in target_channel_ids:
        post_successful = False
        for attempt in range(MAX_RETRIES):
            try:
                print(f"Sending image via bot to channel {channel_id}... (Attempt {attempt + 1}/{MAX_RETRIES})")
                payload = {"content": ""}
                files = {
                    "files[0]": (image_filename, image_data, "image/png")
                }

                response = requests.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers=MESSAGE_POST_HEADERS,
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=REQUEST_TIMEOUT
                )

                if response.status_code in (200, 201):
                    print(f"Successfully posted to channel {channel_id}.")
                    post_successful = True
                    break
                if response.status_code == 429:
                    retry_after = response.json().get("retry_after", POST_RETRY_DELAY)
                    print(f"Rate limited posting to channel {channel_id}. Retrying in {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                print(f"Error posting to channel {channel_id}: {response.status_code} {response.text}")

            except requests.exceptions.RequestException as e:
                print(f"Network error posting to channel {channel_id}: {e}")

            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {POST_RETRY_DELAY} seconds...")
                time.sleep(POST_RETRY_DELAY)

        if not post_successful:
            print(f"Failed to post to channel {channel_id} after {MAX_RETRIES} attempts.")
            all_posts_successful = False

    print(f"--- 4. Discord delivery took: {time.time() - start_time:.2f} seconds ---")
    
    if not all_posts_successful:
        print("Warning: One or more webhooks failed to post.")
        # Optionally, exit with an error code if any webhook fails
        # sys.exit(1)

    print(f"--- Total script execution time: {time.time() - total_start_time:.2f} seconds ---")


if __name__ == "__main__":
    main()
