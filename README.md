# Discord 会計申請ボット

`#会計申請` チャンネルに送信されたレシート画像を Google Vision API で OCR 解析し、Google スプレッドシートに自動保存する Discord ボットです。

## 機能

- **レシート画像の自動OCR解析** — `#会計申請` チャンネルに画像を投稿すると、日付・金額・店名を自動検出
- **フォーム入力** — OCR結果をプレフィルしたモーダルフォームで確認・修正
- **スラッシュコマンド** — `/申請` で画像なしの手動入力も可能
- **Google Sheets 自動保存** — 差引残高の自動計算付き
- **Google Drive 画像保存** — レシート画像を Drive に自動アップロード（任意）

## セットアップ手順

### 1. Discord ボットの作成

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 「New Application」で新しいアプリケーションを作成
3. 左メニュー「Bot」→「Add Bot」
4. **TOKEN** をコピー（後で `.env` に設定）
5. 「Privileged Gateway Intents」で以下を有効化:
   - **MESSAGE CONTENT INTENT** ✅
   - **SERVER MEMBERS INTENT** ✅ (任意)
6. 左メニュー「OAuth2」→「URL Generator」:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Read Messages/View Channels`, `Embed Links`, `Attach Files`, `Read Message History`
7. 生成された URL でボットをサーバーに招待

### 2. Google Cloud の設定

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. 以下の API を有効化:
   - **Cloud Vision API**
   - **Google Sheets API**
   - **Google Drive API**
3. 「IAM と管理」→「サービスアカウント」→ 新規作成
4. サービスアカウントのキー（JSON）をダウンロード
5. ダウンロードした JSON を `credentials.json` としてプロジェクトルートに配置

### 3. Google スプレッドシートの共有

1. 対象のスプレッドシートを開く
2. 右上「共有」→ サービスアカウントのメールアドレス（`xxx@xxx.iam.gserviceaccount.com`）を追加
3. **編集者** 権限を付与

### 4. Google Drive フォルダの共有（任意）

レシート画像を Drive に保存する場合:

1. Drive でレシート保存用フォルダを作成
2. フォルダを右クリック →「共有」→ サービスアカウントのメールアドレスを追加（編集者権限）
3. フォルダの URL から ID を取得: `https://drive.google.com/drive/folders/【ここがフォルダID】`

### 5. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集:

```env
DISCORD_TOKEN=あなたのDiscordボットトークン
CHANNEL_NAME=会計申請
GOOGLE_CREDENTIALS_FILE=credentials.json
SPREADSHEET_ID=1qqx_-yu8T_ZuUZMvMmKPoVUXh3qcAwS1
SHEET_GID=1771030374
DRIVE_FOLDER_ID=（DriveフォルダID。空欄の場合画像アップロードは無効）
```

### 6. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 7. ボットの起動

```bash
python bot.py
```

## 使い方

### 方法1: レシート画像を送信

1. Discord の `#会計申請` チャンネルにレシート画像を送信
2. ボットが自動でOCR解析し、結果を表示
3. 「📝 申請フォームを開く」ボタンをクリック
4. フォームに入力（OCR結果がプレフィル済み）して送信
5. スプレッドシートに自動保存

### 方法2: `/申請` コマンド

1. `/申請` と入力してスラッシュコマンドを実行
2. フォームに手動で入力して送信
3. スプレッドシートに自動保存

### `/会計ヘルプ` コマンド

ボットの使い方を表示します。

## スプレッドシートの列構成

| 列 | 内容 | 入力方法 |
|---|---|---|
| A: 入力日 | フォーム送信日 | 自動 |
| B: 日付（支払日） | 支払った日付 | フォーム入力 |
| C: 記入者 | Discordユーザー名 | 自動 |
| D: 勘定科目 | 科目 | フォーム入力 |
| E: 立て替えた人 | 支払った人 | フォーム入力 |
| F: 使用用途 | 用途詳細 | フォーム入力 |
| G: 入金 | 入金額 | 初期値0 |
| H: 出金 | 出金額 | フォーム入力 |
| I: 差引残高 | 残高 | 自動計算 |
| J: 会計Check | チェック | 空欄 |
| K: 精算 | 精算状況 | 空欄 |

## プロジェクト構成

```
discord-accounting-bot/
├── bot.py                  # エントリーポイント
├── config.py               # 環境変数の読み込み
├── .env                    # 環境設定（git管理外）
├── .env.example            # 環境設定テンプレート
├── credentials.json        # Googleサービスアカウント認証（git管理外）
├── requirements.txt        # Python依存パッケージ
├── README.md               # このファイル
├── cogs/
│   ├── __init__.py
│   └── accounting.py       # 会計申請Cog（UI・ロジック）
└── services/
    ├── __init__.py
    ├── google_auth.py      # Google認証ヘルパー
    ├── sheets.py           # Google Sheets操作
    ├── vision.py           # Google Vision OCR
    └── drive.py            # Google Drive画像アップロード
```

## 注意事項

- `credentials.json` と `.env` はGitにコミットしないでください
- サービスアカウントにスプレッドシートの編集権限が必要です
- Google Vision API の利用には料金が発生する場合があります（月1,000リクエストまで無料）
- Discord の Message Content Intent を有効にする必要があります
