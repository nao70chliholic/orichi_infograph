
import discord
from discord import app_commands
from discord.ext import tasks
import os
import subprocess
import sys
import asyncio
import functools
import datetime
import urllib.request
from PIL import ImageFont

# Initialize macOS proxy settings and font loading on the main thread to prevent Resource deadlock in worker threads
urllib.request.getproxies()
try:
    ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", size=35, index=1)
except Exception:
    pass

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
        # if not self.daily_stats.is_running():
        #     self.daily_stats.start()
        if not self.scheduled_post.is_running():
            self.scheduled_post.start()
        if not self.weekly_post.is_running():
            self.weekly_post.start()
        if not self.cnp_weekly_post.is_running():
            self.cnp_weekly_post.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    @tasks.loop(time=datetime.time(hour=6, minute=0, tzinfo=JST))
    async def daily_stats(self):
        """毎日6時に Daily Bot (stats.py) を実行"""
        now = datetime.datetime.now(JST)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Daily stats task triggered.")
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        exit_code = run_daily_stats_script(log_file_path, trigger_source="daily stats task")
        if exit_code != 0:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Daily stats run failed with exit code {exit_code}.")

    @daily_stats.before_loop
    async def before_daily_stats(self):
        await self.wait_until_ready()
        now = datetime.datetime.now(JST)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Daily stats loop ready. Waiting until 06:00 JST.")

    @daily_stats.error
    async def daily_stats_error(self, error: Exception):
        now = datetime.datetime.now(JST)
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Daily stats task error at {now} ---\n{error}\n")
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Daily stats error: {error}")

    # 日次画像も、本人がPCを開けている時間帯（土日 6〜9時）に寄せる
    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=JST))
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
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled post loop ready. Waiting until 08:00 JST.")

    @scheduled_post.error
    async def scheduled_post_error(self, error: Exception):
        now = datetime.datetime.now(JST)
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Scheduled task error at {now} ---\n{error}\n")
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scheduled post error: {error}")

    # 週報テキストは土曜の日次と同じ実行で出る（着地 実測中央値 06:34 / 08:00までに88%）。
    # 本人がPCを開けているのが土日の 6〜9時なので、そこに 7・8・9 時を置き、
    # 取りこぼした週のために 12・15 時を後詰めにする。
    # 投稿済みなら .last_posted.json の重複ガードで空振りするので、多めに試して問題ない。
    @tasks.loop(time=[datetime.time(hour=h, minute=0, tzinfo=JST) for h in (7, 8, 9, 12, 15)])
    async def weekly_post(self):
        now = datetime.datetime.now(JST)
        if now.weekday() != 5:  # 土曜以外は何もしない
            return
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Weekly post triggered.")
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        exit_code = run_cli_script(log_file_path, trigger_source="weekly scheduled task", weekly=True)
        if exit_code != 0:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Weekly CLI run failed with exit code {exit_code}.")

    @weekly_post.before_loop
    async def before_weekly_post(self):
        await self.wait_until_ready()
        now = datetime.datetime.now(JST)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Weekly post loop ready. Waiting for Saturday 07/08/09/12/15 JST.")

    @weekly_post.error
    async def weekly_post_error(self, error: Exception):
        now = datetime.datetime.now(JST)
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Weekly task error at {now} ---\n{error}\n")
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Weekly post error: {error}")

    # CNPスタープロジェクトの週次画像。オロチと同じ時間帯を10分ずらして置く
    @tasks.loop(time=[datetime.time(hour=h, minute=10, tzinfo=JST) for h in (7, 8, 9, 12, 15)])
    async def cnp_weekly_post(self):
        now = datetime.datetime.now(JST)
        if now.weekday() != 5:  # 土曜以外は何もしない
            return
        if not os.getenv("CNP_DISCORD_WEBHOOK_URL") or not os.getenv("CNP_DISCORD_CHANNEL_ID"):
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] CNP weekly skipped: "
                  ".env に CNP_DISCORD_WEBHOOK_URL / CNP_DISCORD_CHANNEL_ID が未設定")
            return
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] CNP weekly post triggered.")
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        exit_code = run_cli_script(
            log_file_path, trigger_source="CNP weekly scheduled task", weekly=True, community="cnp"
        )
        if exit_code != 0:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] CNP weekly run failed with exit code {exit_code}.")

    @cnp_weekly_post.before_loop
    async def before_cnp_weekly_post(self):
        await self.wait_until_ready()
        now = datetime.datetime.now(JST)
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] CNP weekly loop ready. Waiting for Saturday 07/08/09/12/15:10 JST.")

    @cnp_weekly_post.error
    async def cnp_weekly_post_error(self, error: Exception):
        now = datetime.datetime.now(JST)
        log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- CNP weekly task error at {now} ---\n{error}\n")
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] CNP weekly post error: {error}")

