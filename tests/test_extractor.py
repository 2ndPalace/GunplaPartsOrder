"""Tests for GunplaPartsExtractor using mocks."""

from unittest.mock import MagicMock, patch
from PIL import Image

from src.extractor import GunplaPartsExtractor
from src.models import PartItem, PartsExtractionResponse


def test_extractor_with_mocked_gemini(tmp_path):
    """Gemini API をモックした抽出処理の検証"""
    # テスト用画像を作成
    dummy_img = Image.new("RGB", (50, 50), color="white")
    dummy_path = tmp_path / "manual_sample.jpg"
    dummy_img.save(dummy_path)

    # モックレスポンスの作成
    mock_response = MagicMock()
    mock_response.parsed = PartsExtractionResponse(
        parts=[
            PartItem(runner="B1", number="12", quantity=1),
            PartItem(runner="A", number="26", quantity=1),
            PartItem(runner="A", number="6", quantity=1),
            PartItem(runner="A", number="6", quantity=1),  # 重複
        ]
    )
    mock_response.text = None

    with patch("src.extractor.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_response

        extractor = GunplaPartsExtractor(api_key="dummy_api_key_for_test")
        result = extractor.extract_from_image(dummy_path)

        # 重複排除されていること
        assert len(result.parts) == 3

        # ソート順: A-6 -> A-26 -> B1-12
        assert result.parts[0].runner == "A"
        assert result.parts[0].number == "6"
        assert result.parts[1].runner == "A"
        assert result.parts[1].number == "26"
        assert result.parts[2].runner == "B1"
        assert result.parts[2].number == "12"


def test_extractor_fallback_to_text_parsing(tmp_path):
    """response.parsedがNoneでresponse.textにJSONがある場合のフォールバックテスト"""
    dummy_img = Image.new("RGB", (50, 50), color="white")
    dummy_path = tmp_path / "manual_sample2.jpg"
    dummy_img.save(dummy_path)

    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = """
    {
      "parts": [
        {"runner": "C1", "number": "8", "quantity": 1},
        {"runner": "A", "number": "1", "quantity": 1}
      ]
    }
    """

    with patch("src.extractor.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_response

        extractor = GunplaPartsExtractor(api_key="dummy_api_key_for_test")
        result = extractor.extract_from_image(dummy_path)

        assert len(result.parts) == 2
        assert result.parts[0].runner == "A"
        assert result.parts[0].number == "1"
        assert result.parts[1].runner == "C1"
        assert result.parts[1].number == "8"
