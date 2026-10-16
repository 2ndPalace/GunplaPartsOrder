"""Image processing utilities for Gunpla instruction manual photos."""

import io
from pathlib import Path
from PIL import Image, ImageOps


def load_and_preprocess_image(
    image_path: Path | str,
    max_dimension: int = 3072,
) -> tuple[Image.Image, bytes, str]:
    """画像を読み込み、スマホ撮影写真のEXIF回転情報を補正してバイト列とMIMEタイプを返す。

    Args:
        image_path: 入力画像ファイルのパス
        max_dimension: 最大解像度（長辺ピクセル数）。超える場合はアスペクト比を維持して縮小。

    Returns:
        tuple[Image.Image, bytes, str]:
            - 補正後のPIL Imageオブジェクト
            - エンコード済み画像バイト列（JPEG）
            - MIMEタイプ ("image/jpeg" または "image/png")
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"画像ファイルが見つかりません: {path}")

    # 画像の読み込み
    with Image.open(path) as img:
        # EXIFのOrientationタグに基づいて回転を補正（スマホ写真の90度・180度回転対策）
        corrected_img = ImageOps.exif_transpose(img)
        if corrected_img is None:
            corrected_img = img.copy()

        # RGBモードに変換（RGBAやパレットモード対応）
        if corrected_img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", corrected_img.size, (255, 255, 255))
            if corrected_img.mode == "P":
                corrected_img = corrected_img.convert("RGBA")
            background.paste(
                corrected_img,
                mask=corrected_img.split()[-1] if corrected_img.mode == "RGBA" else None,
            )
            corrected_img = background
        elif corrected_img.mode != "RGB":
            corrected_img = corrected_img.convert("RGB")

        # 長辺が max_dimension を超える場合はアスペクト比を維持して縮小（過大なスマホ写真の通信最適化）
        width, height = corrected_img.size
        longest_edge = max(width, height)
        if longest_edge > max_dimension:
            scale = max_dimension / longest_edge
            new_size = (int(width * scale), int(height * scale))
            corrected_img = corrected_img.resize(new_size, Image.Resampling.LANCZOS)

        # JPEGバイト列として書き出し
        buffer = io.BytesIO()
        corrected_img.save(buffer, format="JPEG", quality=92, optimize=True)
        image_bytes = buffer.getvalue()
        mime_type = "image/jpeg"

    return corrected_img, image_bytes, mime_type
