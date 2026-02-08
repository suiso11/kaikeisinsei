"""
会計申請 Cog - Discord UI（モーダルフォーム、ボタン、メッセージ監視）
"""
import uuid
import logging
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

from services.vision import VisionService
from services.sheets import SheetsService
from services.drive import DriveService
import config

logger = logging.getLogger(__name__)


# =============================================================================
#  モーダルフォーム（会計申請入力画面）
# =============================================================================
class AccountingModal(discord.ui.Modal, title="会計申請フォーム"):
    """会計データを入力するモーダルフォーム（最大5フィールド）"""

    date_input = discord.ui.TextInput(
        label="日付（支払日）",
        placeholder="例: 2026/02/08",
        required=True,
        max_length=20,
        style=discord.TextStyle.short,
    )
    category_input = discord.ui.TextInput(
        label="勘定科目",
        placeholder="例: 消耗品費、交通費、会議費、通信費",
        required=True,
        max_length=50,
        style=discord.TextStyle.short,
    )
    payer_input = discord.ui.TextInput(
        label="立て替えた人",
        placeholder="名前を入力",
        required=True,
        max_length=50,
        style=discord.TextStyle.short,
    )
    purpose_input = discord.ui.TextInput(
        label="使用用途",
        placeholder="例: ○○の購入、会議室利用料",
        required=True,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )
    amount_input = discord.ui.TextInput(
        label="出金額（円）",
        placeholder="例: 1500",
        required=True,
        max_length=20,
        style=discord.TextStyle.short,
    )

    def __init__(self, cog: "AccountingCog", submission_id: str, defaults: dict | None = None):
        super().__init__()
        self.cog = cog
        self.submission_id = submission_id

        # OCR結果やデフォルト値をプレフィル
        if defaults:
            if defaults.get("date"):
                self.date_input.default = defaults["date"]
            if defaults.get("category"):
                self.category_input.default = defaults["category"]
            if defaults.get("payer"):
                self.payer_input.default = defaults["payer"]
            if defaults.get("purpose"):
                self.purpose_input.default = defaults["purpose"]
            if defaults.get("amount"):
                self.amount_input.default = defaults["amount"]

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pending = self.cog.pending.pop(self.submission_id, {})

        # --- 金額のバリデーション ---
        amount_str = (
            self.amount_input.value
            .replace(",", "").replace("¥", "").replace("￥", "")
            .replace(" ", "").replace("　", "")
        )
        try:
            amount = int(amount_str)
        except ValueError:
            await interaction.followup.send(
                "❌ 金額が正しくありません。半角数字を入力してください。",
                ephemeral=True,
            )
            return

        # --- レシート画像を Google Drive にアップロード ---
        drive_link = ""
        if pending.get("image_bytes"):
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"receipt_{timestamp}_{interaction.user.name}.png"
                drive_link = self.cog.drive_service.upload_image(
                    pending["image_bytes"], filename
                )
            except Exception as e:
                logger.error(f"Drive アップロード失敗: {e}")

        # --- スプレッドシートに書き込み ---
        today = datetime.now().strftime("%Y/%m/%d")
        author = pending.get("author", interaction.user.display_name)

        row_data = {
            "入力日": today,
            "日付": self.date_input.value,
            "記入者": author,
            "勘定科目": self.category_input.value,
            "立て替えた人": self.payer_input.value,
            "使用用途": self.purpose_input.value,
            "入金": 0,
            "出金": amount,
            "会計Check": "",
            "精算": "",
        }

        try:
            self.cog.sheets_service.append_row(row_data)
        except Exception as e:
            logger.error(f"スプレッドシート書き込み失敗: {e}")
            await interaction.followup.send(
                f"❌ スプレッドシートへの保存に失敗しました。\n```{e}```",
                ephemeral=True,
            )
            return

        # --- 成功メッセージ ---
        embed = discord.Embed(
            title="✅ 会計申請が完了しました",
            color=discord.Color.green(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="日付（支払日）", value=self.date_input.value, inline=True)
        embed.add_field(name="勘定科目", value=self.category_input.value, inline=True)
        embed.add_field(name="立て替えた人", value=self.payer_input.value, inline=True)
        embed.add_field(name="使用用途", value=self.purpose_input.value, inline=False)
        embed.add_field(name="出金額", value=f"¥{amount:,}", inline=True)
        embed.add_field(name="記入者", value=author, inline=True)
        if drive_link:
            embed.add_field(
                name="レシート画像",
                value=f"[Google Driveで表示]({drive_link})",
                inline=False,
            )
        embed.set_footer(text="スプレッドシートに保存済み")

        await interaction.followup.send(embed=embed)
        logger.info(f"会計申請完了: {author} ¥{amount:,} ({self.purpose_input.value})")

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"モーダルエラー: {error}", exc_info=True)
        try:
            await interaction.followup.send(
                "❌ エラーが発生しました。もう一度お試しください。",
                ephemeral=True,
            )
        except Exception:
            pass


