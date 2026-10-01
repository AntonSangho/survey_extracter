"""제안 양식을 마크다운 문서로 만든다(구글 독스 등에 붙여넣어 편집·보존용).

    python tools/make_form_markdown.py docs/form_sample.md [--school "OO초등학교"]

선택지는 tools/make_proposed_form.py(PDF)와 같은 상수를 써서 두 양식이 어긋나지 않는다.
"""

import argparse
from pathlib import Path

from make_proposed_form import KITS, QUESTIONS

RULES = [
    "연필이나 가는 펜(0.7mm 이하)으로 쓰세요. 굵은 펜·형광펜·사인펜은 쓰지 마세요.",
    "고르는 문항은 동그라미 안을 ● 처럼 가득 칠하세요. (V 체크나 동그라미 치기는 안 돼요)",
    "잘못 칠했으면 그 칸에 큰 X 표시를 하고, 맞는 칸을 새로 칠하세요.",
    "하고 싶은 말은 아래 네모 칸 안에 쓰세요. 이름이나 친구 이름은 쓰지 않아요.",
]
GAP = "　　"  # 전각 공백


def options_table(options: list[str]) -> list[str]:
    return ["| " + " | ".join(options) + " |", "|" + "---|" * len(options), "| " + " | ".join(["○"] * len(options)) + " |"]


def kit_lines() -> list[str]:
    rows = [KITS[i:i + 4] for i in range(0, len(KITS), 4)]
    return [GAP.join(f"○ {k}" for k in row) + "  " for row in rows]  # 끝의 공백 2개 = 줄바꿈


def build(school: str) -> str:
    out = ["# 2026년 학교로 찾아가는 피지컬AI 융합 체험 프로그램 만족도 조사", "", f"**학교:** {school}", "", "## 작성 방법", ""]
    out += [f"- {r}" for r in RULES]
    out += ["", "## 학년", "", GAP.join(f"○ {i}학년" for i in range(1, 7)), ""]
    for label in ("2교시", "3교시"):
        out += [f"## 참여한 키트 · {label}", ""] + kit_lines() + [""]
    for text, options in QUESTIONS:
        out += [f"## {text}", ""] + options_table(options) + [""]
    out += ["## 5. 하고 싶은 말이 있다면 아래 네모 칸 안에 적어 주세요.", "",
            "| 　 |", "|---|", "| 　 |", "| 　 |", "| 　 |", "| 　 |", ""]
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="docs/form_sample.md")
    ap.add_argument("--school", default="OO초등학교")
    args = ap.parse_args()
    Path(args.out).write_text(build(args.school), encoding="utf-8")
    print(f"저장: {args.out}")
