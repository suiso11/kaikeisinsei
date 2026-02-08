"""
Google 認証ヘルパー - サービスアカウント認証を一元管理
"""
from google.oauth2.service_account import Credentials
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/cloud-vision",
]


def get_credentials() -> Credentials:
    """サービスアカウントの認証情報を取得する"""
    return Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
    )
