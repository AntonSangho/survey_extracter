"""처리 단계별 시간 측정 + GPU(OpenCV CUDA) 사용 가능 여부 확인.

    python tools/benchmark.py <스캔폴더> [--limit 100]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from survey_extract import omr  # noqa: E402
from survey_extract.align import Aligner  # noqa: E402
from survey_extract.imageio import find_images, load_gray  # noqa: E402
from survey_extract.layout import load_layout  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    layout = load_layout()
    aligner = Aligner(layout.template)
    images = find_images(Path(args.input))
    if args.limit:
        images = images[: args.limit]

    t = {"load": 0.0, "align": 0.0, "omr": 0.0}
    for path in images:
        t0 = time.perf_counter()
        img = load_gray(path)
        t1 = time.perf_counter()
        res = aligner.align(img)
        t2 = time.perf_counter()
        omr.read_all(res.image, layout.template, layout.questions)
        t3 = time.perf_counter()
        t["load"] += t1 - t0
        t["align"] += t2 - t1
        t["omr"] += t3 - t2

    n = len(images)
    total = sum(t.values())
    print(f"OpenCV {cv2.__version__}, CPU 스레드 {cv2.getNumThreads()}")
    print(f"이미지 {n}장, 합계 {total:.1f}초, 장당 {1000 * total / n:.0f}ms")
    for k, v in t.items():
        print(f"  {k:6s} {1000 * v / n:6.1f}ms/장 ({100 * v / total:4.1f}%)")

    try:
        cuda = cv2.cuda.getCudaEnabledDeviceCount()
    except AttributeError:
        cuda = 0
    print(f"OpenCV CUDA 장치 수: {cuda} " + ("" if cuda else "(pip 배포판 OpenCV는 CUDA 미포함)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
