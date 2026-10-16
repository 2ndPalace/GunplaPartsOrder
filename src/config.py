"""Configuration settings for Gunpla Parts Order project."""

import os
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルートディレクトリの検出と .env の読み込み
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """アプリケーション設定クラス"""

    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = PROJECT_ROOT / "data"
    DEFAULT_OUTPUT_DIR: Path = DATA_DIR / "output"
    SAMPLE_IMAGES_DIR: Path = DATA_DIR / "sample_images"

    # Gemini API 設定
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    @classmethod
    def validate_api_key(cls) -> str:
        """APIキーが設定されているか検証し、取得する。未設定の場合はValueErrorを発生。"""
        # 直前の環境変数変更にも対応できるように再度getenvを確認
        key = os.getenv("GEMINI_API_KEY", cls.GEMINI_API_KEY).strip()
        if not key or key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY が設定されていません。\n"
                ".env ファイルに GEMINI_API_KEY=your_actual_api_key を設定するか、\n"
                "環境変数 GEMINI_API_KEY を設定してください。"
            )
        return key


settings = Settings()
