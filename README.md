# ガンプラ部品注文アシスタント (GunplaPartsOrder)

ガンプラの組立説明書をスマートフォンで撮影した写真から、**パーツ番号（ランナー記号＋番号）を自動で読み取り**、BANDAI SPIRITS の部品注文サイトに入力するための一覧を作る Python ツールです。

- 説明書の写真を1枚渡すだけで、`A-6`、`B1-12` のような**パーツ番号の一覧**を作る
- 画像の読み取りには Google の **Gemini API（`gemini-2.5-flash`）** を使い、パーツ番号ではない数字（**シール番号**や**組み立て手順の番号**など）を除外する
- スマホ写真によくある **90度回転・傾き・影** があっても読み取れるようにする
- 同じパーツの**重複を自動で取り除き**、**ランナー記号順・番号順**に並べる
- 結果を**JSON ファイル**と**画面の表**の両方で出す（JSON はフェーズ2の自動入力でそのまま使う）

> **パソコンに慣れていない方へ**
> 手順だけを短くまとめた「[かんたんユーザーズガイド](USER_GUIDE.md)」を用意しています。まずはそちらを見てください。この README は、仕組みや細かい設定まで知りたいときの詳細版です。

---

## 目次

1. [はじめての方向け: これは何をするもの？](#はじめての方向け-これは何をするもの)
2. [開発の進み具合（フェーズ）](#開発の進み具合フェーズ)
3. [できること（機能一覧）](#できること機能一覧)
4. [セットアップ手順（順番通りに）](#セットアップ手順順番通りに)
5. [設定の書き方（.env）](#設定の書き方env)
6. [使い方](#使い方)
7. [出力形式](#出力形式)
8. [ディレクトリ構成](#ディレクトリ構成)
9. [設計上のポイント（上級者向け）](#設計上のポイント上級者向け)
10. [認識精度の評価と改善（開発者向け）](#認識精度の評価と改善開発者向け)
11. [テスト](#テスト)
12. [既知の制約](#既知の制約)
13. [トラブルシューティング](#トラブルシューティング)

---

## はじめての方向け: これは何をするもの？

ガンプラのパーツをなくしたり壊したりしたときは、BANDAI SPIRITS の部品注文サービスで取り寄せられます。このとき、説明書を見ながら「Aランナーの6番」「B1ランナーの12番」のように**パーツ番号を1つずつ書き写す**必要があります。

説明書の1ページにはパーツ番号がたくさん載っています。しかも、シールの番号や組み立て手順の番号など、**パーツ番号とまぎらわしい数字**も混ざっています。書き写すのは手間がかかり、間違いも起きやすい作業です。

このツールを使うと、説明書の写真を撮ってパソコンで

```powershell
.\.venv\Scripts\python.exe main.py data\sample_images\説明書.jpg
```

と実行するだけで、次のような一覧ができあがります。

```
+-----+-------------------+---------------------+-----------------+
| No. | ランナー (Runner) | パーツ番号 (Number) | 数量 (Quantity) |
+-----+-------------------+---------------------+-----------------+
| 1   | A                 | 6                   | 1               |
| 2   | A                 | 26                  | 1               |
| 3   | B1                | 12                  | 1               |
+-----+-------------------+---------------------+-----------------+
合計パーツ種類数: 3 点
```

---

## 開発の進み具合（フェーズ）

| フェーズ | 内容 | 状態 |
|---|---|---|
| フェーズ1 | 説明書の画像からパーツ番号を読み取り、JSON に出す | ✅ 実装済み |
| フェーズ2 | JSON をもとに、Playwright で部品注文サイトへ半自動で入力する | ⏳ 未実装（`src/order_automation/` にひな形のみ） |

---

## できること（機能一覧）

### パーツ番号の読み取り（`src/extractor.py`）

| 機能 | 内容 |
|---|---|
| 読み取りの対象 | **四角い枠で囲まれたランナー記号**（`A`、`B1`、`E1`、`H1`、`PC` など）と、それに付いた**パーツ番号**（`6`、`14`、`26` など）の組 |
| 除外するもの | シール・ホイルシール・マーキングシールの番号、組み立て手順の番号（黒いひし形の `1`、`2` など）、`×2` などの数量の指示、ページ番号、価格、バーコードなど |
| まとめて書かれた番号 | 1つのランナー枠の下に `6` と `7` が並んでいるときは、`A-6` と `A-7` の2つのパーツとして読み取る |
| 写真の向き | 90度・180度・270度の回転、傾き、影、照明の反射に対応する（プロンプトでの指示と EXIF 補正） |

### 画像の前処理（`src/image_utils.py`）

| 処理 | 内容 |
|---|---|
| 回転の補正 | スマホ写真に記録された EXIF の向き情報（Orientation）を読んで、正しい向きに回す |
| 色形式の統一 | PNG の透明部分や、パレット形式の画像などを、白背景の RGB に変換する |
| 縮小 | 長辺が 3072px を超える写真は、縦横比を保ったまま縮小する（送信量を減らすため） |
| 形式の統一 | JPEG（品質92）に変換してから Gemini に送る |

### 結果の整理（`src/models.py`）

| 処理 | 内容 |
|---|---|
| 表記ゆれの修正 | 全角の英数字を半角にし、ランナー記号を大文字にそろえる。`[A]`、`No.6`、`#6` のような余分な記号も取り除く |
| 重複の除去 | 同じランナー記号・番号の組は1つにまとめる |
| 並べ替え | ランナー記号順（`A` → `B` → `B1` → `B2` → `C`）、番号順（`1` → `2` → `6` → `14` → `26`）。文字列としてではなく数として比べるので、`14` が `2` より前に来ることはない |
| 数量の合算（任意） | `--sum-quantities` を付けると、同じパーツが何回出てきたかを数量として数える |

---

## セットアップ手順（順番通りに）

コマンドはすべて Windows の PowerShell で実行する前提で書いています。macOS / Linux の場合は、`.\.venv\Scripts\python.exe` を `.venv/bin/python` に読み替えてください。

### ステップ0: 必要なものを確認する

| 必要なもの | 確認方法 |
|---|---|
| Python 3.10 以上 | `py -0p` で `3.10` 以上が表示される |
| Git | `git --version` でバージョンが表示される |
| Google アカウント | Gemini API キーの発行に使う |

### ステップ1: リポジトリを取得する

```powershell
cd $HOME\Projects
git clone https://github.com/2ndPalace/GunplaPartsOrder.git
cd GunplaPartsOrder
```

### ステップ2: 仮想環境を作り、ライブラリを入れる

このプロジェクト専用の Python 環境（`.venv`）を作り、その中にライブラリを入れます。パソコン全体の Python には影響しません。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

入るライブラリは次のとおりです。

| ライブラリ | 用途 |
|---|---|
| `google-genai` | Gemini API の公式 SDK |
| `pydantic` | Gemini の出力を決まった形（構造化出力）にし、内容を検証する |
| `python-dotenv` | `.env` から API キーを読み込む |
| `pillow` | 画像の回転補正・縮小・変換 |
| `playwright` | フェーズ2のブラウザ自動化で使う予定 |
| `pytest` | テスト |

フェーズ2を試すときは、ブラウザ本体も入れておきます（フェーズ1だけなら不要です）。

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

### ステップ3: Gemini API キーを取得する

1. [Google AI Studio の API キーのページ](https://aistudio.google.com/apikey) を開き、Google アカウントでログインします。
2. 「API キーを作成」を押して、表示されたキー（`AIza` で始まる文字列）をコピーします。

**API キーはパスワードと同じです。** チャットや GitHub、SNS に貼らないでください。

### ステップ4: `.env` を作る

```powershell
Copy-Item .env.example .env
notepad .env
```

メモ帳が開いたら、`GEMINI_API_KEY=` の後ろをコピーしたキーに書き換えて保存します。書き方は[設定の書き方（.env）](#設定の書き方env)を見てください。

### ステップ5: 動作確認

まず、API を呼ばないモックモードで、全体が動くかを確かめます。

```powershell
.\.venv\Scripts\python.exe main.py dummy.jpg --mock
```

`[SUCCESS] JSONファイルを正常に出力しました` と出れば、インストールは成功です。次に、実際の説明書の写真で試します。

```powershell
.\.venv\Scripts\python.exe main.py data\sample_images\説明書.jpg
```

---

## 設定の書き方（.env）

プロジェクトのフォルダ（`main.py` と同じ場所）に置いた `.env` が読まれます。

```env
# 必須: Gemini API キー
GEMINI_API_KEY=AIzaSy...

# 任意: 使うモデル（書かなければ gemini-2.5-flash）
GEMINI_MODEL=gemini-2.5-flash
```

| 変数 | 必須 | 既定値 | 内容 |
|---|---|---|---|
| `GEMINI_API_KEY` | ✅ | なし | Gemini API キー。空のときや、見本の `your_gemini_api_key_here` のままのときはエラーで止まる |
| `GEMINI_MODEL` | | `gemini-2.5-flash` | 使う Gemini のモデル名。コマンドの `--model` を指定すると、そちらが優先される |

- `=` の前後に空白を入れないでください。
- `.env` は `.gitignore` に入っているので、`git push` しても GitHub には上がりません。
- `.env` を使わずに、環境変数 `GEMINI_API_KEY` を直接設定しても動きます。

---

## 使い方

### 基本

```powershell
.\.venv\Scripts\python.exe main.py <説明書の画像ファイル>
```

JPEG、PNG など、Pillow で開ける形式の画像を指定します。結果は画面に表と JSON で表示され、`data\output\<画像ファイル名>_parts.json` に保存されます。

### オプション一覧

| オプション | 内容 | 例 |
|---|---|---|
| `-o`, `--output` | JSON の保存先を指定する | `-o data\output\order.json` |
| `--model` | 使う Gemini のモデルを指定する | `--model gemini-2.5-pro` |
| `--sum-quantities` | 同じパーツが複数回出てきたら、その回数を数量にする（指定しなければ数量は常に1） | `--sum-quantities` |
| `--mock` | Gemini API を呼ばず、決まったダミーデータで動きを確かめる。API キーも画像も要らない | `--mock` |
| `-h`, `--help` | 使い方を表示する | `--help` |

### 使い方の例

```powershell
# 保存先を指定する
.\.venv\Scripts\python.exe main.py data\sample_images\page12.jpg -o data\output\rx78_page12.json

# 同じパーツが2回描かれているページで、数量も数えたい
.\.venv\Scripts\python.exe main.py data\sample_images\page12.jpg --sum-quantities
```

### 終了コード

| コード | 意味 |
|---|---|
| `0` | 成功した |
| `1` | 失敗した（API キーがない、画像が見つからない、API エラーなど） |

---

## 出力形式

```json
{
  "parts": [
    {"runner": "A", "number": "6", "quantity": 1},
    {"runner": "A", "number": "26", "quantity": 1},
    {"runner": "B1", "number": "12", "quantity": 1}
  ]
}
```

| 項目 | 型 | 内容 |
|---|---|---|
| `runner` | 文字列 | ランナー記号（`A`、`B1`、`PC` など）。半角・大文字にそろえてある |
| `number` | 文字列 | パーツ番号。部品注文サイトに入力しやすいよう、数ではなく文字列で持つ |
| `quantity` | 整数（1以上） | 注文する数量。通常は1 |

---

## ディレクトリ構成

```
GunplaPartsOrder/
├── .env.example              # .env の見本
├── .gitignore
├── pyproject.toml            # プロジェクト情報と pytest の設定
├── requirements.txt          # 依存ライブラリ
├── README.md                 # この文書（詳細版）
├── USER_GUIDE.md             # かんたんユーザーズガイド
├── main.py                   # コマンドの入り口（CLI）
├── evaluate.py               # 認識精度の評価ツール（CLI）
├── prompts/                  # 改良用のプロンプト（system.md / user.md）
├── src/
│   ├── config.py             # .env の読み込みと設定値
│   ├── models.py             # Pydantic モデル、表記ゆれの修正、重複の除去、並べ替え
│   ├── image_utils.py        # EXIF 回転補正などの前処理
│   ├── extractor.py          # Gemini API の呼び出しとプロンプト
│   ├── evaluation.py         # 正解ラベルとの比較・採点・実行記録
│   └── order_automation/     # フェーズ2（Playwright による自動入力）のひな形
├── tests/
│   ├── test_models.py
│   ├── test_image_utils.py
│   ├── test_extractor.py
│   └── test_evaluation.py
└── data/
    ├── sample_images/        # 説明書の写真を置く場所（Git には上がらない）
    ├── output/               # 結果の JSON の保存先（Git には上がらない）
    └── eval/                 # 精度評価用（中身は Git には上がらない）
        ├── images/           # 評価に使う説明書の写真
        ├── labels/           # 写真ごとの正解ラベル（<写真の名前>.json）
        └── runs/             # 評価を実行するたびの記録
```

---

## 設計上のポイント（上級者向け）

### 処理の流れ

```
写真 ─▶ image_utils: EXIF 回転補正・RGB 化・縮小・JPEG 化
     ─▶ extractor:  Gemini API（system_instruction + 構造化出力）
     ─▶ models:     Pydantic で検証・表記ゆれの修正
     ─▶ models:     重複の除去・自然順ソート
     ─▶ main:       画面に表示・JSON に保存
```

### なぜ構造化出力（Structured Outputs）を使うのか

`GenerateContentConfig` の `response_schema` に Pydantic モデル（`PartsExtractionResponse`）を渡しています。こうすると Gemini は、決まった形の JSON だけを返します。「説明文の中に JSON が混ざっている」といった、文章を解析しないと取り出せない出力になりません。

ただし、SDK が `response.parsed` を組み立てられなかったときに備えて、`response.text` を `model_validate_json` で読み直すフォールバックも入れています（`src/extractor.py`）。

### なぜ重複の除去・並べ替えを Gemini に任せないのか

プロンプトでは「同じパーツが何回出てきても全部返す」ように指示し、重複の除去と並べ替えは Python 側（`PartsOrderResult.from_raw_parts`）で行っています。理由は次の2つです。

- LLM に並べ替えまで任せると、並べ替えに気を取られて読み落としが増えたり、順番を間違えたりすることがある
- `--sum-quantities` で数量を数えるには、重複を含んだ生の結果が必要になる

### 自然順ソート

`B1` は `[(0, "B"), (1, 1)]`、`14` は `[(1, 14)]` のように、文字の部分と数字の部分に分けてから比べています（`split_alphanumeric_chunks`）。こうすると、`A` → `B` → `B1` → `B2` → `C` や、`2` → `6` → `14` → `26` の順に正しく並びます。

### 表記ゆれの修正

Gemini が `Ａ`（全角）や `[A]`、`No.6` のように返しても、`PartItem` の `field_validator` で次のように直します。

- NFKC 正規化で全角の英数字を半角にする
- ランナー記号を大文字にそろえる
- 括弧や `#`、`No.` などの記号を取り除く

`PartItem` の `__eq__` / `__hash__` は `(runner, number)` だけで比べるので、数量が違っても同じパーツとして扱われます。

### 画像の前処理を Python 側でも行う理由

スマホの写真は、画素データは横向きのまま保存され、「表示するときに90度回す」という情報だけが EXIF に書かれていることがよくあります。この情報がない状態で送ると、Gemini には横倒しの画像が届きます。そこで `ImageOps.exif_transpose` で、送る前に向きを直しています。EXIF のない画像（スキャン画像や、横倒しのまま撮った写真）の向きは、プロンプトで Gemini に判断させています。

### temperature を 0.1 にしている理由

同じ写真なら毎回同じ結果になってほしいので、出力のばらつきを小さくしています。

---

## 認識精度の評価と改善（開発者向け）

プロンプトやモデルを変えたときに、**本当に読み取りがよくなったのか**を数字で確かめるための仕組みです。写真ごとに「正解のパーツ一覧（正解ラベル）」を用意しておき、`evaluate.py` で抽出結果と比べて採点します。

> 説明書の写真はバンダイの著作物です。`data/eval/` の中身は `.gitignore` で除外してあり、公開リポジトリには上がりません。

### 改善のサイクル

```
① 写真を置く ─▶ ② 正解ラベルを作る ─▶ ③ 評価（基準）
                                          │
       ┌──────────────────────────────────┘
       ▼
④ prompts/system.md を直す ─▶ ⑤ 評価 ─▶ ⑥ 前回と比べる ─▶ ④ に戻る
```

### ① 写真を置く

評価に使う写真を `data/eval/images/` に入れます（JPEG / PNG / WebP / BMP）。シールの番号が多いページ、横向きの写真、影がかかった写真など、**苦手そうな写真を混ぜておく**と改善の効果が見えやすくなります。

### ② 正解ラベルを作る

1枚ずつ手で書くのは大変なので、まず AI に下書きを作らせてから直します。

```powershell
.\.venv\Scripts\python.exe evaluate.py init-labels
```

`data/eval/labels/<写真の名前>.json` ができます。**説明書と見比べて、間違いを手で直してください。** 形式は抽出結果の JSON と同じです（`quantity` は採点に使いません）。

```json
{
  "parts": [
    {"runner": "A", "number": "6", "quantity": 1},
    {"runner": "B1", "number": "12", "quantity": 1}
  ]
}
```

すでにラベルがある写真は飛ばします。作り直すときは `--overwrite` を付けます。

### ③ 評価する（基準を記録する）

```powershell
.\.venv\Scripts\python.exe evaluate.py run --note baseline
```

正解ラベルのある写真だけを抽出し、次のような結果を表示して `data/eval/runs/` に記録します。

```
+------------+--------+----+------------+--------------+--------+--------+--------+--------+--------+
| 画像       | 正解数 | TP | FP(誤検出) | FN(見落とし) | 適合率 | 再現率 | F1     | 安定   | エラー |
+------------+--------+----+------------+--------------+--------+--------+--------+--------+--------+
| page12.jpg | 3      | 5  | 1          | 1            |  83.3% |  83.3% |  83.3% | いいえ | 0      |
| page13.jpg | 1      | 2  | 0          | 0            | 100.0% | 100.0% | 100.0% | はい   | 0      |
+------------+--------+----+------------+--------------+--------+--------+--------+--------+--------+
合計: 適合率  87.5% / 再現率  87.5% / F1  87.5%（TP 7, FP 1, FN 1）
完全一致: 3 / 4 試行

【間違いの内訳】
- page12.jpg #1: 誤検出 S-4 / 見落とし B1-12
```

| 指標 | 意味 | 低いときに疑うこと |
|---|---|---|
| 適合率 | 抽出したもののうち、正しかった割合 | シール番号や手順番号を拾っている（誤検出が多い） |
| 再現率 | 正解のうち、抽出できた割合 | 小さい番号や、まとめて書かれた番号を見落としている |
| F1 | 適合率と再現率のバランスをとった総合点 | |
| 安定 | 同じ写真で、全試行が同じ結果だったか | 結果が毎回変わる（`--repeat` を2以上にしたときに意味がある） |

### ④ プロンプトを直す

既定のプロンプトを `prompts/` に書き出し、それを直します。

```powershell
.\.venv\Scripts\python.exe evaluate.py export-prompts
notepad prompts\system.md
```

### ⑤ 直したプロンプトで評価する

```powershell
.\.venv\Scripts\python.exe evaluate.py run --system-prompt prompts\system.md --note "シール除外を強化"
```

### ⑥ 前回と比べる

```powershell
.\.venv\Scripts\python.exe evaluate.py compare
```

引数を省くと、**1つ前の実行と最新の実行**を比べ、合計と写真ごとの F1 の増減を表示します。よくなったら、`prompts/system.md` の内容を `src/extractor.py` の `SYSTEM_INSTRUCTION` に反映します。

### コマンド一覧

| コマンド | 内容 | API を呼ぶか |
|---|---|---|
| `run` | 抽出して採点し、記録する | 呼ぶ |
| `init-labels` | 正解ラベルの下書きを作る | 呼ぶ |
| `rescore [実行]` | 過去の抽出結果を、**今の正解ラベル**で採点し直す。ラベルの間違いに気づいて直したときに使う | 呼ばない |
| `report [実行]` | 過去の記録を表示する | 呼ばない |
| `compare [A] [B]` | 2つの記録を比べる | 呼ばない |
| `list` | 記録の一覧（実行ID・モデル・プロンプトのハッシュ・F1・メモ）を表示する | 呼ばない |
| `export-prompts` | 既定のプロンプトを `prompts/` に書き出す | 呼ばない |

`[実行]` には、実行ID（先頭の一部だけでもよい）、`latest`（最新）、`latest~1`（1つ前）、記録ファイルのパスを指定できます。

### `run` / `init-labels` のオプション

| オプション | 内容 |
|---|---|
| `--note` | 記録に付けるメモ。何を変えたかを書いておくと、あとで `list` で見分けやすい（`run` のみ） |
| `--repeat N` | 1枚あたり N 回抽出する。Gemini の結果は毎回少し変わるので、改善したかどうかを判断するときは 3 回程度がおすすめ（`run` のみ） |
| `--system-prompt` / `--user-prompt` | プロンプトをファイルから読む |
| `--model` / `--temperature` | モデルや温度を変える |
| `--only NAME ...` | 指定した写真（拡張子なしの名前）だけを対象にする。苦手な1枚を集中して直すときに使う |
| `--interval 秒` | API 呼び出しの間を空ける。`429` エラー（回数制限）が出るときに使う |

### 記録に残るもの

`data/eval/runs/<実行ID>.json` には、モデル名、温度、**プロンプトの全文とハッシュ**、写真ごとの正解ラベル、Gemini が返した生の結果、エラー、処理時間が入ります。どのプロンプトでどの結果が出たかを、あとから必ずたどれるようにしています。

---

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Gemini API はモックに差し替えているので、API キーがなくても、通信しなくても実行できます。

| テスト | 確かめていること |
|---|---|
| `test_models.py::test_part_item_normalization` | 全角→半角、大文字化、記号の除去 |
| `test_models.py::test_part_sorting` | ランナー記号・番号の自然順ソート |
| `test_models.py::test_deduplication_and_order_result` | 重複の除去と、数量が1になること |
| `test_models.py::test_deduplication_with_sum_quantities` | `--sum-quantities` での数量の合算 |
| `test_models.py::test_extraction_response_parsing` | 構造化出力の JSON を読めること |
| `test_image_utils.py::test_load_and_preprocess_image` | 画像の読み込み・変換・縮小 |
| `test_extractor.py::test_extractor_with_mocked_gemini` | `response.parsed` から結果を組み立てる流れ |
| `test_extractor.py::test_extractor_fallback_to_text_parsing` | `response.text` から読み直すフォールバック |
| `test_evaluation.py` | 採点（TP / FP / FN、エラー時の扱い、合算）、安定性の判定、画像・ラベル・記録の読み込み、レポートと比較の表示、`run` → `rescore` の流れ |

---

## 既知の制約

- **実物の説明書の写真での精度は、まだ十分に確かめていません。** 特に、シール番号との区別や、細かい引き出し線の読み取りは、写真によって間違えることがあります。注文する前に、必ず説明書と見比べてください。
- 1回の実行で処理できる画像は1枚です。複数ページある場合は、ページごとに実行してください。
- プロンプトでは `SB-13` のような特殊なランナー記号を例に挙げています。説明書によっては `SB` がランナー記号で `13` がパーツ番号のこともあり、読み取りが揺れることがあります。
- 部品注文サイトへの入力（フェーズ2）はまだ実装していません。
- Python 3.14 で実行すると、`google-genai` から `DeprecationWarning` が出ることがあります。動作には影響しません。
- Gemini API の利用には、Google の利用規約と料金・回数の上限が適用されます。

---

## トラブルシューティング

| 症状・エラー | 原因 | 対処 |
|---|---|---|
| `ImportError: cannot import name 'genai' from 'google'` | ライブラリを入れていない Python で実行している | `python` ではなく `.\.venv\Scripts\python.exe` で実行する。または[ステップ2](#ステップ2-仮想環境を作りライブラリを入れる)をやり直す |
| `[CONFIG ERROR] GEMINI_API_KEY が設定されていません。` | `.env` がない、またはキーが空・見本のまま | `.env` が `main.py` と同じフォルダにあるか、`GEMINI_API_KEY=` の後ろにキーがあるかを確かめる |
| `.env` を作ったのに読まれない | メモ帳で保存したときに `.env.txt` になっている | `Get-ChildItem -Force` で名前を確かめ、`Rename-Item .env.txt .env` で直す |
| `[ERROR] 入力画像ファイルが見つかりません` | パスが間違っている | 画像のパスを確かめる。空白を含むパスは `"..."` で囲む |
| `API key not valid` を含むエラー | API キーが間違っている、または無効になっている | AI Studio でキーを確かめ、`.env` に貼り直す |
| `429` / `RESOURCE_EXHAUSTED` を含むエラー | API の回数の上限に達した | 少し時間を空けてから実行する |
| 抽出結果が空、または少ない | 写真がぼやけている、暗い、遠い | 説明書を平らにし、明るい場所で、1ステップ分を画面いっぱいに撮る |
| シール番号が混ざる | プロンプトだけでは区別できない写真 | シールの記号が写らないように撮り直す。結果を説明書と見比べて手で消す |
| `.\.venv\Scripts\Activate.ps1` が実行できない | PowerShell の実行ポリシーで止められている | 有効化せずに、`.\.venv\Scripts\python.exe` を直接使えば問題ない |
