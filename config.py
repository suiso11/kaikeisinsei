"""
設定ファイル - 環境変数から設定を読み込む
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ===== Discord =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "会計申請")

# ===== Google Cloud =====
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# ===== Google Spreadsheet =====
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_GID = int(os.getenv("SHEET_GID", "0"))
SHEET_NAME = os.getenv("SHEET_NAME", "")  # シート名を直接指定（xlsx対応用）

# ===== Google Drive =====
# レシート画像を保存するGoogle DriveフォルダのID（空の場合はアップロードしない）
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")
