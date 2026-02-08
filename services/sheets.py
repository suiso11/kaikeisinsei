"""
Google Sheets サービス - Sheets API v4 を直接使用してスプレッドシートへ書き込む
（アップロードされた .xlsx ファイルにも対応）
"""
import logging
from googleapiclient.discovery import build
from services.google_auth import get_credentials
import config

logger = logging.getLogger(__name__)


class SheetsService:
    """Google Sheets API v4 で直接スプレッドシートを操作する"""

    # スプレッドシートの列順序（0-indexed）
    COLUMNS = [
        "入力日",         # A: 0
        "日付（支払日）",  # B: 1
        "記入者",         # C: 2
        "勘定科目",       # D: 3
        "立て替えた人",    # E: 4
        "使用用途",       # F: 5
        "入金",           # G: 6
        "出金",           # H: 7
        "差引残高",       # I: 8
        "会計Check",      # J: 9
        "精算",           # K: 10
    ]

    def __init__(self):
        credentials = get_credentials()
        self.service = build("sheets", "v4", credentials=credentials)
        self.spreadsheet_id = config.SPREADSHEET_ID
        self.sheet_name = getattr(config, "SHEET_NAME", "")
        # シート名が設定で指定されていなければ自動検出を試みる
        if not self.sheet_name:
            self.sheet_name = self._resolve_sheet_name(config.SHEET_GID)
        logger.info(
            f"スプレッドシート接続完了: ID={self.spreadsheet_id} "
            f"シート: '{self.sheet_name}'"
        )

    def _resolve_sheet_name(self, gid: int) -> str:
        """GID からシート名を取得する。取得できなければデフォルト名を返す"""
        try:
            meta = (
                self.service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
            for sheet in meta.get("sheets", []):
                props = sheet.get("properties", {})
                if props.get("sheetId") == gid:
                    name = props.get("title", "Sheet1")
                    logger.info(f"GID {gid} → シート名: '{name}'")
                    return name
            first = meta["sheets"][0]["properties"]["title"]
            logger.warning(f"GID {gid} が見つかりません。最初のシート '{first}' を使用")
            return first
        except Exception as e:
            logger.warning(
                f"シート名の自動取得に失敗 ({e})。"
                "SHEET_NAME を .env に設定するか、シート名なしで続行します"
            )
            return ""

    def _make_range(self, col_range: str = "") -> str:
        """シート名付きのレンジ文字列を生成する"""
        if self.sheet_name:
            base = f"'{self.sheet_name}'"
        else:
            base = "Sheet1"  # デフォルト
        if col_range:
            return f"{base}!{col_range}"
        return base

    def _get_all_values(self) -> list[list[str]]:
        """シートの全データを取得する"""
        range_str = self._make_range()
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=range_str)
            .execute()
        )
        return result.get("values", [])

    def get_last_balance(self) -> int:
        """最後の行の差引残高を取得する"""
        try:
            all_values = self._get_all_values()
            if len(all_values) <= 1:  # ヘッダーのみ
                return 0

            # 最後の行から差引残高を取得（I列 = index 8）
            for row in reversed(all_values[1:]):
                if len(row) > 8 and row[8].strip():
                    balance_str = row[8].strip()
                    # カンマ、¥記号を除去して数値化
                    balance_str = (
                        balance_str.replace(",", "")
                        .replace("¥", "")
                        .replace("￥", "")
                        .replace(" ", "")
                    )
                    try:
                        return int(float(balance_str))
                    except ValueError:
                        continue
            return 0
        except Exception as e:
            logger.error(f"差引残高の取得に失敗: {e}")
            return 0

    def append_row(self, data: dict) -> None:
        """
        会計データをスプレッドシートに1行追加する
        """
        income = int(data.get("入金", 0))
        expense = int(data.get("出金", 0))

        # 差引残高を計算
        last_balance = self.get_last_balance()
        new_balance = last_balance + income - expense

        row = [
            data.get("入力日", ""),
            data.get("日付", ""),
            data.get("記入者", ""),
            data.get("勘定科目", ""),
            data.get("立て替えた人", ""),
            data.get("使用用途", ""),
            income if income else "",
            expense if expense else "",
            new_balance,
            data.get("会計Check", ""),
            data.get("精算", ""),
        ]

        range_str = self._make_range("A:K")
        body = {"values": [row]}

        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_str,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        logger.info(
            f"行を追加: 日付={data.get('日付')} "
            f"出金={expense} 差引残高={new_balance}"
        )
