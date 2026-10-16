"""Data models for Gunpla parts extraction and ordering."""

import re
import unicodedata
from typing import Any
from pydantic import BaseModel, Field, field_validator


def normalize_string(val: str) -> str:
    """全角文字を半角に正規化し、前後の空白を除去して大文字に揃える。"""
    if not val:
        return ""
    # 全角英数字記号を半角に変換 (NFKC正規化)
    normalized = unicodedata.normalize("NFKC", str(val)).strip()
    return normalized


def split_alphanumeric_chunks(s: str) -> list[tuple[int, Any]]:
    """自然順ソートのためのキー生成関数。

    文字列をアルファベット・記号チャンクと数字チャンクに分割し、
    数字チャンクは整数に変換して比較可能にする。
    例: 'B1' -> [(0, 'B'), (1, 1)]
         '14' -> [(1, 14)]
    """
    chunks: list[tuple[int, Any]] = []
    for part in re.split(r"(\d+)", s):
        if not part:
            continue
        if part.isdigit():
            chunks.append((1, int(part)))
        else:
            chunks.append((0, part.upper()))
    return chunks


def part_sort_key(item: "PartItem") -> tuple[list[tuple[int, Any]], list[tuple[int, Any]]]:
    """パーツのソートキー（ランナー記号順 -> パーツ番号順）を返す。"""
    runner_key = split_alphanumeric_chunks(item.runner)
    number_key = split_alphanumeric_chunks(item.number)
    return (runner_key, number_key)


class PartItem(BaseModel):
    """単一のガンプラパーツ情報"""

    runner: str = Field(
        ...,
        description="ランナー記号（四角い枠内のアルファベットや英数字。例: A, B1, E1, H1, PC, SB-13など）。",
    )
    number: str = Field(
        ...,
        description="パーツ番号（ランナー記号に付随する数字。例: '6', '14', '26'など）。",
    )
    quantity: int = Field(
        default=1,
        ge=1,
        description="注文数量（通常は1）。",
    )

    @field_validator("runner", mode="before")
    @classmethod
    def clean_runner(cls, v: Any) -> str:
        s = normalize_string(str(v)).upper()
        # 不要な記号「枠」や括弧などが紛れ込んだ場合のサニタイズ
        s = re.sub(r"[\[\]【】\(\)「」<>]", "", s).strip()
        return s

    @field_validator("number", mode="before")
    @classmethod
    def clean_number(cls, v: Any) -> str:
        s = normalize_string(str(v))
        # 先頭の不要な記号（#やNo.、括弧など）を除去
        s = re.sub(r"^(?:NO\.?|#|№)", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"[\[\]【】\(\)「」<>]", "", s).strip()
        return s

    def __hash__(self) -> int:
        return hash((self.runner, self.number))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, PartItem):
            return self.runner == other.runner and self.number == other.number
        return False


class PartsExtractionResponse(BaseModel):
    """Gemini APIの構造化出力用レスポンスモデル"""

    parts: list[PartItem] = Field(
        default_factory=list,
        description="説明書画像から抽出されたすべてのパーツ番号リスト",
    )


class PartsOrderResult(BaseModel):
    """ソート・重複排除済みの注文用パーツデータ"""

    parts: list[PartItem] = Field(
        default_factory=list,
        description="重複排除・自然順ソート済みのパーツリスト",
    )

    @classmethod
    def from_raw_parts(
        cls,
        raw_parts: list[PartItem],
        sum_quantities: bool = False,
    ) -> "PartsOrderResult":
        """未加工のパーツリストから重複を排除し、ランナー記号順・番号順にソートして生成する。

        Args:
            raw_parts: 抽出されたパーツリスト
            sum_quantities: 重複時に数量を合算するかどうか（Falseの場合は1とする）
        """
        # 重複排除の集約マップ: (runner, number) -> quantity
        unique_map: dict[tuple[str, str], int] = {}
        for p in raw_parts:
            # 空のrunnerやnumberは除外
            if not p.runner or not p.number:
                continue
            key = (p.runner, p.number)
            if key not in unique_map:
                unique_map[key] = p.quantity if sum_quantities else 1
            else:
                if sum_quantities:
                    unique_map[key] += p.quantity

        # PartItem オブジェクトのリストを再構築
        unique_items = [
            PartItem(runner=runner, number=number, quantity=qty)
            for (runner, number), qty in unique_map.items()
        ]

        # ランナー順・パーツ番号順に自然順ソート
        sorted_items = sorted(unique_items, key=part_sort_key)
        return cls(parts=sorted_items)

    def to_table_string(self) -> str:
        """コンソール表示用のテーブル文字列を生成する。"""
        if not self.parts:
            return "（抽出されたパーツはありません）"

        headers = ["No.", "ランナー (Runner)", "パーツ番号 (Number)", "数量 (Quantity)"]
        rows: list[list[str]] = []
        for i, item in enumerate(self.parts, start=1):
            rows.append([str(i), item.runner, item.number, str(item.quantity)])

        def char_width(c: str) -> int:
            return 2 if unicodedata.east_asian_width(c) in ("F", "W", "A") else 1

        def string_width(s: str) -> int:
            return sum(char_width(c) for c in s)

        def pad_string(s: str, width: int) -> str:
            w = string_width(s)
            return s + " " * max(0, width - w)

        col_widths = [string_width(h) for h in headers]
        for row in rows:
            for c_idx, val in enumerate(row):
                w = string_width(val)
                if w > col_widths[c_idx]:
                    col_widths[c_idx] = w

        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        header_line = "| " + " | ".join(pad_string(headers[i], col_widths[i]) for i in range(len(headers))) + " |"

        lines = [separator, header_line, separator]
        for row in rows:
            row_line = "| " + " | ".join(pad_string(row[i], col_widths[i]) for i in range(len(row))) + " |"
            lines.append(row_line)
        lines.append(separator)
        lines.append(f"合計パーツ種類数: {len(self.parts)} 点")
        return "\n".join(lines)
