"""
Discord Infograph Bot CLI.

This script fetches metric data from a Discord channel using the Discord API,
generates an infographic image, and posts it back to Discord via Webhook.
"""

import argparse
import hashlib
import json
import os
import sys
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook
from typing import Optional

# --- Constants ---
# These need to be available before helper functions are invoked at import-time
MAX_RETRIES = 3
FETCH_RETRY_DELAY = 10  # seconds to wait for source data
POST_RETRY_DELAY = 5    # seconds to wait for network issues
REQUEST_TIMEOUT = 15    # seconds to wait for a response from Discord

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
# Keep insertion order while deduplicating channel IDs
seen = set()
unique_target_channel_ids = []
for channel_id in target_channel_ids:
    if channel_id not in seen:
        seen.add(channel_id)
        unique_target_channel_ids.append(channel_id)
if len(target_channel_ids) != len(unique_target_channel_ids):
    print(f"DEBUG: Removed {len(target_channel_ids) - len(unique_target_channel_ids)} duplicated target channel IDs")
target_channel_ids = unique_target_channel_ids
print(f"DEBUG: DISCORD_TARGET_CHANNEL_IDS parsed: {target_channel_ids}")


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") # Discord Bot Token (for API access)
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID") # ID of the Discord channel to read from

# Collect all webhook URLs from environment variables
# This will find DISCORD_WEBHOOK_URL, DISCORD_WEBHOOK_URL_2, DISCORD_WEBHOOK_URL_3, etc.
webhook_urls = [
    value.strip() for key, value in os.environ.items()
    if key.startswith("DISCORD_WEBHOOK_URL") and value and value.strip()
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

# Attempt to resolve webhook target channel IDs and deduplicate webhooks
# that point to the same destination channel to avoid duplicate posts.
def _resolve_webhook_channel_id(url: str, timeout: int | None = None) -> Optional[str]:
    if timeout is None:
        timeout = REQUEST_TIMEOUT

    try:
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            raise ValueError("Invalid webhook URL format")

        webhook_id = parts[-2]
        webhook_token = parts[-1]
        info_url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}"
        resp = requests.get(info_url, timeout=timeout)
        if resp.ok:
            info = resp.json()
            return str(info.get("channel_id"))
        print(f"DEBUG: Webhook info request failed for {url[:40]}: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"DEBUG: Could not resolve webhook info for {url[:40]}: {e}")
    return None

seen_channels = set()
resolved_webhook_urls = []
unresolved_webhook_urls = []
for url in webhook_urls:
    channel_id = _resolve_webhook_channel_id(url)
    if channel_id:
        if channel_id in seen_channels:
            print(f"DEBUG: Removing webhook {url[:40]} — duplicate target channel {channel_id}")
            continue
        seen_channels.add(channel_id)
        resolved_webhook_urls.append(url)
    else:
        unresolved_webhook_urls.append(url)

if resolved_webhook_urls and unresolved_webhook_urls:
    print(f"DEBUG: Resolved {len(resolved_webhook_urls)} webhook(s) and kept {len(unresolved_webhook_urls)} unresolved webhook(s).")
    webhook_urls = resolved_webhook_urls + unresolved_webhook_urls
elif resolved_webhook_urls:
    print(f"DEBUG: Resolved {len(resolved_webhook_urls)} webhook(s); no unresolved webhook URLs.")
    webhook_urls = resolved_webhook_urls
elif unresolved_webhook_urls:
    print(f"DEBUG: Could not resolve any webhook channel IDs; using {len(unresolved_webhook_urls)} original webhook(s).")
    webhook_urls = unresolved_webhook_urls
else:
    print("DEBUG: No webhook URLs configured.")
    webhook_urls = []

print(f"DEBUG: Final webhook URL count after resolution: {len(webhook_urls)}")

# --- Main Logic ---

def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and post Orochi infograph images.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the infographic image locally without posting to Discord."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="dry_infograph.png",
        help="Output file path for dry-run image generation."
    )
    return parser.parse_args()

def main(dry_run: bool = False, output_path: str | None = None):
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

    print(f"DEBUG: Using {len(webhook_urls)} webhook(s) and {len(target_channel_ids)} target channel IDs.")

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

    if dry_run:
        dry_output = output_path or "dry_infograph.png"
        try:
            with open(dry_output, "wb") as f:
                f.write(image_data)
            print(f"Dry run complete: wrote infographic to {dry_output}")
            sys.exit(0)
        except Exception as e:
            print(f"Error: Failed to write dry-run image to {dry_output}: {e}")
            sys.exit(1)

    # Idempotency guard: avoid posting the same infographic twice
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    posted_record_file = os.path.join(project_root, '.last_posted.json')
    metrics_hash = hashlib.sha256(
        json.dumps(metrics, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()
    post_key = f"{title}|{title_timestamp}|{metrics_hash}"
    try:
        prev = {}
        if os.path.exists(posted_record_file):
            with open(posted_record_file, 'r', encoding='utf-8') as pf:
                prev = json.load(pf)
        if prev.get('last_key') == post_key:
            print("INFO: Same infographic already posted previously; skipping to avoid duplicate.")
            sys.exit(0)
    except Exception as e:
        print(f"DEBUG: Could not read posted record file: {e}")

    # 4. Post the generated image to Discord via Webhooks (with retries)
    start_time = time.time()
    image_filename = "orochi_infograph.png"

    all_posts_successful = True
    any_webhook_success = False
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
                    any_webhook_success = True
                    break
                else:
                    print(f"Error posting to {url[:40]}: {response.status_code} {getattr(response, 'reason', '')}")
                    try:
                        print(response.content)
                    except Exception:
                        pass

            except requests.exceptions.RequestException as e:
                print(f"Network error posting to {url[:40]}: {e}")
            except Exception as e:
                print(f"Error posting to {url[:40]}: {e}")

            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {POST_RETRY_DELAY} seconds...")
                time.sleep(POST_RETRY_DELAY)
        
        if not post_successful:
            print(f"Failed to post to {url[:40]} after {MAX_RETRIES} attempts.")
            all_posts_successful = False

    if webhook_urls and target_channel_ids and not any_webhook_success:
        print("DEBUG: All webhook posts failed; falling back to bot channel posting.")
        webhook_urls = []

    if webhook_urls and target_channel_ids:
        print("DEBUG: Both webhook URLs and target channel IDs are configured; posting only via webhooks to avoid duplicate infographic delivery.")
    else:
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
                except Exception as e:
                    print(f"Error posting to channel {channel_id}: {e}")

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
    else:
        # Record successful post to prevent immediate duplicates from other triggers
        try:
            with open(posted_record_file, 'w', encoding='utf-8') as pf:
                json.dump({'last_key': post_key, 'timestamp': time.time()}, pf)
        except Exception as e:
            print(f"DEBUG: Failed to write posted record file: {e}")

    print(f"--- Total script execution time: {time.time() - total_start_time:.2f} seconds ---")


if __name__ == "__main__":
    args = parse_cli_args()
    main(dry_run=args.dry_run, output_path=args.output)
