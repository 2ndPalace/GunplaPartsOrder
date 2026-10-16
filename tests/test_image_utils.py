"""Tests for image loading and preprocessing."""

import io
from PIL import Image
from src.image_utils import load_and_preprocess_image


def test_load_and_preprocess_image(tmp_path):
    """画像の正常読み込みとリサイズ・フォーマット変換のテスト"""
    # テスト用画像の生成 (100x200 RGBA画像)
    test_img = Image.new("RGBA", (100, 200), color=(255, 0, 0, 128))
    img_path = tmp_path / "test_instruction.png"
    test_img.save(img_path)

    # 読み込みと前処理
    processed_img, img_bytes, mime_type = load_and_preprocess_image(img_path, max_dimension=150)

    # 検証
    assert processed_img.mode == "RGB"
    assert mime_type == "image/jpeg"
    assert len(img_bytes) > 0
    # 長辺200が150にリサイズされていること (アスペクト比維持: 75x150)
    assert max(processed_img.size) == 150
