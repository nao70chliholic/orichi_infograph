"""
Discord Infograph Bot CLI.

This script fetches metric data from a Discord channel using the Discord API,
generates an infographic image, and posts it back to Discord via Webhook.
"""

import os
import sys
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

# Add project root to Python path to allow importing local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orochi_infograph import core

# --- Environment Variables ---
load_dotenv() # Load environment variables from .env file

# Debugging: Print loaded environment variables
print(f"DEBUG: DISCORD_BOT_TOKEN loaded: {bool(os.getenv("DISCORD_BOT_TOKEN"))}")
print(f"DEBUG: DISCORD_CHANNEL_ID loaded: {bool(os.getenv("DISCORD_CHANNEL_ID"))}")
print(f"DEBUG: DISCORD_WEBHOOK_URL loaded: {bool(os.getenv("DISCORD_WEBHOOK_URL"))}")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") # Discord Bot Token (for API access)
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID") # ID of the Discord channel to read from
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") # Webhook URL to post the image to
DISCORD_WEBHOOK_URL_2 = os.getenv("DISCORD_WEBHOOK_URL_2") # (Optional) 2nd Webhook URL

# --- Main Logic ---

def main():
    """
    Main function to fetch data, generate image, and post to Discord.
    """
    total_start_time = time.time()
    print(f"--- Script started at {datetime.now()} ---")

    # Validate essential environment variables
    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID or not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, and DISCORD_WEBHOOK_URL must be set in .env file.")
        sys.exit(1)

    # Discord API endpoint for fetching channel messages
    API_URL = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    HEADERS = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    # 1. Fetch Raw Text Data from Discord API
    start_time = time.time()
    raw_text_data = ""
    try:
        # Fetch latest messages (limit=5 to get recent ones)
        response = requests.get(API_URL, headers=HEADERS, params={"limit": 5})
        response.raise_for_status() # Raise an exception for HTTP errors
        messages = response.json()

        # Find the most recent message that matches the expected format
        for message in messages:
            # Heuristic: Check if message content starts with '◆' or '・' to identify relevant data
            if message["content"].startswith("◆") or message["content"].startswith("・"):
                raw_text_data = message["content"]
                print(f"Found relevant message: {raw_text_data[:50]}...")
                break

    except requests.exceptions.RequestException as e:
        print(f"Error fetching messages from Discord API: {e}")
        sys.exit(1)
    finally:
        print(f"--- 1. Discord API fetch took: {time.time() - start_time:.2f} seconds ---")


    # Exit if no relevant data is found
    if not raw_text_data:
        print("Error: Could not find relevant data in channel history.")
        sys.exit(1)

    # 2. Parse Metrics, Title, and Title Timestamp using the core module
    start_time = time.time()
    metrics, title, title_timestamp = core.parse_metrics(raw_text_data)
    print("Parsed Metrics:", metrics)
    print("Parsed Title:", title)
    print("Parsed Title Timestamp:", title_timestamp)
    print(f"--- 2. Parsing data took: {time.time() - start_time:.2f} seconds ---")


    # 3. Build Infographic Image using the core module
    start_time = time.time()
    image_bytes = core.build_image(metrics, title, title_timestamp)
    image_bytes.seek(0) # Reset stream position to the beginning
    print(f"--- 3. Image generation took: {time.time() - start_time:.2f} seconds ---")


    # 4. Post the generated image to Discord via Webhooks
    start_time = time.time()
    
    # Create a list of webhook URLs to post to
    webhook_urls = [DISCORD_WEBHOOK_URL]
    if DISCORD_WEBHOOK_URL_2:
        webhook_urls.append(DISCORD_WEBHOOK_URL_2)

    # Read image data once
    image_data = image_bytes.read()

    for url in webhook_urls:
        if not url:
            continue

        webhook = DiscordWebhook(url=url)
        # Reset buffer to the beginning for each webhook
        webhook.add_file(file=image_data, filename="orochi_infograph.png")

        print(f"Sending image to {url[:40]}...")
        response = webhook.execute()

        if response.status_code in [200, 204]:
            print(f"Successfully posted to {url[:40]}.")
        else:
            print(f"Error posting to {url[:40]}: {response.status_code} {response.reason}")
            print(response.content)
            
    print(f"--- 4. Discord webhook post took: {time.time() - start_time:.2f} seconds ---")
    print(f"--- Total script execution time: {time.time() - total_start_time:.2f} seconds ---")


if __name__ == "__main__":
    main()