# Botのインテントを設定
intents = discord.Intents.default()
client = MyClient(intents=intents)

def _make_subprocess_env(python_executable: str) -> dict[str, str]:
    """Build a clean subprocess environment for a venv-based Python executable."""
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)

    venv_dir = os.path.dirname(os.path.dirname(python_executable))
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = os.pathsep.join([os.path.dirname(python_executable), env.get("PATH", "")])
    return env


def run_daily_stats_script(log_path: str, trigger_source: str = "daily stats task"):
    """Wrapper function to run stats.py from the 20250715orochi_dailycounter project."""
    # Path to the Daily Counter project
    project_root = "/Users/naomatsuoka/Documents/開発/cnp/20250715orochi_dailycounter"
    script_path = os.path.join(project_root, "stats.py")
    python_executable = os.path.join(project_root, ".venv", "bin", "python3")
    env = _make_subprocess_env(python_executable)
    
    with open(log_path, "a") as log_file:
        log_file.write(f"--- Daily Stats Script triggered by {trigger_source} at {datetime.datetime.now()} ---\n")
        log_file.write(f"Project root: {project_root}\n")
        log_file.write(f"Python executable: {python_executable}\n")
        log_file.write(f"Script path: {script_path}\n")
        log_file.write(f"Subprocess VIRTUAL_ENV: {env.get('VIRTUAL_ENV')}\n")
        log_file.flush()

        try:
            result = subprocess.run(
                [python_executable, script_path],
                cwd=project_root,
                stdout=log_file,
                stderr=log_file,
                text=True,
                env=env,
                check=True
            )
            log_file.write(f"--- Daily Stats Script finished with exit code {result.returncode} at {datetime.datetime.now()} ---\n")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log_file.write(f"--- Daily Stats Script failed: {e} at {datetime.datetime.now()} ---\n")
            if hasattr(e, 'stderr') and e.stderr:
                log_file.write(f"--- Stderr: ---\n{e.stderr}\n")
            return 1  # Indicate failure
        
        log_file.flush()
        return result.returncode

# CNPスタープロジェクトの見た目。既定値（開運オロチ）を上書きする値だけを持つ。
# 由来は oridhi_dailicounter の README「コミュニティごとのテーマ」。
CNP_THEME = {
    "INFOGRAPH_BG_COLOR": "#2E3350",
    "INFOGRAPH_PANEL_COLOR": "#F5F3EC",
    "INFOGRAPH_TEXT_COLOR": "#2E3350",
    "INFOGRAPH_TITLE_COLOR": "#F3D98B",
    "INFOGRAPH_UP_COLOR": "#2E7D50",
    "INFOGRAPH_DOWN_COLOR": "#3A5BC7",
    "INFOGRAPH_CHARACTER": "MAKAMIshinonome.jpg",
    "INFOGRAPH_CHARACTER_SIZE": "260",
    "INFOGRAPH_CHARACTER_STRIP_BG": "1",
    "INFOGRAPH_TITLE_SPLIT": "プロジェクト",
    "POSTED_RECORD_FILE": ".last_posted_cnp.json",
}


def _apply_cnp_env(env: dict) -> dict:
    """
    CNP用の実行に切り替える。

    cli_post_infograph は DISCORD_WEBHOOK_URL で**始まる**環境変数を
    全部投稿先として拾うため、オロチ側のWebhookを必ず無効化すること。
    残すとCNPの画像がオロチのチャンネルにも飛ぶ。

    ⚠️ del ではなく空文字を入れる。cli側は起動時に load_dotenv() を呼ぶので、
    消しただけだと .env から読み直されて復活する（load_dotenv は既存の変数は
    上書きしないが、無い変数は入れてしまう）。空文字なら「既存」扱いで上書きされず、
    かつ cli 側の `if value and value.strip()` で投稿先から外れる。
    """
    for key in list(env):
        if key.startswith("DISCORD_WEBHOOK_URL") or key == "DISCORD_WEBHOOK":
            env[key] = ""
    env["DISCORD_TARGET_CHANNEL_IDS"] = ""
    env["DISCORD_WEBHOOK_URL"] = os.getenv("CNP_DISCORD_WEBHOOK_URL", "")
    env["DISCORD_CHANNEL_ID"] = os.getenv("CNP_DISCORD_CHANNEL_ID", "")
    env.update(CNP_THEME)
    return env


