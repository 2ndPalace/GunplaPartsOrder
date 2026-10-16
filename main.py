"""Command Line Interface for Gunpla Parts Order Extractor."""

import argparse
import io
import json
import sys
from pathlib import Path

# Windows環境のコンソール文字化け対策（UTF-8設定）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.config import settings
from src.extractor import GunplaPartsExtractor
from src.models import PartItem, PartsOrderResult


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ガンプラ説明書画像からパーツ番号（ランナー記号＋番号）を抽出し、JSON出力するツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "image_path",
        type=str,
        help="説明書の画像ファイルパス（JPEG/PNG等）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="出力先JSONファイルパス（省略時は data/output/<画像ファイル名>_parts.json）",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=settings.DEFAULT_MODEL,
        help=f"使用するGeminiモデル名（デフォルト: {settings.DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--sum-quantities",
        action="store_true",
        help="画像内で同一パーツが複数回登場した場合、数量を合算する（デフォルトは1）",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Gemini APIを呼び出さず、モックデータで動作確認を行うテストモード",
    )
    return parser.parse_args()


def get_mock_result() -> PartsOrderResult:
    """テスト・動作確認用のモック結果を返す。"""
    raw_mock_parts = [
        PartItem(runner="B1", number="12", quantity=1),
        PartItem(runner="A", number="26", quantity=1),
        PartItem(runner="A", number="6", quantity=1),
        PartItem(runner="A", number="6", quantity=1),  # 重複テスト
        PartItem(runner="E1", number="2", quantity=1),
        PartItem(runner="H1", number="14", quantity=1),
    ]
    return PartsOrderResult.from_raw_parts(raw_mock_parts)


def main() -> int:
    args = parse_arguments()
    image_path = Path(args.image_path)

    # 出力ファイルパスの決定
    if args.output:
        output_path = Path(args.output)
    else:
        settings.DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = settings.DEFAULT_OUTPUT_DIR / f"{image_path.stem}_parts.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(" ガンプラ部品注文半自動化 - パーツ番号抽出 (フェーズ1)")
    print("=" * 60)
    print(f"入力画像: {image_path}")
    print(f"使用モデル: {args.model}")
    print(f"出力先JSON: {output_path}")
    print("-" * 60)

    try:
        if args.mock:
            print("[INFO] --mock モードで実行します（Gemini APIは呼び出しません）...")
            result = get_mock_result()
        else:
            if not image_path.is_file():
                print(f"[ERROR] 入力画像ファイルが見つかりません: {image_path}", file=sys.stderr)
                return 1

            print("[INFO] 画像を前処理し、Gemini APIでパーツ番号を抽出しています...")
            extractor = GunplaPartsExtractor(model_name=args.model)
            result = extractor.extract_from_image(
                image_path=image_path,
                sum_quantities=args.sum_quantities,
            )

        # コンソールへのテーブル表示
        print("\n【抽出結果一覧（重複排除・ランナー記号/番号順ソート済み）】")
        print(result.to_table_string())

        # JSONファイルへの書き出し
        json_data = result.model_dump()
        json_str = json.dumps(json_data, indent=2, ensure_ascii=False)
        output_path.write_text(json_str, encoding="utf-8")

        print("\n【JSONプレビュー】")
        print(json_str)

        print("-" * 60)
        print(f"[SUCCESS] JSONファイルを正常に出力しました: {output_path}")
        print("=" * 60)
        return 0

    except ValueError as ve:
        print(f"\n[CONFIG ERROR] {ve}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[ERROR] 抽出処理中にエラーが発生しました: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
