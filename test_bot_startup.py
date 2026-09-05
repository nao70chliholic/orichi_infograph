#!/usr/bin/env python3
"""
Quick test to verify the bot can start without errors.
"""
import sys
import os

# Add bot directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

try:
    from dotenv import load_dotenv
    import discord
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(dotenv_path=env_path)
    
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not found in .env")
        sys.exit(1)
    
    print("✓ All dependencies loaded successfully")
    print("✓ Token is configured")
    print("\nBot can start. Attempting to run bot...")
    
    # Try importing bot.main
    import bot.main
    print("✓ bot.main imported successfully")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
