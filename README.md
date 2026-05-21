# Cosense Personal Agent MCP Server for LM Studio

Cosense (旧 Scrapbox) の知識ベースを LM Studio 上のローカル LLM から自在に検索・閲覧できるようにするための MCP (Model Context Protocol) サーバーです。
ローカルの Embedding モデルを活用した「意味・概念検索 (ベクトル検索)」と、Cosense 標準 API による「キーワード完全一致検索 (全文検索)」のハイブリッド検索に対応しています。

## 主な機能

*   **search_page (ベクトル検索)**: 曖昧な記憶や抽象的な概念から、関連するページを意味的に探索します。検索時に自動で Cosense 側との差分同期が走ります。
*   **search_page_fulltext (全文検索)**: 固有名詞やエラー文など、特定のキーワードが直接含まれるページを確実にヒットさせます。
*   **read_page_details (全文取得)**: 検索結果の `pageID` を指定することで、対象ページの本文全量を読み込み、LLM にコンテキストを渡します。

## 前提条件

*   Python 3.10 以上
*   LM Studio 内でEmbeddingモデル, Toolが使用できるモデルが同時に動かせる

## セットアップ手順

### 1. 環境構築 (venv)

プロジェクトのルートディレクトリで仮想環境を作成し、依存ライブラリをインストールします。

```bash
# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化 (Windows PowerShell)
.venv\Scripts\activate

# 仮想環境の有効化 (macOS / Linux)
source .venv/bin/activate

# ライブラリのインストール
pip install -r requirements.txt

```

### 2. 環境変数の設定 (`.env`)

`cosense_mcp.py` と同じフォルダに `.env` ファイルを作成し、各自の環境に合わせて書き換えてください。(.env.exampleを参考に作成してください)

```ini
# 対象にするCosenseのプロジェクト名 (URLの [https://scrapbox.io/XXXX/](https://scrapbox.io/XXXX/) の部分)
COSENSE_PROJECT_NAME=YourProjectName

# LM Studio の Embedding API エンドポイントと使用するモデル名
EMBEDDING_API_URL=http://localhost:1234/v1/embeddings
EMBEDDING_MODEL_NAME=
# 【任意】プライベート(非公開)プロジェクトの場合のみ設定
# ブラウザのデベロッパーツールからクッキーの 'connect.sid' の値をコピーして貼り付けてください
COSENSE_COOKIE_CONNECT_SID=

```

### 3. LM Studio への登録

1. LM Studio を起動し、右側サイドバーの **「Program」タブ** を開きます。
2. **「Install」＞「Edit mcp.json」** をクリックし、アプリ内エディタを開きます。
3. `mcpServers` オブジェクトの内部に、以下の設定を追記して保存します。

**Windows の場合:**

```json
{
  "mcpServers": {
    "cosense-agent-mcp": {
      "command": "C:\\Users\\あなたのユーザー名\\パス...\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\あなたのユーザー名\\パス...\\cosense_mcp.py"
      ]
    }
  }
}

```

**macOS / Linux の場合:**

```json
{
  "mcpServers": {
    "cosense-agent-mcp": {
      "command": "/path/to/project/.venv/bin/python",
      "args": [
        "/path/to/project/cosense_mcp.py"
      ]
    }
  }
}

```

### 4. おすすめのシステムプロンプト設定

ローカル LLM が自律的にツールを呼び出せるよう、LM Studio の **System Prompt** に以下の指示（英語）を設定することを推奨します。

```text
You are an agent designed to search and summarize the user's personal knowledge base (Cosense) utilizing cosense_mcp, which contains the user's notes and pages.

Whenever you lack context or information, you MUST proactively execute the available search tools (search_page or search_page_fulltext) to resolve the information gap yourself BEFORE asking the user for clarification.

**CRITICAL CONSTRAINTS FOR TOOL USAGE:**
1. NEVER output preliminary announcements, conversational filler, or progress updates (e.g., "I will search now," "Please wait a moment," "Let me look that up") before calling a tool.
2. You must immediately and silently execute the Function Call first.
3. Generate your natural language response ONLY AFTER you have received the execution results from the tool.

```

## ディレクトリ構造

```text
.
├── .env                  # 環境設定ファイル (各自書き換え)
├── cosense_mcp.py        # MCP サーバー本体コード
├── requirements.txt      # 依存ライブラリ一覧
├── database/             # ローカルのベクトルDB (自動生成されます)
└── README.md             # 本ドキュメント

```