"""Accuracy evaluation CLI for Gunpla Parts Order Extractor.

使い方の例:
    python evaluate.py init-labels             # 正解ラベルの下書きを作る（あとで手で直す）
    python evaluate.py run --note baseline     # 全画像を評価して記録する
    python evaluate.py run --system-prompt prompts/system.md --note v2
    python evaluate.py compare                 # 直前の2回を比べる
    python evaluate.py rescore latest          # 正解ラベルを直したあと、API を呼ばずに採点し直す
"""

import argparse
import sys
import time
from pathlib import Path

# Windows環境のコンソール文字化け対策（UTF-8設定）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.config import settings
from src.evaluation import (
    DEFAULT_IMAGES_DIR,
    DEFAULT_LABELS_DIR,
    DEFAULT_RUNS_DIR,
    ImageResult,
    RunRecord,
    TrialResult,
    build_label_json,
    find_images,
    label_path_for,
    load_label,
    load_run,
    new_run_id,
    prompt_hash,
    render_comparison,
    render_report,
    render_table,
    save_run,
    total_score,
)
from src.extractor import SYSTEM_INSTRUCTION, USER_PROMPT, GunplaPartsExtractor

PROMPTS_DIR = settings.PROJECT_ROOT / "prompts"


def add_dir_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES_DIR, help="評価用画像のフォルダ")
    p.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS_DIR, help="正解ラベルのフォルダ")
    p.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR, help="実行記録の保存先フォルダ")


def add_extractor_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=settings.DEFAULT_MODEL, help="使用するGeminiモデル名")
    p.add_argument("--temperature", type=float, default=0.1, help="生成時の温度（既定: 0.1）")
    p.add_argument("--system-prompt", type=Path, default=None, help="システムプロンプトのファイル（省略時は src/extractor.py の既定）")
    p.add_argument("--user-prompt", type=Path, default=None, help="ユーザープロンプトのファイル（省略時は src/extractor.py の既定）")
    p.add_argument("--only", nargs="+", default=None, metavar="NAME", help="この名前（拡張子なし）の画像だけを対象にする")
    p.add_argument("--interval", type=float, default=0.0, help="API 呼び出しの間に空ける秒数（回数制限対策）")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ガンプラ説明書のパーツ番号抽出の精度を、正解ラベルと比べて評価するツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="画像を抽出して正解ラベルと比べ、結果を記録する")
    add_dir_options(p_run)
    add_extractor_options(p_run)
    p_run.add_argument("--repeat", type=int, default=1, help="1枚あたりの試行回数（結果のばらつきを見る）")
    p_run.add_argument("--note", default="", help="実行記録に付けるメモ（何を変えたか）")
    p_run.add_argument("-q", "--quiet", action="store_true", help="間違いの内訳を表示しない")

    p_init = sub.add_parser("init-labels", help="正解ラベルがない画像を抽出し、ラベルの下書きを作る")
    add_dir_options(p_init)
    add_extractor_options(p_init)
    p_init.add_argument("--overwrite", action="store_true", help="既存の正解ラベルも上書きする")

    p_rescore = sub.add_parser("rescore", help="過去の実行結果を、今の正解ラベルで採点し直す（API は呼ばない）")
    add_dir_options(p_rescore)
    p_rescore.add_argument("run", nargs="?", default="latest", help="実行ID・ファイルパス・latest・latest~1 など")
    p_rescore.add_argument("--note", default="", help="新しい実行記録に付けるメモ")

    p_report = sub.add_parser("report", help="過去の実行記録を表示する")
    add_dir_options(p_report)
    p_report.add_argument("run", nargs="?", default="latest", help="実行ID・ファイルパス・latest・latest~1 など")

    p_cmp = sub.add_parser("compare", help="2つの実行記録を比べる")
    add_dir_options(p_cmp)
    p_cmp.add_argument("base", nargs="?", default="latest~1", help="比較元（既定: 1つ前の実行）")
    p_cmp.add_argument("target", nargs="?", default="latest", help="比較先（既定: 最新の実行）")

    p_list = sub.add_parser("list", help="実行記録の一覧を表示する")
    add_dir_options(p_list)

    p_export = sub.add_parser("export-prompts", help="既定のプロンプトを prompts/ に書き出す（改良の出発点にする）")
    p_export.add_argument("--overwrite", action="store_true", help="既存のファイルも上書きする")

    return parser.parse_args()


def read_prompt(path: Path | None, default: str) -> tuple[str, str]:
    """(プロンプト本文, 出どころの表示名) を返す。"""
    if path is None:
        return default, "default"
    return path.read_text(encoding="utf-8"), str(path)


def build_extractor(args: argparse.Namespace) -> tuple[GunplaPartsExtractor, dict]:
    system_prompt, system_src = read_prompt(args.system_prompt, SYSTEM_INSTRUCTION)
    user_prompt, user_src = read_prompt(args.user_prompt, USER_PROMPT)
    extractor = GunplaPartsExtractor(
        model_name=args.model,
        system_instruction=system_prompt,
        user_prompt=user_prompt,
        temperature=args.temperature,
    )
    meta = {
        "model": args.model,
        "temperature": args.temperature,
        "system_prompt_source": system_src,
        "system_prompt_sha256": prompt_hash(system_prompt),
        "user_prompt_source": user_src,
        "user_prompt_sha256": prompt_hash(user_prompt),
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }
    return extractor, meta


def run_trial(extractor: GunplaPartsExtractor, image: Path) -> TrialResult:
    started = time.perf_counter()
    try:
        parts = extractor.extract_raw_parts(image)
        return TrialResult(predicted=parts, elapsed_sec=round(time.perf_counter() - started, 2))
    except Exception as e:  # 1枚の失敗で評価全体を止めない
        return TrialResult(error=f"{type(e).__name__}: {e}", elapsed_sec=round(time.perf_counter() - started, 2))


