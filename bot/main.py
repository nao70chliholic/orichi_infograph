
import discord
from discord import app_commands
from discord.ext import tasks
import os
from dotenv import load_dotenv
import subprocess
import sys
import asyncio
import functools
import datetime

# .envファイルから環境変数を読み込む
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path)

# BotのトークンとサーバーIDを取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# Botのクライアントを作成
class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # グローバルにコマンドを登録
        await self.tree.sync()
        # 定期実行タスクを開始
        self.scheduled_post.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    @tasks.loop(minutes=1.0)
    async def scheduled_post(self):
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Checking time for scheduled post...")
        if now.hour == 6 and now.minute == 30:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Condition met. Posting infograph...")
            log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
            run_cli_script(log_file_path)

    @scheduled_post.before_loop
    async def before_scheduled_post(self):
        await self.wait_until_ready()

# Botのインテントを設定
intents = discord.Intents.default()
client = MyClient(intents=intents)

def run_cli_script(log_path: str):
    """Wrapper function to run the blocking subprocess call and log its output."""
    script_path = os.path.join(os.path.dirname(__file__), "cli_post_infograph.py")
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    python_executable = os.path.join(project_root, ".venv", "bin", "python")
    
    with open(log_path, "a") as log_file:
        log_file.write(f"--- Triggered by scheduled task at {datetime.datetime.now()} ---\n")
        log_file.write(f"Project root: {project_root}\n")
        log_file.write(f"Python executable: {python_executable}\n")
        log_file.write(f"Script path: {script_path}\n")
        log_file.flush()

        try:
            result = subprocess.run(
                [python_executable, script_path],
                stdout=log_file,
                stderr=log_file,
                text=True,
                check=True  # Raise an exception if the command returns a non-zero exit code
            )
            log_file.write(f"--- CLI script finished with exit code {result.returncode} at {datetime.datetime.now()} ---\n")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log_file.write(f"--- CLI script failed: {e} at {datetime.datetime.now()} ---\n")
            # If there's stderr output from the process, log it
            if hasattr(e, 'stderr') and e.stderr:
                log_file.write(f"--- Stderr: ---\n{e.stderr}\n")
            return None # Indicate failure
        
        log_file.flush()
        return result

@client.tree.command()
async def graph(interaction: discord.Interaction):
    """インフォグラフィックを生成して投稿します。"""
    # Defer the response immediately, as the process takes time.
    await interaction.response.defer(ephemeral=True)

    log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")

    try:
        loop = asyncio.get_running_loop()
        
        blocking_task = functools.partial(run_cli_script, log_file_path)
        
        # Run the blocking subprocess in a separate thread
        result = await loop.run_in_executor(None, blocking_task)

        if result.returncode == 0:
            # The webhook should have posted the image.
            await interaction.followup.send("インフォグラフィックを投稿しました！")
        else:
            error_message = f"インフォグラフィックの生成に失敗しました。ログを確認してください。:disappointed_relieved:"
            await interaction.followup.send(error_message)

    except Exception as e:
        error_message = f"予期せぬエラーが発生しました。:pleading_face:\n```{str(e)}```"
        # Log the exception to the file as well
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Exception in graph command: {e} ---\n")
        await interaction.followup.send(error_message)

# Botを起動
if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        client.run(DISCORD_BOT_TOKEN)
    else:
        print("エラー: DISCORD_BOT_TOKENが設定されていません。")

