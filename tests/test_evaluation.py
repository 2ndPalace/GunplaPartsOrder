"""Tests for accuracy evaluation utilities and CLI."""

import sys
from unittest.mock import patch

import pytest
from PIL import Image

import evaluate
from src.evaluation import (
    ImageResult,
    RunRecord,
    TrialResult,
    build_label_json,
    find_images,
    is_stable,
    load_label,
    load_run,
    render_comparison,
    render_report,
    save_run,
    score_trial,
    total_score,
)
from src.models import PartItem


def P(runner: str, number: str) -> PartItem:
    return PartItem(runner=runner, number=number)


def make_record(run_id: str, results: list[ImageResult], note: str = "") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        created_at="2026-10-16T00:00:00",
        note=note,
        model="gemini-2.5-flash",
        temperature=0.1,
        system_prompt_source="default",
        system_prompt_sha256="aaaaaaaaaaaa",
        user_prompt_source="default",
        user_prompt_sha256="bbbbbbbbbbbb",
        system_prompt="sys",
        user_prompt="user",
        repeat=1,
        results=results,
    )


def test_score_trial_counts_fp_and_fn():
    """正規化後の (runner, number) で比べ、重複と数量は無視すること"""
    expected = [P("A", "6"), P("A", "26"), P("B1", "12")]
    trial = TrialResult(predicted=[P("ａ", "6"), P("A", "6"), P("A", "26"), P("C", "3")])
    s = score_trial(expected, trial)
    assert (s.tp, s.fp, s.fn) == (2, 1, 1)
    assert s.precision == pytest.approx(2 / 3)
    assert s.recall == pytest.approx(2 / 3)
    assert s.f1 == pytest.approx(2 / 3)


def test_error_trial_counts_all_expected_as_missed():
    s = score_trial([P("A", "1"), P("A", "2")], TrialResult(error="boom"))
    assert (s.tp, s.fp, s.fn) == (0, 0, 2)
    assert s.f1 == 0.0


def test_total_score_is_micro_average():
    results = [
        ImageResult(image="p1.jpg", expected=[P("A", "1")], trials=[TrialResult(predicted=[P("A", "1")])]),
        ImageResult(
            image="p2.jpg",
            expected=[P("B", "1"), P("B", "2")],
            trials=[TrialResult(predicted=[P("B", "1"), P("X", "9")])],
        ),
    ]
    s = total_score(results)
    assert (s.tp, s.fp, s.fn) == (2, 1, 1)


def test_is_stable():
    expected = [P("A", "1")]
    same = ImageResult(
        image="p.jpg",
        expected=expected,
        trials=[TrialResult(predicted=[P("A", "1")]), TrialResult(predicted=[P("A", "1"), P("A", "1")])],
    )
    diff = ImageResult(
        image="p.jpg",
        expected=expected,
        trials=[TrialResult(predicted=[P("A", "1")]), TrialResult(predicted=[P("A", "2")])],
    )
    assert is_stable(same)
    assert not is_stable(diff)


def test_find_images_filters_extension_and_only(tmp_path):
    for name in ["p1.jpg", "p2.PNG", "notes.txt", "p3.jpeg"]:
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in find_images(tmp_path)] == ["p1.jpg", "p2.PNG", "p3.jpeg"]
    assert [p.name for p in find_images(tmp_path, only=["p3"])] == ["p3.jpeg"]
    assert find_images(tmp_path / "missing") == []


def test_label_roundtrip(tmp_path):
    """下書きラベルは重複を除き、自然順に並び、読み直せること"""
    path = tmp_path / "p1.json"
    path.write_text(build_label_json([P("B1", "12"), P("A", "26"), P("A", "6"), P("A", "6")]), encoding="utf-8")
    assert [(p.runner, p.number) for p in load_label(path)] == [("A", "6"), ("A", "26"), ("B1", "12")]


def test_load_run_resolves_latest(tmp_path):
    save_run(make_record("20261016-100000_a", []), tmp_path)
    save_run(make_record("20261016-110000_b", []), tmp_path)
    assert load_run("latest", tmp_path).run_id == "20261016-110000_b"
    assert load_run("latest~1", tmp_path).run_id == "20261016-100000_a"
    assert load_run("20261016-10", tmp_path).run_id == "20261016-100000_a"
    with pytest.raises(FileNotFoundError):
        load_run("latest~5", tmp_path)


def test_render_report_and_comparison():
    base = make_record(
        "r1",
        [ImageResult(image="p1.jpg", expected=[P("A", "1"), P("A", "2")], trials=[TrialResult(predicted=[P("A", "1"), P("S", "4")])])],
    )
    target = make_record(
        "r2",
        [ImageResult(image="p1.jpg", expected=[P("A", "1"), P("A", "2")], trials=[TrialResult(predicted=[P("A", "1"), P("A", "2")])])],
    )
    report = render_report(base)
    assert "誤検出 S-4" in report
    assert "見落とし A-2" in report
    comparison = render_comparison(base, target)
    assert "+50.0pt" in comparison


def test_cli_run_and_rescore(tmp_path, monkeypatch, capsys):
    """run で記録を保存し、ラベルを直したあと rescore で API を呼ばずに採点し直せること"""
    images, labels, runs = tmp_path / "images", tmp_path / "labels", tmp_path / "runs"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (20, 20), "white").save(images / "p1.jpg")
    Image.new("RGB", (20, 20), "white").save(images / "p2.jpg")  # ラベルなし → 対象外
    (labels / "p1.json").write_text(build_label_json([P("A", "1"), P("A", "2")]), encoding="utf-8")

    dirs = ["--images-dir", str(images), "--labels-dir", str(labels), "--runs-dir", str(runs)]

    with patch("evaluate.GunplaPartsExtractor") as mock_cls:
        mock_cls.return_value.extract_raw_parts.return_value = [P("A", "1"), P("S", "4")]
        monkeypatch.setattr(sys, "argv", ["evaluate.py", "run", *dirs, "--repeat", "2", "--note", "base"])
        assert evaluate.main() == 0
        assert mock_cls.return_value.extract_raw_parts.call_count == 2

    out = capsys.readouterr().out
    assert "対象外: p2.jpg" in out
    record = load_run("latest", runs)
    assert record.repeat == 2
    assert total_score(record.results).f1 == pytest.approx(0.5)

    # 正解ラベルを直す（S-4 も正解だった）→ API なしで再採点
    (labels / "p1.json").write_text(build_label_json([P("A", "1"), P("S", "4")]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "rescore", "latest", *dirs])
    assert evaluate.main() == 0
    rescored = load_run("latest", runs)
    assert rescored.rescored_from == record.run_id
    assert total_score(rescored.results).f1 == 1.0
