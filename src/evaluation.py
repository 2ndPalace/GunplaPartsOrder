"""Accuracy evaluation utilities for the Gunpla parts extractor.

正解ラベルと抽出結果を (runner, number) の集合として比較し、
適合率・再現率・F1 を計算する。実行結果は JSON に保存し、後から比較・再採点できる。
"""

import hashlib
import json
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.config import settings
from src.models import PartItem, PartsExtractionResponse, part_sort_key

EVAL_DIR: Path = settings.DATA_DIR / "eval"
DEFAULT_IMAGES_DIR: Path = EVAL_DIR / "images"
DEFAULT_LABELS_DIR: Path = EVAL_DIR / "labels"
DEFAULT_RUNS_DIR: Path = EVAL_DIR / "runs"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

PartKey = tuple[str, str]


# ---------------------------------------------------------------------------
# 画像・正解ラベルの読み込み
# ---------------------------------------------------------------------------


def find_images(images_dir: Path, only: Optional[list[str]] = None) -> list[Path]:
    """評価用画像を名前順で返す。only を指定した場合は、そのファイル名（拡張子なし）の画像だけを返す。"""
    if not images_dir.is_dir():
        return []
    images = sorted(
        p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if only:
        wanted = set(only)
        images = [p for p in images if p.stem in wanted]
    return images


def label_path_for(image_path: Path, labels_dir: Path) -> Path:
    """画像に対応する正解ラベルのパス（labels/<画像ファイル名>.json）を返す。"""
    return labels_dir / f"{image_path.stem}.json"


def load_label(path: Path) -> list[PartItem]:
    """正解ラベルを読み込む。抽出結果と同じ {"parts": [...]} 形式で、同じ正規化を通す。"""
    return PartsExtractionResponse.model_validate_json(path.read_text(encoding="utf-8")).parts


def to_key_set(parts: list[PartItem]) -> set[PartKey]:
    """パーツリストを (runner, number) の集合にする。数量と重複は採点に使わない。"""
    return {(p.runner, p.number) for p in parts if p.runner and p.number}


def sort_keys(keys: set[PartKey]) -> list[PartKey]:
    """(runner, number) の集合を、出力と同じ自然順に並べる。"""
    return sorted(keys, key=lambda k: part_sort_key(PartItem(runner=k[0], number=k[1])))


def format_key(key: PartKey) -> str:
    return f"{key[0]}-{key[1]}"


# ---------------------------------------------------------------------------
# 採点
# ---------------------------------------------------------------------------


class Score(BaseModel):
    """1回分（または合計）の採点結果"""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        """適合率: 抽出したもののうち正しかった割合（誤検出が少ないほど高い）"""
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        """再現率: 正解のうち抽出できた割合（読み落としが少ないほど高い）"""
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def __add__(self, other: "Score") -> "Score":
        return Score(tp=self.tp + other.tp, fp=self.fp + other.fp, fn=self.fn + other.fn)


class TrialResult(BaseModel):
    """1枚の画像に対する1回分の抽出結果"""

    predicted: list[PartItem] = Field(default_factory=list, description="Gemini が返した生の結果")
    error: Optional[str] = None
    elapsed_sec: float = 0.0


class ImageResult(BaseModel):
    """1枚の画像に対する全試行の結果"""

    image: str
    expected: list[PartItem]
    trials: list[TrialResult]


def score_sets(expected: set[PartKey], predicted: set[PartKey]) -> Score:
    return Score(
        tp=len(expected & predicted),
        fp=len(predicted - expected),
        fn=len(expected - predicted),
    )


def score_trial(expected: list[PartItem], trial: TrialResult) -> Score:
    """1回分を採点する。エラーになった試行は、何も抽出できなかったものとして扱う。"""
    predicted = set() if trial.error else to_key_set(trial.predicted)
    return score_sets(to_key_set(expected), predicted)


def total_score(results: list[ImageResult]) -> Score:
    """全画像・全試行を合算した採点結果（マイクロ平均）"""
    total = Score()
    for r in results:
        for t in r.trials:
            total = total + score_trial(r.expected, t)
    return total


def is_stable(result: ImageResult) -> bool:
    """全試行で同じ結果が返ったかどうか（試行が1回なら常に True）"""
    sets = [frozenset(to_key_set(t.predicted)) if not t.error else None for t in result.trials]
    return len(set(sets)) <= 1


# ---------------------------------------------------------------------------
# 実行結果の保存・読み込み
# ---------------------------------------------------------------------------


class RunRecord(BaseModel):
    """1回の評価実行の記録（data/eval/runs/ に保存する）"""

    run_id: str
    created_at: str
    note: str = ""
    model: str
    temperature: float
    system_prompt_source: str
    system_prompt_sha256: str
    user_prompt_source: str
    user_prompt_sha256: str
    system_prompt: str
    user_prompt: str
    repeat: int
    results: list[ImageResult]
    rescored_from: Optional[str] = None


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def new_run_id(note: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in note.strip())[:30]
    return f"{stamp}_{slug}" if slug else stamp


def save_run(record: RunRecord, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{record.run_id}.json"
    # 同じ秒・同じメモで実行したときに、前の記録を上書きしない
    suffix = 2
    while path.exists():
        record.run_id = f"{record.run_id.rsplit('~', 1)[0]}~{suffix}"
        path = runs_dir / f"{record.run_id}.json"
        suffix += 1
    path.write_text(
        json.dumps(record.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def load_run(ref: str, runs_dir: Path) -> RunRecord:
    """実行記録を読み込む。ref はファイルパス、run_id、または "latest" / "latest~1"（1つ前）など。"""
    path = resolve_run_path(ref, runs_dir)
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_run_path(ref: str, runs_dir: Path) -> Path:
    if ref.startswith("latest"):
        back = int(ref.split("~", 1)[1]) if "~" in ref else 0
        runs = sorted(runs_dir.glob("*.json"))
        if len(runs) <= back:
            raise FileNotFoundError(f"実行記録が足りません（{len(runs)} 件しかありません）: {ref}")
        return runs[-1 - back]
    candidate = Path(ref)
    if candidate.is_file():
        return candidate
    candidate = runs_dir / (ref if ref.endswith(".json") else f"{ref}.json")
    if candidate.is_file():
        return candidate
    # run_id の先頭部分だけでも指定できるようにする
    matches = sorted(runs_dir.glob(f"{ref}*.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(m.stem for m in matches)
        raise FileNotFoundError(f"複数の実行記録に一致しました: {names}")
    raise FileNotFoundError(f"実行記録が見つかりません: {ref}")


# ---------------------------------------------------------------------------
# レポート
# ---------------------------------------------------------------------------


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W", "A") else 1 for c in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _width(s))


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(_width(h), *(_width(r[i]) for r in rows)) if rows else _width(h) for i, h in enumerate(headers)]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [sep, "| " + " | ".join(_pad(h, w) for h, w in zip(headers, widths)) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(_pad(c, w) for c, w in zip(row, widths)) + " |")
    lines.append(sep)
    return "\n".join(lines)


def _pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def image_score(result: ImageResult) -> Score:
    total = Score()
    for t in result.trials:
        total = total + score_trial(result.expected, t)
    return total


def render_report(record: RunRecord, verbose: bool = True) -> str:
    """実行記録を、画像ごとの表・合計・間違いの一覧にして返す。"""
    lines: list[str] = []
    lines.append(f"実行ID: {record.run_id}" + (f"（メモ: {record.note}）" if record.note else ""))
    lines.append(
        f"モデル: {record.model} / temperature: {record.temperature} / 試行回数: {record.repeat}"
    )
    lines.append(
        f"プロンプト: system={record.system_prompt_source} [{record.system_prompt_sha256}]"
        f" / user={record.user_prompt_source} [{record.user_prompt_sha256}]"
    )
    if record.rescored_from:
        lines.append(f"再採点元: {record.rescored_from}")
    lines.append("")

    rows: list[list[str]] = []
    for r in record.results:
        s = image_score(r)
        errors = sum(1 for t in r.trials if t.error)
        rows.append(
            [
                r.image,
                str(len(to_key_set(r.expected))),
                str(s.tp),
                str(s.fp),
                str(s.fn),
                _pct(s.precision),
                _pct(s.recall),
                _pct(s.f1),
                "はい" if is_stable(r) else "いいえ",
                str(errors),
            ]
        )
    headers = ["画像", "正解数", "TP", "FP(誤検出)", "FN(見落とし)", "適合率", "再現率", "F1", "安定", "エラー"]
    lines.append(render_table(headers, rows))

    total = total_score(record.results)
    perfect = sum(
        1 for r in record.results for t in r.trials if score_trial(r.expected, t).f1 == 1.0
    )
    trials = sum(len(r.trials) for r in record.results)
    lines.append(
        f"合計: 適合率 {_pct(total.precision)} / 再現率 {_pct(total.recall)} / F1 {_pct(total.f1)}"
        f"（TP {total.tp}, FP {total.fp}, FN {total.fn}）"
    )
    lines.append(f"完全一致: {perfect} / {trials} 試行")

    if verbose:
        detail = render_mistakes(record)
        if detail:
            lines.append("")
            lines.append("【間違いの内訳】")
            lines.append(detail)
    return "\n".join(lines)


def render_mistakes(record: RunRecord) -> str:
    """画像ごとに、誤検出（正解にないのに抽出したもの）と見落とし（抽出できなかったもの）を列挙する。"""
    lines: list[str] = []
    for r in record.results:
        expected = to_key_set(r.expected)
        for i, t in enumerate(r.trials, start=1):
            tag = f"{r.image}" + (f" #{i}" if len(r.trials) > 1 else "")
            if t.error:
                lines.append(f"- {tag}: エラー: {t.error}")
                continue
            predicted = to_key_set(t.predicted)
            fp = sort_keys(predicted - expected)
            fn = sort_keys(expected - predicted)
            if not fp and not fn:
                continue
            parts = []
            if fp:
                parts.append("誤検出 " + ", ".join(format_key(k) for k in fp))
            if fn:
                parts.append("見落とし " + ", ".join(format_key(k) for k in fn))
            lines.append(f"- {tag}: " + " / ".join(parts))
    return "\n".join(lines)


def render_comparison(base: RunRecord, target: RunRecord) -> str:
    """2つの実行記録を比べ、合計と画像ごとの F1 の変化を返す。"""
    lines: list[str] = []
    lines.append(f"比較元(A): {base.run_id}" + (f"（{base.note}）" if base.note else ""))
    lines.append(f"比較先(B): {target.run_id}" + (f"（{target.note}）" if target.note else ""))
    if base.system_prompt_sha256 != target.system_prompt_sha256:
        lines.append(
            f"  system プロンプトが変わっています: {base.system_prompt_sha256} → {target.system_prompt_sha256}"
        )
    if base.model != target.model:
        lines.append(f"  モデルが変わっています: {base.model} → {target.model}")
    lines.append("")

    a, b = total_score(base.results), total_score(target.results)
    lines.append(
        render_table(
            ["指標", "A", "B", "差"],
            [
                [name, _pct(fa), _pct(fb), f"{(fb - fa) * 100:+.1f}pt"]
                for name, fa, fb in [
                    ("適合率", a.precision, b.precision),
                    ("再現率", a.recall, b.recall),
                    ("F1", a.f1, b.f1),
                ]
            ],
        )
    )

    base_by_image = {r.image: r for r in base.results}
    rows: list[list[str]] = []
    for r in target.results:
        if r.image not in base_by_image:
            rows.append([r.image, "-", _pct(image_score(r).f1), "（新規）"])
            continue
        fa = image_score(base_by_image[r.image]).f1
        fb = image_score(r).f1
        mark = "↑" if fb > fa else "↓" if fb < fa else ""
        rows.append([r.image, _pct(fa), _pct(fb), f"{(fb - fa) * 100:+.1f}pt {mark}".rstrip()])
    lines.append("")
    lines.append("画像ごとの F1:")
    lines.append(render_table(["画像", "A", "B", "差"], rows))
    return "\n".join(lines)


def build_label_json(parts: list[PartItem]) -> str:
    """正解ラベルの下書き用 JSON（数量はすべて1、ソート済み）を返す。"""
    keys = sort_keys(to_key_set(parts))
    data: dict[str, Any] = {
        "parts": [{"runner": r, "number": n, "quantity": 1} for r, n in keys]
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
