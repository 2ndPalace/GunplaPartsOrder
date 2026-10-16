"""Gemini API extractor for Gunpla instruction manual parts."""

from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types

from src.config import settings
from src.image_utils import load_and_preprocess_image
from src.models import (
    PartItem,
    PartsExtractionResponse,
    PartsOrderResult,
)

# ガンプラ説明書専用のシステムプロンプト
SYSTEM_INSTRUCTION = """\
あなたはガンプラ（バンダイのプラモデル）の説明書（組立説明書・マニュアル）から、
注文に必要なプラスチックパーツ番号を極めて高い精度で抽出するエキスパートAIです。

【入力画像について】
- スマートフォン等で撮影された説明書画像です。
- 写真が90度/180度/270度回転していたり、斜めに傾いていたり、影や照明の反射、歪みがある場合があります。
- 文字や枠の向きを画像全体から自動的に判読し、どのようなアングルや向きであっても正確に読み取ってください。

【抽出対象（必ず抽出するもの）】
- 説明書の組み立て工程やパーツ図にある「四角い枠（ボックス）で囲まれたランナー記号」と、その直後・直下または引き出し線で示された「パーツ番号（数字）」のペア。
  - ランナー記号の例:
    - アルファベット1文字: A, B, C, D, E, F など
    - アルファベット＋数字: B1, B2, C1, D2, E1, H1 など
    - 特殊ランナー記号: PC（ポリキャップ）、SB（サーベル等、例: SB-13, SB-12）、BA（台座）など
  - パーツ番号の例:
    - 1, 2, 6, 14, 26, 45 など
- 同じランナー枠に対して複数のパーツ番号が並んでいる場合（例: [A] の下に 6 と 7 がある場合）、それぞれ独立したパーツ（runner: "A", number: "6" と runner: "A", number: "7"）としてすべて抽出してください。

【除外対象（絶対に抽出してはいけないもの）】
1. シール・ホイルシール・マーキングシールの番号:
   - 「シール」「ホイルシール」「マーキングシール」「プラスチックシール」「テトロンシール」等の記載があるもの、または角丸四角や特殊なシールマーク・丸数字で指示されている番号（例: シール 4〜7、シール 1 など）はすべて除外してください。
2. 組み立て手順の工程番号・ステップ番号:
   - 黒いひし形（◆）、黒丸（●）、大きな四角囲み、工程枠の先頭に振られているステップ番号（「1」「2」「3」など）はパーツ番号ではないため除外してください。
3. 組み立て指示記号・数量指示:
   - 「×2」「2個作る」「反対側も同様に組み立てる」「向きに注意」「あとからはめこむ」「接着」などの指示文や指示記号・数字は除外してください。
4. 説明書のページ番号、注意書き番号、対象年齢、価格、バーコード等の周辺テキスト。
5. パーツ番号が伴わないランナー名単体。

【出力仕様】
- 指定されたJSONスキーマに従い、すべての抽出パーツをリスト形式で返してください。
- 1つの画像内に同一のパーツ番号が複数回登場する場合も、見つかったものを漏れなく抽出してください（後続の処理で重複排除・ソートを行います）。
"""

USER_PROMPT = """\
この説明書画像に記載されているすべてのプラスチックパーツの「ランナー記号」と「パーツ番号」のペアを漏れなく抽出してください。
シール番号や組み立て手順番号、注記の数字は厳密に除外してください。
画像が回転している場合や影がある場合も、枠内の文字を正確に読み取ってください。
"""


class GunplaPartsExtractor:
    """Gemini APIを使用してガンプラ説明書画像からパーツ番号を抽出するクラス。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """イニシャライザ。

        Args:
            api_key: Gemini APIキー。省略時は .env または環境変数から読み込む。
            model_name: 使用するモデル名。省略時は settings.DEFAULT_MODEL ('gemini-2.5-flash')。
        """
        self.api_key = api_key or settings.validate_api_key()
        self.model_name = model_name or settings.DEFAULT_MODEL
        self.client = genai.Client(api_key=self.api_key)

    def extract_from_image(
        self,
        image_path: Path | str,
        sum_quantities: bool = False,
    ) -> PartsOrderResult:
        """画像ファイルからパーツ一覧を抽出し、重複排除・ソート済みの結果を返す。

        Args:
            image_path: 画像ファイルのパス
            sum_quantities: 同一パーツが複数回抽出された際に数量を合算するかどうか（デフォルトはFalse=数量1）

        Returns:
            PartsOrderResult: 重複排除・ソートされたパーツ一覧
        """
        path = Path(image_path)
        # 画像の前処理（EXIF回転補正、サイズ調整）
        _, image_bytes, mime_type = load_and_preprocess_image(path)

        # Gemini API のリクエスト構築
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            USER_PROMPT,
        ]

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=PartsExtractionResponse,
            temperature=0.1,  # 再現性と正確性のために低温度
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=config,
        )

        # 構造化出力のパース
        raw_parts: list[PartItem] = []
        if response.parsed and isinstance(response.parsed, PartsExtractionResponse):
            raw_parts = response.parsed.parts
        elif response.text:
            # フォールバック: JSONテキストからPydanticで検証
            parsed_data = PartsExtractionResponse.model_validate_json(response.text)
            raw_parts = parsed_data.parts

        # 重複排除と自然順ソートを実施
        result = PartsOrderResult.from_raw_parts(
            raw_parts=raw_parts,
            sum_quantities=sum_quantities,
        )
        return result
