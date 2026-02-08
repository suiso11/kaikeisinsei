"""
Discord 会計申請ボット - メインエントリーポイント
"""
import discord
from discord.ext import commands
import config
import logging

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("accounting-bot")

# Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"ログイン完了: {bot.user} (ID: {bot.user.id})")
    try:
        await bot.load_extension("cogs.accounting")
        synced = await bot.tree.sync()
        logger.info(f"スラッシュコマンド同期完了: {len(synced)}個")
    except Exception as e:
        logger.error(f"初期化エラー: {e}", exc_info=True)


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN が設定されていません。.env ファイルを確認してください。")
        exit(1)
    bot.run(config.DISCORD_TOKEN)
