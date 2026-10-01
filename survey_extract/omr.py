"""체크박스 판독(OMR).

학생들은 체크(✓)를 박스 안이 아니라 박스 위에 걸쳐 그리는 경우가 많다.
그래서 박스 내부 픽셀만 세지 않고, 문항 열(column)에서 템플릿에 없는 새 잉크를
연결 성분으로 묶은 뒤 각 성분의 "가장 아래 지점"(체크의 꼭짓점)이 속한 박스에 배정한다.

판정 규칙
- 1등 점수 < BLANK_PX                         → blank(무응답, 검토)
- 2등 < 1등 × SECOND_RATIO 이고 2등 < MARK_PX → 1등을 자동 확정
- 2등 ≥ MARK_PX 이고 2등 ≥ 1등 × SECOND_RATIO → multi(이중 체크, 검토)
- 그 밖                                       → low_margin(애매, 검토)
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

INK_THRESHOLD = 128  # 이보다 어두우면 잉크
MIN_COMPONENT_PX = 40  # 이보다 작은 성분은 먼지/점 노이즈로 무시
BLANK_PX = 40  # 1등 점수가 이보다 작으면 무응답
MARK_PX = 120  # 2등 점수가 이 이상이면 두 번째 표시로 본다
SECOND_RATIO = 0.3  # 2등/1등 비율이 이 이상이면 자동 확정하지 않음
FILLED_DENSITY = 0.6  # 박스 내부가 이만큼 칠해지면 "칠한 박스"(지운 흔적일 수 있음)

# 박스 기준 여백(px, 300dpi)
COL_LEFT, COL_RIGHT = 70, 80  # 문항 열 ROI
ANCHOR_ABOVE, ANCHOR_BELOW = 30, 20  # 꼭짓점이 이 범위에 있으면 그 박스에 배정
WIN_X, WIN_ABOVE, WIN_BELOW = 30, 40, 15  # 배정된 성분의 점수를 세는 창
TIGHT = 4  # 다른 박스 "안"을 지나가는지 볼 때의 여백
JOIN_PX = 5  # 끊긴 획을 잇는 팽창 크기
BOX_RING = 6  # 체크박스 테두리 ±이 범위의 잉크는 무시(인쇄 굵기·정합 오차 흡수)

REVIEW_FLAGS = {"blank", "multi", "low_margin"}


@dataclass
class QuestionResult:
    qid: str
    answer: str | None  # 자동 확정 답(검토 필요 시 None)
    candidate: str | None  # 가장 점수가 높은 선택지
    scores: list[int]  # 선택지별 점수(배정된 잉크 픽셀 수)
    flags: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(f in REVIEW_FLAGS for f in self.flags)


def new_ink_mask(aligned: np.ndarray, template: np.ndarray, questions: list[dict]) -> np.ndarray:
    """템플릿(인쇄된 양식)에 없는 잉크만 남긴다.

    정합 오차를 감안해 템플릿을 팽창시키고, 스캔마다 굵기가 다른 체크박스 테두리는
    테두리 띠(ring)를 통째로 지운다.
    """
    ignore = cv2.dilate((template < INK_THRESHOLD).astype(np.uint8), np.ones((7, 7), np.uint8))
    for q in questions:
        for o in q["options"]:
            x, y, w, h = o["box"]
            cv2.rectangle(ignore, (x, y), (x + w - 1, y + h - 1), 1, thickness=2 * BOX_RING + 1)
    return ((aligned < INK_THRESHOLD) & (ignore == 0)).astype(np.uint8)


def read_question(ink: np.ndarray, question: dict) -> QuestionResult:
    opts = question["options"]
    boxes = [o["box"] for o in opts]
    x0 = min(b[0] for b in boxes) - COL_LEFT
    x1 = max(b[0] + b[2] for b in boxes) + COL_RIGHT
    y0 = boxes[0][1] - ANCHOR_ABOVE - 60
    y1 = boxes[-1][1] + boxes[-1][3] + ANCHOR_BELOW
    col = ink[y0:y1, x0:x1]

    # 1비트 스캔은 얇은 획이 끊기므로, 살짝 팽창시킨 마스크로 성분을 묶는다.
    joined = cv2.dilate(col, np.ones((JOIN_PX, JOIN_PX), np.uint8))
    n, labels = cv2.connectedComponents(joined, connectivity=8)
    labels = labels * col  # 원래 잉크 픽셀만 남김

    windows = [_window(b, x0, y0) for b in boxes]
    tights = [_tight(b, x0, y0) for b in boxes]
    scores = [0] * len(opts)
    for i in range(1, n):
        comp = labels == i
        if comp.sum() < MIN_COMPONENT_PX:
            continue
        ys, _ = np.nonzero(comp)
        idx = _nearest_box(y0 + int(ys.max()), boxes)  # 성분의 가장 아래 지점 = 체크 꼭짓점
        for j in range(len(opts)):
            if j == idx:
                scores[j] += int(comp[windows[j]].sum())
            else:
                # 꼭짓점이 다른 박스에 있어도, 이 박스 안을 실제로 지나가면 점수를 준다.
                scores[j] += int(comp[tights[j]].sum())

    order = sorted(range(len(opts)), key=lambda i: scores[i], reverse=True)
    best, second = scores[order[0]], scores[order[1]]
    flags: list[str] = []
    answer = None
    if best < BLANK_PX:
        flags.append("blank")
    elif second < best * SECOND_RATIO and second < MARK_PX:
        answer = opts[order[0]]["label"]
    elif second >= MARK_PX:
        flags.append("multi")
    else:
        flags.append("low_margin")

    if not answer:
        k = BOX_RING + 1
        for i, (bx, by, bw, bh) in enumerate(boxes):
            if ink[by + k : by + bh - k, bx + k : bx + bw - k].mean() >= FILLED_DENSITY:
                flags.append(f"filled:{opts[i]['label']}")

    return QuestionResult(
        qid=question["id"],
        answer=answer,
        candidate=opts[order[0]]["label"] if best >= BLANK_PX else None,
        scores=scores,
        flags=flags,
    )


def _window(box, x0, y0):
    bx, by, bw, bh = box
    return (
        slice(max(by - WIN_ABOVE - y0, 0), by + bh + WIN_BELOW - y0),
        slice(max(bx - WIN_X - x0, 0), bx + bw + WIN_X - x0),
    )


def _tight(box, x0, y0):
    bx, by, bw, bh = box
    return (slice(by - TIGHT - y0, by + bh + TIGHT - y0), slice(bx - TIGHT - x0, bx + bw + TIGHT - x0))


def _nearest_box(anchor_y: int, boxes: list[list[int]]) -> int | None:
    for i, (_, by, _, bh) in enumerate(boxes):
        if by - ANCHOR_ABOVE <= anchor_y <= by + bh + ANCHOR_BELOW:
            return i
    # 범위 밖이면 가장 가까운 박스 중심(단, 너무 멀면 무시)
    centers = [by + bh / 2 for _, by, _, bh in boxes]
    i = int(np.argmin([abs(anchor_y - c) for c in centers]))
    return i if abs(anchor_y - centers[i]) < 60 else None


def read_all(aligned: np.ndarray, template: np.ndarray, questions: list[dict]) -> list[QuestionResult]:
    ink = new_ink_mask(aligned, template, questions)
    return [read_question(ink, q) for q in questions]
