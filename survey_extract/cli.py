"""명령줄 진입점.

    python -m survey_extract extract <스캔폴더> -o <출력폴더> [--debug]

스캔폴더 안의 하위 폴더 이름을 학교명(그룹)으로 쓴다. 하위 폴더가 없으면 스캔폴더 이름을 쓴다.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

from . import omr
from .align import Aligner
from .crops import build_sheets, debug_overlay, save_crops
from .imageio import find_images, load_gray, save_image
from .layout import DEFAULT_LAYOUT, load_layout

HANDWRITING_FIELDS = ["grade", "name", "kit_2", "kit_3", "q5"]


def cmd_extract(args) -> int:
    layout = load_layout(args.layout)
    aligner = Aligner(layout.template)
    src, out = Path(args.input), Path(args.output)
    images = find_images(src)
    if not images:
        print(f"이미지가 없습니다: {src}", file=sys.stderr)
        return 1

    rows = []
    t0 = time.perf_counter()
    for n, path in enumerate(images, 1):
        sid = f"{n:04d}"
        group = path.parent.name if path.parent != src else src.name
        res = aligner.align(load_gray(path))
        qres = omr.read_all(res.image, layout.template, layout.questions)

        row = {
            "id": sid,
            "school": group,
            "file": path.relative_to(src).as_posix(),
            "align_ok": res.ok,
            "align_inliers": res.inliers,
            "rotated_180": abs(abs(res.rotation) - 180) < 45,
        }
        flags = [] if res.ok else ["align_fail"]
        for r in qres:
            row[r.qid] = r.answer or ""
            row[f"{r.qid}_candidate"] = r.candidate or ""
            row[f"{r.qid}_scores"] = " ".join(map(str, r.scores))
            flags += [f"{r.qid}:{f}" for f in r.flags]
        for f in HANDWRITING_FIELDS:
            row[f] = ""
        row.update(save_crops(res.image, layout.fields, out, sid))
        row["omr_flags"] = ";".join(flags)
        row["omr_status"] = "needs_review" if (not res.ok or any(r.needs_review for r in qres)) else "auto"
        rows.append(row)

        if args.debug:
            save_image(out / "debug" / f"{sid}.jpg", debug_overlay(res.image, layout.questions, layout.fields, qres))
        print(f"\r[{n}/{len(images)}] {path.name}", end="", flush=True)
    elapsed = time.perf_counter() - t0
    print()

    _write_csv(out / "responses.csv", rows)
    sheets = build_sheets(out, rows, layout.fields, per_sheet=args.per_sheet)

    n_review = sum(r["omr_status"] == "needs_review" for r in rows)
    n_q = len(rows) * len(layout.questions)
    n_q_review = sum(len([f for f in r["omr_flags"].split(";") if f]) for r in rows)
    print(f"처리: {len(rows)}장, {elapsed:.1f}초 (장당 {1000 * elapsed / len(rows):.0f}ms)")
    print(f"체크박스 검토 필요: {n_review}장 / 플래그 {n_q_review}건 (전체 문항 {n_q}개)")
    print(f"결과: {out / 'responses.csv'}")
    print(f"손글씨 판독용 시트: {len(sheets)}장 → {out / 'sheets'}")
    return 0


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Windows Excel에서 한글이 깨지지 않도록 BOM을 붙인다.
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="survey_extract", description="설문지 스캔 이미지 응답 추출기")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="스캔 이미지에서 체크박스 판독 + 손글씨 크롭")
    e.add_argument("input", help="스캔 이미지 폴더(하위 폴더 = 학교/그룹)")
    e.add_argument("-o", "--output", default="output", help="출력 폴더 (기본: output)")
    e.add_argument("--layout", default=DEFAULT_LAYOUT, help="양식 레이아웃 JSON")
    e.add_argument("--debug", action="store_true", help="판정 결과 오버레이 이미지 저장")
    e.add_argument("--per-sheet", type=int, default=12, help="손글씨 묶음 시트당 학생 수")
    e.set_defaults(func=cmd_extract)

    args = p.parse_args(argv)
    return args.func(args)