def run_cli_script(log_path: str, trigger_source: str = "scheduled task", weekly: bool = False,
                   community: str | None = None):
    """Wrapper function to run the CLI logic via subprocess to avoid macOS deadlocks."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(project_root, "bot", "cli_post_infograph.py")
    python_executable = os.path.join(project_root, ".venv", "bin", "python")
    env = _make_subprocess_env(python_executable)
    if community == "cnp":
        env = _apply_cnp_env(env)
    command = [python_executable, script_path] + (["--weekly"] if weekly else [])

    with open(log_path, "a") as log_file:
        log_file.write(f"--- Triggered by {trigger_source} at {datetime.datetime.now()} ---\n")
        log_file.flush()
        
        try:
            result = subprocess.run(
                command,
                cwd=project_root,
                stdout=log_file,
                stderr=log_file,
                text=True,
                env=env,
                check=False
            )
            log_file.write(f"--- CLI script finished with exit code {result.returncode} at {datetime.datetime.now()} ---\n")
            exit_code = result.returncode
        except Exception as e:
            import traceback
            log_file.write(f"--- CLI script failed: {e} at {datetime.datetime.now()} ---\n")
            traceback.print_exc(file=log_file)
            exit_code = 1
        finally:
            log_file.flush()
            
        return exit_code

@client.tree.command()
async def graph(interaction: discord.Interaction):
    """インフォグラフィックを生成して投稿します。"""
    try:
        # Defer the response immediately with a small timeout buffer
        await interaction.response.defer(ephemeral=True)
    except discord.errors.NotFound:
        print("[ERROR] Interaction expired before defer - likely timeout from slow import")
        return
    except Exception as e:
        print(f"[ERROR] Failed to defer interaction: {e}")
        try:
            await interaction.followup.send(f"エラーが発生しました: {str(e)}", ephemeral=True)
        except:
            pass
        return

    log_file_path = os.path.join(os.path.dirname(__file__), "..", "cron.log")

    try:
        loop = asyncio.get_running_loop()
        
        blocking_task = functools.partial(run_cli_script, log_file_path, "slash command")
        
        # Run the blocking subprocess in a separate thread with timeout
        exit_code = await asyncio.wait_for(
            loop.run_in_executor(None, blocking_task),
            timeout=60.0  # 60 second timeout for the CLI script
        )

        if exit_code == 0:
            # The webhook should have posted the image.
            await interaction.followup.send("インフォグラフィックを投稿しました！")
        else:
            error_message = f"インフォグラフィックの生成に失敗しました。ログを確認してください。:disappointed_relieved:"
            await interaction.followup.send(error_message)

    except asyncio.TimeoutError:
        error_message = "処理がタイムアウトしました。ログを確認してください。"
        try:
            await interaction.followup.send(error_message)
        except:
            print(f"[ERROR] Could not send timeout message: interaction may have expired")
        
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Timeout in graph command ---\n")

    except Exception as e:
        error_message = f"予期せぬエラーが発生しました。:pleading_face:\n```{str(e)[:100]}```"
        # Log the exception to the file as well
        with open(log_file_path, "a") as log_file:
            log_file.write(f"--- Exception in graph command: {e} ---\n")
        
        try:
            await interaction.followup.send(error_message)
        except:
            print(f"[ERROR] Could not send error message: {str(e)}")

# Botを起動
if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        print(f"[INFO] Starting bot with token: {DISCORD_BOT_TOKEN[:20]}...")
        try:
            print(f"[INFO] Attempting to connect to Discord...")
            client.run(DISCORD_BOT_TOKEN)
        except Exception as exc:
            now = datetime.datetime.now(JST)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Bot terminated unexpectedly: {exc}")
    else:
        print("エラー: DISCORD_BOT_TOKENが設定されていません。")
