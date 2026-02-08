"""
Google Drive サービス - レシート画像のアップロード
"""
import logging
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from services.google_auth import get_credentials
import config

logger = logging.getLogger(__name__)


class DriveService:
    """Google Drive にレシート画像をアップロードする"""

    def __init__(self):
        self.enabled = bool(config.DRIVE_FOLDER_ID)
        if self.enabled:
            credentials = get_credentials()
            self.service = build("drive", "v3", credentials=credentials)
            logger.info(f"Google Drive 接続完了 (フォルダID: {config.DRIVE_FOLDER_ID})")
        else:
            self.service = None
            logger.info("DRIVE_FOLDER_ID 未設定のため、画像アップロードは無効です")

    def upload_image(
        self,
        image_bytes: bytes,
        filename: str | None = None,
        mimetype: str = "image/png",
    ) -> str:
        """
        画像を Google Drive にアップロードし、共有リンクを返す

        Returns:
            共有リンクURL（アップロード無効の場合は空文字列）
        """
        if not self.enabled:
            return ""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"receipt_{timestamp}.png"

        file_metadata = {
            "name": filename,
            "parents": [config.DRIVE_FOLDER_ID],
        }

        media = MediaInMemoryUpload(image_bytes, mimetype=mimetype)

        try:
            file = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink",
                )
                .execute()
            )

            web_link = file.get("webViewLink", "")
            logger.info(f"画像アップロード完了: {filename} -> {web_link}")
            return web_link

        except Exception as e:
            logger.error(f"画像アップロード失敗: {e}")
            raise
