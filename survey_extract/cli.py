"""명령줄 진입점.

    python -m survey_extract extract <스캔폴더> -o <출력폴더> [--debug]

스캔폴더 안의 하위 폴더 이름을 학교명(그룹)으로 쓴다. 하위 폴더가 없으면 스캔폴더 이름을 쓴다.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2

from . import omr
from .align import Aligner
from .crops import build_sheets, debug_overlay, save_crops
from .imageio import find_images, load_gray, save_image
from .layout import DEFAULT_LAYOUT, load_layout
from .review import build_review, export_xlsx
from .transcribe import merge, prompt_for

HANDWRITING_FIELDS = ["grade", "kit_2", "kit_3", "q5"]


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
    stems = [p.stem for p in images]
    for n, path in enumerate(images, 1):
        group = path.parent.name if path.parent != src else src.name
        # ID는 파일명 기반이라 이미지를 더하거나 빼도 바뀌지 않는다. 다른 폴더에 같은 이름이 있으면 학교명을 붙인다.
        sid = path.stem if stems.count(path.stem) == 1 else f"{group}_{path.stem}"
        gray = load_gray(path)
        res = aligner.align(gray)
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
        save_original(gray, row["rotated_180"], out, sid)
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


def save_original(gray, flipped: bool, out: Path, sid: str, width: int = 1100) -> None:
    """검토용 원본 사본. 거꾸로 스캔된 것은 180° 돌려 바로 세운다(raw 원본은 건드리지 않는다)."""
    if flipped:
        gray = cv2.rotate(gray, cv2.ROTATE_180)
    h = round(gray.shape[0] * width / gray.shape[1])
    save_image(out / "originals" / f"{sid}.jpg", cv2.resize(gray, (width, h), interpolation=cv2.INTER_AREA))


def cmd_prompt(args) -> int:
    manifest = json.loads((Path(args.output) / "sheets" / "manifest.json").read_text(encoding="utf-8"))
    done = {p.stem for p in (Path(args.output) / "transcripts").glob("*.json")}
    todo = [s for s in manifest if s not in done]
    for s in ([args.sheet] if args.sheet else todo[:1]):
        print(prompt_for(s, manifest))
    print(f"(판독 대기 시트 {len(todo)}/{len(manifest)}장)")
    return 0


def cmd_merge(args) -> int:
    r = merge(Path(args.output))
    print(f"병합: {r['cells']}칸 (확신도 low {r['low']}칸), 대기 시트 {len(r['pending'])}장")
    for e in r["errors"]:
        print("오류:", e, file=sys.stderr)
    return 1 if r["errors"] else 0


def cmd_review(args) -> int:
    out = Path(args.output)
    path = build_review(out, load_layout(args.layout).questions)
    print(f"검토 화면: {path}\n브라우저로 열어 검토한 뒤 '결과 CSV 다운로드'로 받은 review_decisions.csv를 {out}에 두세요.")
    return 0


def cmd_export(args) -> int:
    out = Path(args.output)
    r = export_xlsx(out, load_layout(args.layout).questions, Path(args.decisions) if args.decisions else out / "review_decisions.csv")
    print(f"저장: {r['path']} ({r['rows']}행, 검토 중 수정 {r['edited']}건)")
    if r["pending"]:
        print(f"미검토 {len(r['pending'])}장: {', '.join(r['pending'][:10])}{' ...' if len(r['pending']) > 10 else ''}", file=sys.stderr)
        return 1
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

    m = sub.add_parser("merge", help="손글씨 판독 결과(transcripts/*.json)를 responses.csv에 병합")
    m.add_argument("-o", "--output", default="output")
    m.set_defaults(func=cmd_merge)

    t = sub.add_parser("prompt", help="Claude에게 줄 시트 판독 지침 출력")
    t.add_argument("-o", "--output", default="output")
    t.add_argument("--sheet", help="시트 이름(기본: 아직 판독 안 한 첫 시트)")
    t.set_defaults(func=cmd_prompt)

    v = sub.add_parser("review", help="검토용 review.html 생성")
    v.add_argument("output", nargs="?", default="output")
    v.add_argument("--layout", default=DEFAULT_LAYOUT)
    v.set_defaults(func=cmd_review)

    x = sub.add_parser("export", help="검토 결과를 합쳐 responses_final.xlsx 생성")
    x.add_argument("output", nargs="?", default="output")
    x.add_argument("--layout", default=DEFAULT_LAYOUT)
    x.add_argument("--decisions", help="review_decisions.csv 경로(기본: <출력폴더>/review_decisions.csv)")
    x.set_defaults(func=cmd_export)

    args = p.parse_args(argv)
    return args.func(args)