# =============================================================================
#  確認ボタンビュー（レシート解析後に表示）
# =============================================================================
class ConfirmView(discord.ui.View):
    """レシートOCR後に「申請フォームを開く」ボタンを表示するビュー"""

    def __init__(self, cog: "AccountingCog", submission_id: str):
        super().__init__(timeout=600)  # 10分でタイムアウト
        self.cog = cog
        self.submission_id = submission_id

    @discord.ui.button(
        label="📝 申請フォームを開く",
        style=discord.ButtonStyle.primary,
    )
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.cog.pending.get(self.submission_id)
        if not data:
            await interaction.response.send_message(
                "⏰ タイムアウトしました。もう一度レシート画像を送信してください。",
                ephemeral=True,
            )
            return

        # OCR結果をデフォルト値としてモーダルに渡す
        defaults = dict(data.get("ocr_data", {}))
        defaults["payer"] = interaction.user.display_name

        modal = AccountingModal(self.cog, self.submission_id, defaults)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="❌ キャンセル",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.pending.pop(self.submission_id, None)
        await interaction.response.edit_message(
            content="🚫 申請がキャンセルされました。",
            embed=None,
            view=None,
        )
        self.stop()

    async def on_timeout(self):
        self.cog.pending.pop(self.submission_id, None)


