
import discord
from discord import app_commands
from discord.ext import tasks
import os
import subprocess
import sys
import asyncio
import functools
import datetime

from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path)

# BotのトークンとサーバーIDを取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
GUILD_IDS_ENV = os.getenv("GUILD_IDS", "")

# Slashコマンドを即時利用したいGuildのID一覧（カンマ区切り or 単一ID）
GUILD_IDS = []
if GUILD_IDS_ENV:
    GUILD_IDS = [gid.strip() for gid in GUILD_IDS_ENV.split(",") if gid.strip()]
elif GUILD_ID:
    GUILD_IDS = [GUILD_ID]

JST = datetime.timezone(datetime.timedelta(hours=9))

# Botのクライアントを作成
class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._commands_synced = False

    async def setup_hook(self):
        # グローバル登録 + Guild単位の即時同期を一度だけ実行
        if not self._commands_synced:
            await self.tree.sync()
            if GUILD_IDS:
                guild_objects = [discord.Object(id=int(gid)) for gid in GUILD_IDS]
                for guild_obj in guild_objects:
                    await self.tree.sync(guild=guild_obj)
            self._commands_synced = True
        # 定期実行タスクを開始（既に動いていれば再起動しない）
        if not self.scheduled_post.is_running():
            self.scheduled_post.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    @tasks.loop(time=datetime.time(hour=7, minute=0, tzinfo=JST))
    async def scheduled_post(self):
        now = datetime.datetime.now(JST)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled post triggered.")
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        exit_code = run_cli_script(log_file_path, trigger_source="scheduled task")
        if exit_code != 0:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled CLI run failed with exit code {exit_code}.")

    @scheduled_post.before_loop
    async def before_scheduled_post(self):
        await self.wait_until_ready()
        now = datetime.datetime.now(JST)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled post loop ready. Waiting until 07:00 JST.")

    @scheduled_post.error
    async def scheduled_post_error(self, error: Exception):
        now = datetime.datetime.now(JST)
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Scheduled task error at {now} ---\n{error}\n")
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled post error: {error}")

# Botのインテントを設定
intents = discord.Intents.default()
client = MyClient(intents=intents)

def run_cli_script(log_path: str, trigger_source: str = "scheduled task"):
    """Wrapper function to run the blocking subprocess call and log its output."""
    script_path = os.path.join(os.path.dirname(__file__), "cli_post_infograph.py")
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    python_executable = os.path.join(project_root, ".venv", "bin", "python")
    
    with open(log_path, "a") as log_file:
        log_file.write(f"--- Triggered by {trigger_source} at {datetime.datetime.now()} ---\n")
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
            return None  # Indicate failure
        
        log_file.flush()
        return result.returncode

@client.tree.command()
async def graph(interaction: discord.Interaction):
    """インフォグラフィックを生成して投稿します。"""
    # Defer the response immediately, as the process takes time.
    await interaction.response.defer(ephemeral=True)

    log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")

    try:
        loop = asyncio.get_running_loop()
        
        blocking_task = functools.partial(run_cli_script, log_file_path, "slash command")
        
        # Run the blocking subprocess in a separate thread
        exit_code = await loop.run_in_executor(None, blocking_task)

        if exit_code == 0:
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
        try:
            client.run(DISCORD_BOT_TOKEN)
        except Exception as exc:
            now = datetime.datetime.now(JST)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Bot terminated unexpectedly: {exc}")
    else:
        print("エラー: DISCORD_BOT_TOKENが設定されていません。")
