"""스캔 품질(해상도·이진화·JPEG 압축)이 정합과 체크박스 판독에 주는 영향을 재현한다.

실제 스캔(raw/)을 설정별로 열화시킨 뒤 extract와 같은 경로로 읽고, 사람이 검토한 최종값
(output/responses_final.csv)과 비교한다. 결과는 표로만 출력하며 이미지는 저장하지 않는다.

    python tools/scan_quality.py raw output/responses_final.csv [--limit 100]
"""

import argparse
import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from survey_extract import omr  # noqa: E402
from survey_extract.align import Aligner  # noqa: E402
from survey_extract.imageio import load_gray  # noqa: E402
from survey_extract.layout import load_layout  # noqa: E402

# (이름, dpi, 이진화 여부, JPEG 품질 또는 None). 원본은 300dpi 1비트.
SETTINGS = [
    ("300dpi 원본(1비트)", 300, False, None),
    ("200dpi 그레이", 200, False, None),
    ("150dpi 그레이", 150, False, None),
    ("100dpi 그레이", 100, False, None),
    ("75dpi 그레이", 75, False, None),
    ("50dpi 그레이", 50, False, None),
    ("40dpi 그레이", 40, False, None),
    ("200dpi 1비트", 200, True, None),
    ("150dpi 1비트", 150, True, None),
    ("100dpi 1비트", 100, True, None),
    ("75dpi 1비트", 75, True, None),
    ("50dpi 1비트", 50, True, None),
    ("200dpi JPEG q90", 200, False, 90),
    ("200dpi JPEG q60", 200, False, 60),
    ("200dpi JPEG q30", 200, False, 30),
    ("150dpi JPEG q60", 150, False, 60),
]

_state = {}


def degrade(img: np.ndarray, dpi: int, binarize: bool, jpeg: int | None) -> np.ndarray:
    if dpi != 300:
        w = round(img.shape[1] * dpi / 300)
        img = cv2.resize(img, (w, round(img.shape[0] * w / img.shape[1])), interpolation=cv2.INTER_AREA)
    if binarize:
        img = np.where(img < 128, 0, 255).astype(np.uint8)
    if jpeg:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
        img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return img


def _init():
    layout = load_layout()
    _state["layout"], _state["aligner"] = layout, Aligner(layout.template)


def _job(args):
    path, setting = args
    layout, aligner = _state["layout"], _state["aligner"]
    img = degrade(load_gray(Path(path)), *setting[1:])
    res = aligner.align(img)
    q = omr.read_all(res.image, layout.template, layout.questions)
    return res.ok, [r.answer or "" for r in q]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("final_csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    layout = load_layout()
    labels = {q["id"]: {o["label"] for o in q["options"]} for q in layout.questions}
    qids = [q["id"] for q in layout.questions]
    with open(args.final_csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    rows = rows[: args.limit] if args.limit else rows
    paths = [str(Path(args.raw) / r["file"]) for r in rows]

    print("| 설정 | 정합 성공 | 판독 문항 | 자동 확정 정답 | 자동 확정 오답 | 사람 검토로 넘김 | 오답률(자동 확정 중) | 시간 |")
    print("|---|---|---|---|---|---|---|---|")
    with ProcessPoolExecutor(initializer=_init) as ex:
        for setting in SETTINGS:
            t0 = time.perf_counter()
            out = list(ex.map(_job, [(p, setting) for p in paths], chunksize=8))
            ok = sum(o for o, _ in out)
            good = bad = flagged = total = 0
            for r, (_, answers) in zip(rows, out):
                for qid, ans in zip(qids, answers):
                    truth = r[qid]
                    if truth not in labels[qid]:  # 무효/무응답 정답은 정확도 비교에서 제외
                        continue
                    total += 1
                    if not ans:
                        flagged += 1
                    elif ans == truth:
                        good += 1
                    else:
                        bad += 1
            auto = good + bad
            print(f"| {setting[0]} | {ok}/{len(rows)} | {total} | {good} | {bad} | {flagged} ({100 * flagged / total:.1f}%) "
                  f"| {100 * bad / max(auto, 1):.2f}% | {time.perf_counter() - t0:.0f}s |", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
