"""템플릿에 가상 응답을 합성해 샘플 스캔과 정답표(truth.csv)를 만든다. 모든 데이터는 가상이다.

    python tools/make_samples.py samples/scans [--font /path/to/handwriting.ttf]

사례: 정방향, 180° 뒤집힘, 기울임, 이중 체크, 무응답, 지운 흔적, X 취소, 자유의견 없음.
"""

import argparse
import csv
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from survey_extract.layout import load_layout  # noqa: E402

DEFAULT_FONT = "NanumBarunpen"

# (파일 번호, 학교, 사례, q1~q4 정답(사람이 최종 판정한 값), 학년, 2교시, 3교시, 자유의견, 스캔 변형)
# 사례 이름은 tests/test_samples.py가 기대 동작을 정하는 데 쓴다.
CASES = [
    (1, "가상초A", "clean", ["매우 만족", "쉬웠다", "매우 그렇다", "네"], "5", "마술봉", "자벌래", "재미있었어요. 또 하고 싶어요.", {}),
    (2, "가상초A", "clean", ["만족", "보통", "그렇다", "네"], "5", "스마트 워치", "피노키오", "만든 것을 가져가고 싶어요.", {}),
    (3, "가상초A", "clean", ["매우 만족", "매우 쉬웠다", "매우 그렇다", "네"], "6", "노래하는 케익", "인사하는 강아지", "", {}),
    (4, "가상초A", "flipped", ["보통", "어려웠다", "보통", "잘 모르겠음"], "6", "메시지키링", "메롱하는 개구리", "설명이 길었어요.", {"flip": True}),
    (5, "가상초A", "flipped", ["매우 만족", "쉬웠다", "그렇다", "네"], "4", "인사하는 강아지", "노래하는 케익", "선생님이 친절했어요!", {"flip": True}),
    (6, "가상초A", "tilted", ["만족", "쉬웠다", "매우 그렇다", "네"], "4", "자벌래", "마술봉", "재밌었다", {"angle": 1.4}),
    (7, "가상초B", "double", ["만족", "보통", "그렇다", "네"], "5", "피노키오", "스마트 워치", "다음에도 하고 싶다.", {"double": 1}),
    (8, "가상초B", "blank", ["매우 만족", "쉬웠다", "", "아니오"], "5", "메롱하는 개구리", "메시지키링", "", {"skip": 2}),
    (9, "가상초B", "scribble", ["불만족", "보통", "그렇다", "네"], "6", "마술봉", "자벌래", "시간이 부족했어요.", {"scribble": 0}),
    (10, "가상초B", "noisy", ["매우 만족", "매우 쉬웠다", "매우 그렇다", "네"], "6", "스마트 워치", "피노키오", "만들기가 재미있었다.", {"flip": True, "angle": -1.0, "line": True}),
    (11, "가상초B", "x_cancel", ["만족", "쉬웠다", "보통", "아니오"], "4", "노래하는 케익", "인사하는 강아지", "", {"x_cancel": 3}),
    (12, "가상초B", "clean", ["보통", "보통", "아니다", "잘 모르겠음"], "5", "자벌래", "마술봉", "없음", {}),
]


def find_font(name: str) -> str:
    if Path(name).exists():
        return name
    out = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True)
    if out.returncode or not out.stdout:
        raise SystemExit(f"폰트를 찾을 수 없습니다: {name} (--font로 손글씨풍 한글 폰트 경로를 지정하세요)")
    return out.stdout


def draw_check(d: ImageDraw.ImageDraw, box, rng: random.Random, width: int = 7):
    x, y, w, h = box
    j = lambda v: v + rng.uniform(-3, 3)  # noqa: E731
    pts = [(j(x + 0.05 * w), j(y + 0.55 * h)), (j(x + 0.4 * w), j(y + 1.0 * h)), (j(x + 1.25 * w), j(y - 0.55 * h))]
    d.line(pts, fill=0, width=width, joint="curve")


def draw_scribble(d: ImageDraw.ImageDraw, box, rng: random.Random):
    x, y, w, h = box
    pts = [(x - 15 + i * 9, y - 12 + (i % 2) * (h + 24) + rng.uniform(-3, 3)) for i in range(9)]
    d.line(pts, fill=0, width=5)


def draw_x(d: ImageDraw.ImageDraw, box):
    x, y, w, h = box
    d.line([(x - 2, y - 2), (x + w + 2, y + h + 2)], fill=0, width=6)
    d.line([(x + w + 2, y - 2), (x - 2, y + h + 2)], fill=0, width=6)


