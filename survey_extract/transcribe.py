"""손글씨 1차 판독 결과(Claude 비전)를 responses.csv에 합친다.

흐름: extract가 sheets/*.png + sheets/manifest.json을 만들면, Claude가 시트를 보고
transcripts/<시트이름>.json을 쓴다. merge가 이를 검증해 CSV에 넣는다.
손글씨 값은 모두 needs_review로 시작한다(사람 검토 필수, #6).

transcripts/<시트>.json 형식:
    {"0001": {"grade": {"text": "5", "conf": "high"}}}
빈 칸은 text를 ""로 쓴다.
"""

import csv
import json
from pathlib import Path

CONFS = ("high", "low")

PROMPT = """\
첨부한 시트는 설문지 손글씨 크롭을 학생별 한 줄로 묶은 것입니다. 왼쪽 굵은 숫자는 학생 ID의 끝 8자리입니다(JSON 키에는 manifest의 전체 ID를 쓰세요).
{layout}
규칙:
{kits}- 보이는 글자를 그대로 옮기세요. 맞춤법을 고치거나 추측해 채우지 마세요.
- 글자가 뚜렷하면 conf="high", 흘려 썼거나 둘 이상으로 읽히면 conf="low"로 쓰세요.
- 비어 있는 칸은 text=""로 두세요. 밑줄·얼룩은 글자가 아닙니다.
- 결과는 transcripts/<시트이름>.json에 저장하세요. 형식:
  {{"0001": {{"{first}": {{"text": "...", "conf": "high"}}, ...}}, ...}}
"""

LABELS = {"grade": "학년", "kit_2": "2교시 키트명", "kit_3": "3교시 키트명", "q5": "5번 자유의견"}


def prompt_for(sheet: str, manifest: dict) -> str:
    m = manifest[sheet]
    layout = "열(왼쪽→오른쪽): " + ", ".join(f"{f}({LABELS.get(f, f)})" for f in m["fields"]) + "\n"
    kits = ""
    if any(f.startswith("kit_") for f in m["fields"]):
        kits = "- 키트명은 '노래하는 케이크'처럼 수식어가 붙기도 합니다. 쓴 그대로 옮기세요(표준 키트명 매칭은 나중에 따로 합니다).\n"
    return f"[{sheet}]\n" + PROMPT.format(layout=layout, kits=kits, first=m["fields"][0])


def merge(out_dir: Path) -> dict:
    """transcripts/*.json을 검증해 responses.csv에 반영하고 요약을 돌려준다."""
    manifest = json.loads((out_dir / "sheets" / "manifest.json").read_text(encoding="utf-8"))
    csv_path = out_dir / "responses.csv"
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns, rows = list(reader.fieldnames), list(reader)
    by_id = {r["id"]: r for r in rows}
    fields = sorted({f for m in manifest.values() for f in m["fields"]}, key=lambda f: list(LABELS).index(f) if f in LABELS else 99)

    errors, done, pending = [], set(), []
    for sheet, m in manifest.items():
        path = out_dir / "transcripts" / f"{sheet}.json"
        if not path.exists():
            pending.append(sheet)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for sid in m["ids"]:
            for fid in m["fields"]:
                cell = data.get(sid, {}).get(fid)
                if not isinstance(cell, dict) or not isinstance(cell.get("text"), str) or cell.get("conf") not in CONFS:
                    errors.append(f"{sheet}: {sid}/{fid} 누락 또는 형식 오류")
                    continue
                by_id[sid][fid] = cell["text"].strip()
                by_id[sid][f"{fid}_conf"] = cell["conf"]
                done.add((sid, fid))
        errors += [f"{sheet}: 시트에 없는 ID {sid}" for sid in data if sid not in m["ids"]]

    for r in rows:
        for fid in fields:
            if r.get(f"blank_{fid}") == "True":  # 크롭 단계에서 빈 칸으로 판정
                r.setdefault(fid, "")
                # 다른 칸에 쓴 내용이 옮겨 적혔다면 값이 있으므로 사람이 확인하도록 low로 둔다.
                r[f"{fid}_conf"] = "low" if r[fid] else "blank"
        r["hw_status"] = "needs_review" if any((r["id"], f) in done for f in fields) else r.get("hw_status", "")

    for fid in fields:
        if f"{fid}_conf" not in columns:
            columns.append(f"{fid}_conf")
    if "hw_status" not in columns:
        columns.append("hw_status")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, restval="")
        w.writeheader()
        w.writerows(rows)
    low = sum(r.get(f"{fid}_conf") == "low" for r in rows for fid in fields)
    return {"cells": len(done), "low": low, "pending": pending, "errors": errors}
