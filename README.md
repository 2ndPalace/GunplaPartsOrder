# ガンプラ説明書パーツ番号抽出・部品注文自動化プロジェクト

ガンプラ（バンダイのプラモデル）の組立説明書をスマートフォン等で撮影した写真から、Gemini API（`gemini-2.5-flash`）を活用してパーツ番号（ランナー記号＋パーツ番号）を高精度に抽出し、バンダイ公式部品通販サイトへの注文入力を半自動化するプロジェクトです。

---

## 主な機能（フェーズ1）

1. **Gemini 2.5 Flash による高精度なパーツ番号抽出**
   - 新公式SDK `google-genai` を採用。
   - スマホ撮影による画像の傾き・90度/180度回転・影・照明ムラに耐性を持つ画像前処理（EXIF Orientation補正）と最適化プロンプト。
   - ガンプラ説明書特有の「四角枠のランナー記号（A, B1, E1, H1, PC等）＋パーツ番号（数字）」のみを厳密に抽出。
   - シール番号（ホイルシール、マーキングシール等）や組み立て手順番号（黒いひし形1、2等）、周辺テキストは確実に除外。

2. **Pydantic による構造化出力（Structured Outputs）と検証**
   - 型安全なレスポンス検証。
   - 全角英数→半角変換、大文字化、不要な記号の自動サニタイズ。

3. **重複排除（ユニーク化）と自然順ソート**
   - 同一パーツの重複を排除。
   - ランナー記号順（A → B → B1 → B2 → C...）およびパーツ番号順（1 → 2 → 6 → 14 → 26...）に自然順ソート。
   - 必要に応じて数量合算（`--sum-quantities`）にも対応。

4. **指定仕様に準拠したJSONファイルおよびコンソールテーブル出力**
   - フォーマット例:
     ```json
     {
       "parts": [
         {"runner": "A", "number": "6", "quantity": 1},
         {"runner": "A", "number": "26", "quantity": 1},
         {"runner": "B1", "number": "12", "quantity": 1}
       ]
     }
     ```

---

## ディレクトリ構成

```
GunplaPartsOrder/
├── .env.example              # 環境変数設定サンプル
├── .gitignore                # Git除外設定
├── pyproject.toml            # プロジェクト設定およびpytest設定
├── requirements.txt          # 依存パッケージ定義
├── README.md                 # 本ドキュメント
├── main.py                   # CLIエントリーポイント
├── src/
│   ├── __init__.py
│   ├── config.py             # 設定・APIキー管理
│   ├── models.py             # Pydanticデータモデル・ソート・重複排除ロジック
│   ├── image_utils.py        # EXIF回転補正・画像前処理
│   ├── extractor.py          # Gemini API抽出エンジン・プロンプト定義
│   └── order_automation/     # 【フェーズ2用】Playwrightブラウザ自動化モジュール
│       └── __init__.py
├── tests/
│   ├── test_models.py        # モデル・ソート・正規化テスト
│   ├── test_image_utils.py   # 画像前処理テスト
│   └── test_extractor.py     # Gemini API抽出モックテスト
└── data/
    ├── sample_images/        # 説明書写真の配置ディレクトリ
    └── output/               # 抽出結果JSONファイルの保存先
```

---

## セットアップ手順

### 1. 依存ライブラリのインストール
Python 3.10以上がインストールされた環境で以下を実行します：

```bash
pip install -r requirements.txt
```

Playwrightブラウザの準備（フェーズ2用）:
```bash
playwright install
```

### 2. Gemini APIキーの設定
プロジェクトルートに `.env` ファイルを作成し、Gemini APIキーを設定します：

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

※ `.env.example` をコピーして作成することも可能です。

---

## 使い方

### 1. 説明書画像からパーツを抽出してJSON出力
スマートフォン等で撮影した説明書画像を指定して実行します：

```bash
python main.py path/to/instruction.jpg
```

出力先はデフォルトで `data/output/<画像ファイル名>_parts.json` に保存されます。

### 2. 出力先JSONパスを指定する場合
```bash
python main.py path/to/instruction.jpg -o data/output/my_order.json
```

### 3. 同一パーツが複数回登場したときに数量を合算したい場合
```bash
python main.py path/to/instruction.jpg --sum-quantities
```

### 4. モックモード（APIキー不要の動作テスト）
Gemini APIを呼び出さずに全体の動作と出力を確認したい場合：
```bash
python main.py dummy.jpg --mock
```

---

## テストの実行

全ユニットテスト（Pydanticバリデーション、自然順ソート、重複排除、画像回転補正、Gemini抽出フロー）を実行します：

```bash
pytest -v
```

---

## フェーズ2（今後の予定）

抽出された `parts.json` を入力として、`playwright` を用いた「BANDAI SPIRITS 部品通販」サイトへの半自動入力機能を `src/order_automation/` に実装予定です。