def cmd_run(args: argparse.Namespace) -> int:
    images = find_images(args.images_dir, args.only)
    if not images:
        print(f"[ERROR] 評価用画像がありません: {args.images_dir}", file=sys.stderr)
        return 1

    labeled = [img for img in images if label_path_for(img, args.labels_dir).is_file()]
    missing = [img for img in images if img not in labeled]
    for img in missing:
        print(f"[SKIP] 正解ラベルがないため対象外: {img.name}（python evaluate.py init-labels で下書きを作れます）")
    if not labeled:
        print("[ERROR] 正解ラベルのある画像が1枚もありません。", file=sys.stderr)
        return 1

    extractor, meta = build_extractor(args)
    total_calls = len(labeled) * args.repeat
    print(f"[INFO] {len(labeled)} 枚 × {args.repeat} 回 = {total_calls} 回 Gemini API を呼び出します（モデル: {args.model}）")

    results: list[ImageResult] = []
    call = 0
    for img in labeled:
        expected = load_label(label_path_for(img, args.labels_dir))
        trials: list[TrialResult] = []
        for _ in range(args.repeat):
            if call and args.interval:
                time.sleep(args.interval)
            call += 1
            trial = run_trial(extractor, img)
            status = f"エラー: {trial.error}" if trial.error else f"{len(trial.predicted)} 件"
            print(f"  [{call}/{total_calls}] {img.name}: {status}（{trial.elapsed_sec}秒）")
            trials.append(trial)
        results.append(ImageResult(image=img.name, expected=expected, trials=trials))

    record = RunRecord(
        run_id=new_run_id(args.note),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        note=args.note,
        repeat=args.repeat,
        results=results,
        **meta,
    )
    path = save_run(record, args.runs_dir)
    print()
    print(render_report(record, verbose=not args.quiet))
    print()
    print(f"[SUCCESS] 実行記録を保存しました: {path}")
    return 0


def cmd_init_labels(args: argparse.Namespace) -> int:
    images = find_images(args.images_dir, args.only)
    if not images:
        print(f"[ERROR] 評価用画像がありません: {args.images_dir}", file=sys.stderr)
        return 1
    targets = [
        img for img in images if args.overwrite or not label_path_for(img, args.labels_dir).is_file()
    ]
    if not targets:
        print("[INFO] すべての画像に正解ラベルがあります（作り直すときは --overwrite）。")
        return 0

    extractor, _ = build_extractor(args)
    args.labels_dir.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(targets):
        if i and args.interval:
            time.sleep(args.interval)
        trial = run_trial(extractor, img)
        if trial.error:
            print(f"[ERROR] {img.name}: {trial.error}", file=sys.stderr)
            continue
        out = label_path_for(img, args.labels_dir)
        out.write_text(build_label_json(trial.predicted), encoding="utf-8")
        print(f"[DRAFT] {img.name} → {out}（{len(trial.predicted)} 件）")

    print()
    print("[NOTE] これは AI が読み取った「下書き」です。説明書と見比べて、間違いを手で直してから評価してください。")
    return 0


def cmd_rescore(args: argparse.Namespace) -> int:
    old = load_run(args.run, args.runs_dir)
    results: list[ImageResult] = []
    for r in old.results:
        label = args.labels_dir / f"{Path(r.image).stem}.json"
        expected = load_label(label) if label.is_file() else r.expected
        results.append(ImageResult(image=r.image, expected=expected, trials=r.trials))

    note = args.note or (f"{old.note} (rescored)" if old.note else "rescored")
    record = old.model_copy(
        update={
            "run_id": new_run_id(note),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": note,
            "results": results,
            "rescored_from": old.run_id,
        }
    )
    path = save_run(record, args.runs_dir)
    print(render_report(record))
    print()
    print(f"[SUCCESS] 再採点の結果を保存しました: {path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    print(render_report(load_run(args.run, args.runs_dir)))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    base = load_run(args.base, args.runs_dir)
    target = load_run(args.target, args.runs_dir)
    print(render_comparison(base, target))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    runs = sorted(args.runs_dir.glob("*.json"))
    if not runs:
        print("[INFO] 実行記録はまだありません。")
        return 0
    rows = []
    for path in runs:
        rec = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        s = total_score(rec.results)
        rows.append(
            [rec.run_id, rec.model, rec.system_prompt_sha256, str(len(rec.results)), str(rec.repeat), f"{s.f1 * 100:.1f}%", rec.note]
        )
    print(render_table(["実行ID", "モデル", "system", "画像", "試行", "F1", "メモ"], rows))
    return 0


def cmd_export_prompts(args: argparse.Namespace) -> int:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in [("system.md", SYSTEM_INSTRUCTION), ("user.md", USER_PROMPT)]:
        path = PROMPTS_DIR / name
        if path.exists() and not args.overwrite:
            print(f"[SKIP] すでにあります: {path}（上書きするときは --overwrite）")
            continue
        path.write_text(text, encoding="utf-8")
        print(f"[EXPORT] {path}")
    return 0


COMMANDS = {
    "run": cmd_run,
    "init-labels": cmd_init_labels,
    "rescore": cmd_rescore,
    "report": cmd_report,
    "compare": cmd_compare,
    "list": cmd_list,
    "export-prompts": cmd_export_prompts,
}


def main() -> int:
    args = parse_arguments()
    try:
        return COMMANDS[args.command](args)
    except (ValueError, FileNotFoundError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
