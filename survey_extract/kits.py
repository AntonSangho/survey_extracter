"""키트명 표준화. 수식어("노래하는", "만들기")나 철자 변형을 표준 키트명 하나로 묶는다.

kits.json: {표준명: [키워드, ...]}. 공백을 뺀 텍스트에 키워드가 들어 있는지로 판단한다.
표준명이 정확히 하나만 맞으면 그 이름, 아무것도 안 맞거나 둘 이상 맞으면 매칭 실패로 돌려준다.
"""

import json
from pathlib import Path

KITS_PATH = Path(__file__).resolve().parent / "kits.json"


def load_kits(path: Path = KITS_PATH) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_kit(text: str, kits: dict[str, list[str]]) -> tuple[str, str]:
    """(표준명, 상태)를 돌려준다. 상태: ok / empty / unmatched / ambiguous."""
    t = "".join((text or "").split())
    if not t:
        return "", "empty"
    hits = [name for name, words in kits.items() if any(w in t for w in words)]
    if len(hits) == 1:
        return hits[0], "ok"
    return "", "ambiguous" if hits else "unmatched"
