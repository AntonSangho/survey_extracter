"""차기 설문지 양식 제안안을 PDF로 만든다(docs/form_design_proposal.md 참고).

    python tools/make_proposed_form.py templates/proposed_form.pdf [--school "OO초등학교"]

개선점: 코너 ArUco 마커(방향·정합 자동화), 학교/회차 QR(사전 인쇄), 학교·학년·키트명은 선택식,
칠하는 원형 버블, 자유의견은 테두리 박스, 작성/수정 규칙 안내.
"""

import argparse
import subprocess
from pathlib import Path

import cv2
from PIL import Image
from reportlab.lib.colors import Color, black
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

KITS = ["마술봉", "메시지키링", "스마트 워치", "노래하는 케익", "인사하는 강아지", "메롱하는 개구리", "피노키오", "자벌래"]
QUESTIONS = [
    ("1. 오늘 워크숍은 전반적으로 만족스러웠나요?", ["매우 만족", "만족", "보통", "불만족", "매우 불만족"]),
    ("2. 만들기(조립) 과정은 어렵지 않았나요?", ["매우 쉬웠다", "쉬웠다", "보통", "어려웠다", "매우 어려웠다"]),
    ("3. 오늘 배운 내용이 흥미로웠나요?", ["매우 그렇다", "그렇다", "보통", "아니다", "매우 아니다"]),
    ("4. 다음에 또 이런 워크숍이 있다면 참여하고 싶나요?", ["네", "아니오", "잘 모르겠음"]),
]
W, H = 210 * mm, 297 * mm
R = 3.0 * mm  # 버블 반지름
GRAY = Color(0.55, 0.55, 0.55)


def font(name: str) -> str:
    out = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True).stdout
    return out


def aruco_image(marker_id: int) -> ImageReader:
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    m = cv2.aruco.generateImageMarker(d, marker_id, 200)
    return ImageReader(Image.fromarray(m))


def qr_image(payload: str) -> ImageReader:
    enc = cv2.QRCodeEncoder.create()
    q = enc.encode(payload)
    q = cv2.copyMakeBorder(q, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    q = cv2.resize(q, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    return ImageReader(Image.fromarray(q))


def bubble(c: canvas.Canvas, x: float, y: float, label: str, size: float = 10.5, num: bool = False):
    c.setLineWidth(1.0)
    c.circle(x, y, R, stroke=1, fill=0)
    c.setFont("Gothic", size)
    c.drawString(x + R + 1.8 * mm, y - 1.2 * mm, label)


def draw(path: Path, school: str) -> None:
    pdfmetrics.registerFont(TTFont("Gothic", font("NanumGothic")))
    pdfmetrics.registerFont(TTFont("GothicB", font("NanumGothic:bold")))
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setTitle("차기 설문지 양식 제안안")

    # 네 모서리 마커(ID 0~3: 좌상, 우상, 좌하, 우하)와 학교/회차 QR
    ms = 12 * mm
    for i, (mx, my) in enumerate([(6 * mm, H - 6 * mm - ms), (W - 6 * mm - ms, H - 6 * mm - ms),
                                  (6 * mm, 6 * mm), (W - 6 * mm - ms, 6 * mm)]):
        c.drawImage(aruco_image(i), mx, my, ms, ms)
    c.drawImage(qr_image(f"survey2026|school={school}|form=v2"), W - 48 * mm, H - 33 * mm, 20 * mm, 20 * mm)

    c.setFont("GothicB", 15)
    c.drawCentredString(W / 2 - 8 * mm, H - 18 * mm, "2026년 학교로 찾아가는 피지컬AI 융합 체험 프로그램 만족도 조사")
    c.setFont("Gothic", 11)
    c.drawString(24 * mm, H - 27 * mm, f"학교: {school}")
    c.setFont("Gothic", 8)
    c.setFillColor(GRAY)
    c.drawString(24 * mm, H - 32 * mm, "(학교·회차는 사전 인쇄 · QR로 자동 인식)")
    c.setFillColor(black)

    # 작성 방법 안내 박스
    top = H - 38 * mm
    c.setFillColor(Color(0.94, 0.94, 0.94))
    c.rect(18 * mm, top - 27 * mm, 174 * mm, 27 * mm, stroke=0, fill=1)
    c.setFillColor(black)
    c.setFont("GothicB", 9.5)
    c.drawString(21 * mm, top - 5.5 * mm, "작성 방법")
    c.setFont("Gothic", 9)
    for i, line in enumerate([
        "● 연필이나 가는 펜(0.7mm 이하)으로 쓰세요. 굵은 펜·형광펜·사인펜은 쓰지 마세요.",
        "● 고르는 문항은 동그라미 안을 ● 처럼 가득 칠하세요. (V 체크나 동그라미 치기는 안 돼요)",
        "● 잘못 칠했으면 그 칸에 큰 X 표시를 하고, 맞는 칸을 새로 칠하세요.",
        "● 하고 싶은 말은 아래 네모 칸 안에 쓰세요.",
    ]):
        c.drawString(21 * mm, top - (11 + i * 4.6) * mm, line)

    y = top - 35 * mm
    c.setFont("GothicB", 10.5)
    c.drawString(20 * mm, y, "학년")
    for i in range(6):
        bubble(c, 38 * mm + i * 22 * mm, y + 1 * mm, f"{i + 1}학년")

    for label in ("참여한 키트  ·  2교시", "참여한 키트  ·  3교시"):
        y -= 9 * mm
        c.setFont("GothicB", 10.5)
        c.drawString(20 * mm, y, label)
        for i, kit in enumerate(KITS):
            bubble(c, 26 * mm + (i % 4) * 41 * mm, y - 6 * mm - (i // 4) * 6.5 * mm, kit, size=9.5)
        y -= 14 * mm

    for text, options in QUESTIONS:
        y -= 9 * mm
        c.setFont("GothicB", 10.5)
        c.drawString(20 * mm, y, text)
        step = 33 * mm if len(options) == 5 else 40 * mm
        for i, opt in enumerate(options):
            bubble(c, 26 * mm + i * step, y - 7 * mm, opt, size=9.5)
        y -= 7 * mm

    y -= 9 * mm
    c.setFont("GothicB", 10.5)
    c.drawString(20 * mm, y, "5. 하고 싶은 말이 있다면 아래 네모 칸 안에 적어 주세요.")
    box_top, box_h = y - 3 * mm, 66 * mm
    c.setLineWidth(1.6)
    c.rect(20 * mm, box_top - box_h, 170 * mm, box_h, stroke=1, fill=0)
    c.setStrokeColor(Color(0.82, 0.82, 0.82))  # 연한 안내선(기울어짐 방지, 스캔에서 쉽게 제거)
    c.setLineWidth(0.5)
    for i in range(1, 5):
        c.line(20 * mm, box_top - i * box_h / 5, 190 * mm, box_top - i * box_h / 5)
    c.save()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="templates/proposed_form.pdf")
    ap.add_argument("--school", default="OO초등학교")
    args = ap.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    draw(Path(args.out), args.school)
    print(f"저장: {args.out}")
