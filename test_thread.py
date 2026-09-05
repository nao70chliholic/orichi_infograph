import asyncio
import os
import sys

# Add the project root and bot to sys.path so we can import bot
sys.path.append(os.path.abspath('.'))
sys.path.append(os.path.abspath('bot'))

from bot.main import run_cli_script

async def test():
    loop = asyncio.get_running_loop()
    import functools
    log_file_path = "cron.log"
    blocking_task = functools.partial(run_cli_script, log_file_path, "test")
    await loop.run_in_executor(None, blocking_task)

if __name__ == '__main__':
    asyncio.run(test())
