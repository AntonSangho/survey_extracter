"""손글씨 영역 크롭, 판독용 묶음 시트, 디버그 오버레이."""

from pathlib import Path

import cv2
import numpy as np

from .imageio import load_gray, save_image
from .omr import QuestionResult

SHEET_WIDTH = 1500  # 묶음 시트 가로 폭(px). Claude 비전 권장 긴 변 ≤1568px
SHEET_MAX_H = 1560
LABEL_W = 170
BLANK_INK_PX = 150  # 밑줄을 뺀 잉크가 이보다 적으면 빈 칸
MIN_GLYPH_H = 22  # 이보다 낮은 성분은 점선·밑줄 조각으로 본다


def handwriting_mask(crop: np.ndarray) -> np.ndarray:
    """밑줄·점선을 지운 손글씨 잉크 마스크(0/1).

    실선 밑줄은 가로 열림 연산으로 지우고, 남은 점선 조각은 높이가 낮으므로
    높이가 MIN_GLYPH_H 이상인 성분만 남긴다.
    """
    ink = (crop < 128).astype(np.uint8)
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (80, 1)))
    ink &= 1 - cv2.dilate(lines, np.ones((5, 1), np.uint8))
    joined = cv2.dilate(ink, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    keep = np.zeros(n, np.uint8)
    h, w = stats[1:, cv2.CC_STAT_HEIGHT], stats[1:, cv2.CC_STAT_WIDTH]
    scanner_line = (h > 0.8 * crop.shape[0]) & (w < 15)  # 스캐너 세로줄 노이즈
    keep[1:] = (h >= MIN_GLYPH_H) & ~scanner_line
    return ink & keep[labels]


def ink_amount(crop: np.ndarray) -> int:
    return int(handwriting_mask(crop).sum())


def trim_rows(crop: np.ndarray, margin: int = 12) -> np.ndarray:
    """손글씨가 있는 행 범위만 남긴다(빈 줄 제거로 시트에 더 많은 학생을 담기 위해)."""
    rows = np.nonzero(handwriting_mask(crop).any(axis=1))[0]
    if rows.size == 0:
        return crop
    return crop[max(rows[0] - margin, 0) : rows[-1] + margin + 1]


def crop_field(aligned: np.ndarray, roi: list[int]) -> np.ndarray:
    x, y, w, h = roi
    return aligned[y : y + h, x : x + w]


def save_crops(aligned: np.ndarray, fields: list[dict], out_dir: Path, sid: str) -> dict[str, object]:
    """필드별 크롭을 저장하고 {crop_<id>: 상대경로, blank_<id>: 빈칸 여부}를 돌려준다."""
    info: dict[str, object] = {}
    for f in fields:
        crop = crop_field(aligned, f["roi"])
        rel = Path("crops") / f["id"] / f"{sid}.png"
        save_image(out_dir / rel, crop)
        info[f"crop_{f['id']}"] = rel.as_posix()
        info[f"blank_{f['id']}"] = ink_amount(crop) < BLANK_INK_PX
    return info


def build_sheets(out_dir: Path, rows: list[dict], fields: list[dict], per_sheet: int = 12) -> list[Path]:
    """손글씨 크롭을 학생 여러 명씩 한 장으로 묶는다(행 = 학생, 왼쪽에 ID).

    헤더(학년·이름·키트명)와 Q5는 비율이 달라 따로 묶는다. 시트는 Claude 비전이
    축소 없이 읽도록 SHEET_MAX_H를 넘지 않게 자르고, 모든 칸이 빈 학생은 넣지 않는다.
    """
    groups = {
        "header": [f for f in fields if f["id"] != "q5"],
        "q5": [f for f in fields if f["id"] == "q5"],
    }
    sheets = []
    for gname, gfields in groups.items():
        if not gfields:
            continue
        todo = [r for r in rows if not all(r[f"blank_{f['id']}"] for f in gfields)]
        lines, page = [], 1
        for r in todo:
            line = _sheet_row(out_dir, r, gfields)
            if lines and (len(lines) >= per_sheet or sum(l.shape[0] for l in lines) + line.shape[0] > SHEET_MAX_H):
                sheets.append(_save_sheet(out_dir, gname, page, lines))
                lines, page = [], page + 1
            lines.append(line)
        if lines:
            sheets.append(_save_sheet(out_dir, gname, page, lines))
    return sheets


def _save_sheet(out_dir: Path, gname: str, page: int, lines: list[np.ndarray]) -> Path:
    path = out_dir / "sheets" / f"{gname}_{page:03d}.png"
    save_image(path, np.vstack(lines))
    return path


def _sheet_row(out_dir: Path, row: dict, fields: list[dict]) -> np.ndarray:
    avail = SHEET_WIDTH - LABEL_W
    crops = [trim_rows(load_gray(out_dir / row["crop_" + f["id"]])) for f in fields]
    gaps = 10 * (len(crops) - 1)
    scale = min(1.0, (avail - gaps) / sum(c.shape[1] for c in crops))
    crops = [cv2.resize(c, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) for c in crops]
    h = max(c.shape[0] for c in crops) + 8
    canvas = np.full((h, SHEET_WIDTH), 255, np.uint8)
    cv2.putText(canvas, row["id"], (6, h // 2 + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.75, 0, 2)
    x = LABEL_W
    for c in crops:
        canvas[4 : 4 + c.shape[0], x : x + c.shape[1]] = c
        x += c.shape[1] + 10
        cv2.line(canvas, (x - 5, 0), (x - 5, h), 180, 1)
    cv2.line(canvas, (0, h - 1), (SHEET_WIDTH, h - 1), 0, 2)
    return canvas


def debug_overlay(aligned: np.ndarray, layout_q: list[dict], fields: list[dict],
                  results: list[QuestionResult]) -> np.ndarray:
    """정렬된 이미지 위에 체크박스·필드 ROI와 판정 결과를 그린다."""
    img = cv2.cvtColor(aligned, cv2.COLOR_GRAY2BGR)
    for q, r in zip(layout_q, results):
        for o, s in zip(q["options"], r.scores):
            x, y, w, h = o["box"]
            chosen = o["label"] in (r.answer, r.candidate)
            color = (0, 160, 0) if r.answer == o["label"] else (0, 0, 255) if chosen else (200, 120, 0)
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 3 if chosen else 1)
            cv2.putText(img, str(s), (x - 110, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        if r.flags:
            x, y = q["options"][0]["box"][:2]
            cv2.putText(img, ",".join(r.flags), (x + 600, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    for f in fields:
        x, y, w, h = f["roi"]
        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 255), 2)
        cv2.putText(img, f["id"], (x + 4, y + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 2)
    return img
