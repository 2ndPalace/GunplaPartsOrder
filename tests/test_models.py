"""Tests for Pydantic data models and sorting/deduplication logic."""

import json
from src.models import (
    PartItem,
    PartsExtractionResponse,
    PartsOrderResult,
    part_sort_key,
)


def test_part_item_normalization():
    """全角や小文字、不要な括弧の正規化テスト"""
    item1 = PartItem(runner="ａ", number="６")
    assert item1.runner == "A"
    assert item1.number == "6"
    assert item1.quantity == 1

    item2 = PartItem(runner="【b1】", number="No.12")
    assert item2.runner == "B1"
    assert item2.number == "12"

    item3 = PartItem(runner="[e1]", number="#2")
    assert item3.runner == "E1"
    assert item3.number == "2"


def test_part_sorting():
    """ランナー記号順およびパーツ番号順の自然順ソートテスト"""
    items = [
        PartItem(runner="H1", number="14"),
        PartItem(runner="B1", number="12"),
        PartItem(runner="A", number="26"),
        PartItem(runner="A", number="6"),
        PartItem(runner="A", number="2"),
        PartItem(runner="B2", number="3"),
        PartItem(runner="B", number="1"),
        PartItem(runner="E1", number="10"),
        PartItem(runner="E1", number="2"),
    ]

    sorted_items = sorted(items, key=part_sort_key)
    pairs = [(item.runner, item.number) for item in sorted_items]

    expected = [
        ("A", "2"),
        ("A", "6"),
        ("A", "26"),
        ("B", "1"),
        ("B1", "12"),
        ("B2", "3"),
        ("E1", "2"),
        ("E1", "10"),
        ("H1", "14"),
    ]
    assert pairs == expected


def test_deduplication_and_order_result():
    """重複排除およびソートの統合テスト"""
    raw_parts = [
        PartItem(runner="B1", number="12"),
        PartItem(runner="A", number="26"),
        PartItem(runner="A", number="6"),
        PartItem(runner="A", number="6"),  # 重複
        PartItem(runner="B1", number="12"),  # 重複
        PartItem(runner="A", number="26"),  # 重複
    ]

    result = PartsOrderResult.from_raw_parts(raw_parts)

    # 重複排除されていること（3点）
    assert len(result.parts) == 3

    # ソート順の確認
    assert result.parts[0].runner == "A" and result.parts[0].number == "6"
    assert result.parts[1].runner == "A" and result.parts[1].number == "26"
    assert result.parts[2].runner == "B1" and result.parts[2].number == "12"

    # JSON出力形式の確認（要件と完全に一致しているか）
    dumped = result.model_dump()
    expected_json = {
        "parts": [
            {"runner": "A", "number": "6", "quantity": 1},
            {"runner": "A", "number": "26", "quantity": 1},
            {"runner": "B1", "number": "12", "quantity": 1},
        ]
    }
    assert dumped == expected_json


def test_deduplication_with_sum_quantities():
    """数量合算オプションのテスト"""
    raw_parts = [
        PartItem(runner="A", number="6", quantity=1),
        PartItem(runner="A", number="6", quantity=2),
    ]
    result = PartsOrderResult.from_raw_parts(raw_parts, sum_quantities=True)
    assert len(result.parts) == 1
    assert result.parts[0].runner == "A"
    assert result.parts[0].number == "6"
    assert result.parts[0].quantity == 3


def test_extraction_response_parsing():
    """Gemini APIからのJSONレスポンス構造のパース確認"""
    json_str = """
    {
      "parts": [
        {"runner": "A", "number": "6", "quantity": 1},
        {"runner": "A", "number": "26", "quantity": 1},
        {"runner": "B1", "number": "12", "quantity": 1}
      ]
    }
    """
    parsed = PartsExtractionResponse.model_validate_json(json_str)
    assert len(parsed.parts) == 3
    assert parsed.parts[0].runner == "A"
    assert parsed.parts[0].number == "6"