def write_text(img: Image.Image, roi, text: str, font_path: str, rng: random.Random, size: int | None = None):
    if not text:
        return
    x, y, w, h = roi
    multiline = h > 200
    size = size or (62 if multiline else int(h * 0.62))
    font = ImageFont.truetype(font_path, size)
    layer = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(layer)
    if multiline:  # 자유의견: 칸 폭에 맞춰 줄바꿈
        lines, cur = [], ""
        for ch in text:
            if d.textlength(cur + ch, font=font) > w - 30:
                lines.append(cur)
                cur = ""
            cur += ch
        lines.append(cur)
        for i, line in enumerate(lines[:4]):
            d.text((15 + rng.uniform(0, 12), 6 + i * (size + 62)), line, font=font, fill=0)
    else:
        tw = d.textlength(text, font=font)
        d.text((max(10, (w - tw) / 2 + rng.uniform(-30, 30)), (h - size) / 2 - 8), text, font=font, fill=0)
    layer = layer.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, fillcolor=255)
    region = img.crop((x, y, x + w, y + h))
    img.paste(Image.fromarray(np.minimum(np.array(region), np.array(layer))), (x, y))


def make(case, layout, font_path: str) -> Image.Image:
    num, _, _, answers, grade, k2, k3, q5, opt = case
    rng = random.Random(num)
    img = Image.fromarray(layout.template).convert("L")
    d = ImageDraw.Draw(img)
    for qi, (q, ans) in enumerate(zip(layout.questions, answers)):
        boxes = {o["label"]: o["box"] for o in q["options"]}
        if qi == opt.get("skip"):
            continue
        if qi == opt.get("scribble"):  # 먼저 다른 칸에 체크하고 낙서로 지운 뒤 정답에 체크
            wrong = next(o["box"] for o in q["options"] if o["label"] != ans)
            draw_check(d, wrong, rng)
            draw_scribble(d, wrong, rng)
        if qi == opt.get("x_cancel"):  # 다른 칸에 체크했다가 X로 취소
            wrong = next(o["box"] for o in q["options"] if o["label"] != ans)
            draw_check(d, wrong, rng)
            draw_x(d, wrong)
        draw_check(d, boxes[ans], rng)
        if qi == opt.get("double"):  # 진짜 두 개 체크(사람이 첫 번째를 택함)
            other = next(o["box"] for o in q["options"] if o["label"] != ans)
            draw_check(d, other, rng)
    fields = {f["id"]: f["roi"] for f in layout.fields}
    for fid, text in (("grade", grade), ("kit_2", k2), ("kit_3", k3)):
        write_text(img, fields[fid], text, font_path, rng)
    write_text(img, fields["q5"], q5, font_path, rng)

    if opt.get("angle"):
        img = img.rotate(opt["angle"], resample=Image.BICUBIC, fillcolor=255)
    shift = (rng.randint(-14, 14), rng.randint(-14, 14))
    img = img.transform(img.size, Image.AFFINE, (1, 0, shift[0], 0, 1, shift[1]), fillcolor=255)
    if opt.get("line"):  # 스캐너 세로줄 노이즈
        x = rng.randint(200, img.width - 200)
        ImageDraw.Draw(img).line([(x, 0), (x + 3, img.height)], fill=0, width=3)
    if opt.get("flip"):
        img = img.rotate(180)
    return img.point(lambda v: 255 if v > 128 else 0).convert("1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", help="샘플 스캔 출력 폴더(하위에 학교별 폴더 생성)")
    ap.add_argument("--font", default=DEFAULT_FONT)
    args = ap.parse_args()
    layout = load_layout()
    font = find_font(args.font)
    out = Path(args.out)
    rows = []
    for case in CASES:
        num, school, kind, answers, grade, k2, k3, q5, _ = case
        rel = Path(school) / f"sample_{num:03d}.png"
        (out / school).mkdir(parents=True, exist_ok=True)
        make(case, layout, font).save(out / rel, dpi=(300, 300), optimize=True)
        rows.append({"file": rel.as_posix(), "case": kind, **{q["id"]: a for q, a in zip(layout.questions, answers)},
                     "grade": grade, "kit_2": k2, "kit_3": k3, "q5": q5})
    with (out.parent / "truth.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)}장 생성: {out} / 정답표: {out.parent / 'truth.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
