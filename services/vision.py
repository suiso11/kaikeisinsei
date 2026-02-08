"""
Google Cloud Vision API を使ったレシートOCR解析サービス
"""
import re
import logging
from google.cloud import vision
from services.google_auth import get_credentials

logger = logging.getLogger(__name__)


class VisionService:
    """Google Vision API でレシート画像からテキストを抽出・解析する"""

    def __init__(self):
        credentials = get_credentials()
        self.client = vision.ImageAnnotatorClient(credentials=credentials)

    def analyze_receipt(self, image_bytes: bytes) -> tuple[str, dict]:
        """
        レシート画像を解析し、OCRテキストと構造化データを返す

        Returns:
            (raw_text, parsed_data) のタプル
            parsed_data = {
                'date': '2026/02/08',
                'amount': '1500',
                'purpose': '店名/用途',
            }
        """
        image = vision.Image(content=image_bytes)
        response = self.client.text_detection(image=image)

        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")

        annotations = response.text_annotations
        if not annotations:
            logger.warning("OCRテキストが検出されませんでした")
            return "", {}

        raw_text = annotations[0].description
        logger.info(f"OCR結果 ({len(raw_text)}文字): {raw_text[:200]}...")

        parsed = self._parse_receipt_text(raw_text)
        return raw_text, parsed

    def _parse_receipt_text(self, text: str) -> dict:
        """OCRテキストからレシート情報を抽出する"""
        result = {"date": "", "amount": "", "purpose": ""}

        # ===== 日付の検出 =====
        result["date"] = self._extract_date(text)

        # ===== 金額の検出（合計額を優先） =====
        result["amount"] = self._extract_amount(text)

        # ===== 店名/用途の検出（先頭行） =====
        result["purpose"] = self._extract_purpose(text)

        return result

    def _extract_date(self, text: str) -> str:
        """テキストから日付を抽出する"""
        # 西暦パターン: 2026/02/08, 2026-02-08, 2026年2月8日
        western_patterns = [
            r"(\d{4})\s*[/\-\.年]\s*(\d{1,2})\s*[/\-\.月]\s*(\d{1,2})\s*日?",
        ]
        for pattern in western_patterns:
            match = re.search(pattern, text)
            if match:
                y, m, d = match.groups()
                year = int(y)
                if 2000 <= year <= 2100:
                    return f"{year}/{int(m):02d}/{int(d):02d}"

        # 令和パターン: 令和8年2月8日, R8.2.8, R8/2/8
        reiwa_patterns = [
            r"令和\s*(\d{1,2})\s*[/\-\.年]\s*(\d{1,2})\s*[/\-\.月]\s*(\d{1,2})\s*日?",
            r"[RＲ]\s*(\d{1,2})\s*[/\-\.年]\s*(\d{1,2})\s*[/\-\.月]\s*(\d{1,2})\s*日?",
        ]
        for pattern in reiwa_patterns:
            match = re.search(pattern, text)
            if match:
                reiwa_year, m, d = match.groups()
                year = 2018 + int(reiwa_year)
                return f"{year}/{int(m):02d}/{int(d):02d}"

        # 年なしパターン: 2/8, 02/08（当年と仮定）
        short_pattern = r"(\d{1,2})\s*[/\-月]\s*(\d{1,2})\s*日?"
        match = re.search(short_pattern, text)
        if match:
            m, d = match.groups()
            m_int, d_int = int(m), int(d)
            if 1 <= m_int <= 12 and 1 <= d_int <= 31:
                from datetime import datetime
                year = datetime.now().year
                return f"{year}/{m_int:02d}/{d_int:02d}"

        return ""

    def _extract_amount(self, text: str) -> str:
        """テキストから合計金額を抽出する（お預かり・お釣りを除外）"""
        lines = text.split("\n")

        # 除外すべきキーワード（お預かり、お釣り、釣銭など）
        exclude_keywords = [
            "お預", "預り", "あずかり", "お釣", "釣銭", "つり",
            "釣り", "現金", "クレジット", "カード", "CASH", "CHANGE",
            "No.", "NO.", "no.", "登録", "電話", "POS", "レジ",
            "担当", "番号",
        ]

        def is_excluded_line(line: str) -> bool:
            return any(kw in line for kw in exclude_keywords)

        # 1. 「合計」「税込」等の明確な合計パターンを最優先
        total_keywords = r"(?:合計|お買[い上]|総[額計]|税込合計|税込|TOTAL|Total|total)"
        total_patterns = [
            total_keywords + r"\s*[(:：]?\s*[¥￥]?\s*([\d,]+)\s*円?",
            r"[¥￥]\s*([\d,]+)\s*" + total_keywords,
        ]
        for line in lines:
            if is_excluded_line(line):
                continue
            for pattern in total_patterns:
                match = re.search(pattern, line)
                if match:
                    try:
                        val = int(match.group(1).replace(",", ""))
                        if val > 0:
                            logger.info(f"金額検出（合計パターン）: {val} from '{line.strip()}'")
                            return str(val)
                    except ValueError:
                        continue

        # 2. 「小計」を探す（除外行でないもの）
        for line in lines:
            if is_excluded_line(line):
                continue
            match = re.search(r"小計\s*[(:：]?\s*[¥￥]?\s*([\d,]+)", line)
            if match:
                try:
                    val = int(match.group(1).replace(",", ""))
                    if val > 0:
                        logger.info(f"金額検出（小計）: {val} from '{line.strip()}'")
                        return str(val)
                except ValueError:
                    continue

        # 3. 「円」が付いた金額（除外行でないもの）を収集し、
        #    「お買上」「合計」に近い位置のものを優先、なければ最大値
        yen_amounts = []
        for line in lines:
            if is_excluded_line(line):
                continue
            for m in re.findall(r"([\d,]+)\s*円", line):
                try:
                    val = int(m.replace(",", ""))
                    if val > 0:
                        yen_amounts.append(val)
                except ValueError:
                    continue
        if yen_amounts:
            logger.info(f"金額検出（円パターン）: {max(yen_amounts)} from {yen_amounts}")
            return str(max(yen_amounts))

        # 4. ¥記号付き金額（除外行でないもの）から最大値
        yen_symbol_amounts = []
        for line in lines:
            if is_excluded_line(line):
                continue
            for m in re.findall(r"[¥￥]\s*([\d,]+)", line):
                try:
                    val = int(m.replace(",", ""))
                    if val > 0:
                        yen_symbol_amounts.append(val)
                except ValueError:
                    continue
        if yen_symbol_amounts:
            logger.info(f"金額検出（¥パターン）: {max(yen_symbol_amounts)} from {yen_symbol_amounts}")
            return str(max(yen_symbol_amounts))

        return ""

    def _extract_purpose(self, text: str) -> str:
        """テキストの先頭行から店名/用途を抽出する"""
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if not lines:
            return ""

        # 先頭数行から店名らしきものを探す（短すぎる行や数字のみの行はスキップ）
        for line in lines[:5]:
            # 数字/記号のみの行はスキップ
            cleaned = re.sub(r"[\d\s\-/\.,:;=\*#\+¥￥円]", "", line)
            if len(cleaned) >= 2:
                return line[:50]

        return lines[0][:50] if lines else ""