# =============================================================================
#  メインCog
# =============================================================================
class AccountingCog(commands.Cog, name="会計申請"):
    """#会計申請 チャンネルのメッセージ監視とスラッシュコマンドを提供する"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending: dict[str, dict] = {}  # submission_id -> 申請データ

        # Google サービス初期化
        try:
            self.vision_service = VisionService()
            logger.info("Vision API 初期化完了")
        except Exception as e:
            logger.error(f"Vision API 初期化失敗: {e}")
            self.vision_service = None

        try:
            self.sheets_service = SheetsService()
            logger.info("Sheets API 初期化完了")
        except Exception as e:
            logger.error(f"Sheets API 初期化失敗: {e}")
            self.sheets_service = None

        try:
            self.drive_service = DriveService()
            logger.info("Drive API 初期化完了")
        except Exception as e:
            logger.error(f"Drive API 初期化失敗: {e}")
            self.drive_service = None

    # -----------------------------------------------------------------
    #  メッセージ監視: #会計申請 チャンネルに画像が投稿されたら自動でOCR
    # -----------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot自身のメッセージは無視
        if message.author.bot:
            return

        # 対象チャンネルかチェック
        if not hasattr(message.channel, "name"):
            return
        if message.channel.name != config.CHANNEL_NAME:
            return

        # 画像添付があるかチェック
        image_attachments = [
            a
            for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]
        if not image_attachments:
            return

        attachment = image_attachments[0]
        logger.info(
            f"画像検出: {attachment.filename} "
            f"({attachment.size} bytes) from {message.author}"
        )

        # 処理中メッセージ
        processing_msg = await message.reply("📷 レシートを検出しました。解析中...")

        # --- 画像ダウンロード ---
        try:
            image_bytes = await attachment.read()
        except Exception as e:
            await processing_msg.edit(content=f"❌ 画像のダウンロードに失敗しました: {e}")
            return

        # --- Vision API で OCR ---
        ocr_text = ""
        ocr_data = {}
        if self.vision_service:
            try:
                ocr_text, ocr_data = self.vision_service.analyze_receipt(image_bytes)
            except Exception as e:
                logger.error(f"OCR失敗: {e}")
                ocr_text = ""
                ocr_data = {}

        # --- 保留データを保存 ---
        submission_id = str(uuid.uuid4())
        self.pending[submission_id] = {
            "image_bytes": image_bytes,
            "ocr_data": ocr_data,
            "ocr_text": ocr_text,
            "attachment_url": attachment.url,
            "author": message.author.display_name,
        }

        # --- 解析結果の Embed 表示 ---
        embed = discord.Embed(
            title="📄 レシート解析結果",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        if ocr_data.get("date"):
            embed.add_field(name="🗓 検出日付", value=ocr_data["date"], inline=True)
        if ocr_data.get("amount"):
            embed.add_field(name="💰 検出金額", value=f"¥{ocr_data['amount']}", inline=True)
        if ocr_data.get("purpose"):
            embed.add_field(
                name="🏪 検出店名/用途",
                value=ocr_data["purpose"][:100],
                inline=False,
            )

        if ocr_text:
            truncated = ocr_text[:400] + ("..." if len(ocr_text) > 400 else "")
            embed.add_field(
                name="📝 OCRテキスト",
                value=f"```\n{truncated}\n```",
                inline=False,
            )
        elif not self.vision_service:
            embed.add_field(
                name="⚠️ 注意",
                value="Vision APIが無効のため、OCR解析はスキップされました。",
                inline=False,
            )

        embed.set_thumbnail(url=attachment.url)
        embed.set_footer(text="下のボタンを押してフォームに入力してください")

        # --- ボタン付きメッセージ送信 ---
        view = ConfirmView(self, submission_id)
        await processing_msg.edit(content=None, embed=embed, view=view)

    # -----------------------------------------------------------------
    #  スラッシュコマンド: /申請 （画像なしで直接フォーム入力）
    # -----------------------------------------------------------------
    @app_commands.command(name="申請", description="会計申請フォームを開きます（画像なし）")
    async def submit_expense(self, interaction: discord.Interaction):
        if not self.sheets_service:
            await interaction.response.send_message(
                "❌ Google Sheets への接続が確立されていません。管理者に連絡してください。",
                ephemeral=True,
            )
            return

        submission_id = str(uuid.uuid4())
        self.pending[submission_id] = {
            "image_bytes": None,
            "ocr_data": {},
            "author": interaction.user.display_name,
        }

        defaults = {
            "payer": interaction.user.display_name,
            "date": datetime.now().strftime("%Y/%m/%d"),
        }
        modal = AccountingModal(self, submission_id, defaults)
        await interaction.response.send_modal(modal)

    # -----------------------------------------------------------------
    #  スラッシュコマンド: /会計ヘルプ
    # -----------------------------------------------------------------
    @app_commands.command(name="会計ヘルプ", description="会計申請ボットの使い方を表示します")
    async def show_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 会計申請ボットの使い方",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="方法1: レシート画像を送信",
            value=(
                f"**#{config.CHANNEL_NAME}** チャンネルにレシート画像を送信すると、\n"
                "自動でOCR解析し、申請フォームを表示します。\n"
                "フォームにはOCR結果がプレフィルされます。"
            ),
            inline=False,
        )
        embed.add_field(
            name="方法2: /申請 コマンド",
            value=(
                "`/申請` コマンドで直接入力フォームを開けます。\n"
                "画像なしで手動入力したい場合にご利用ください。"
            ),
            inline=False,
        )
        embed.add_field(
            name="入力項目",
            value=(
                "• **日付（支払日）** - 支払った日付\n"
                "• **勘定科目** - 消耗品費、交通費、会議費 等\n"
                "• **立て替えた人** - 支払った人の名前\n"
                "• **使用用途** - 何に使ったか\n"
                "• **出金額** - 金額（円）"
            ),
            inline=False,
        )
        embed.set_footer(text="データはGoogleスプレッドシートに自動保存されます")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AccountingCog(bot))
    logger.info("AccountingCog ロード完了")
