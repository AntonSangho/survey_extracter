"""양식 레이아웃(layout.json)과 기준 템플릿 로딩."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .imageio import load_gray

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_LAYOUT = PACKAGE_DIR / "layout.json"


@dataclass
class Layout:
    data: dict
    template: np.ndarray

    @property
    def questions(self) -> list[dict]:
        return self.data["questions"]

    @property
    def fields(self) -> list[dict]:
        return self.data["fields"]


def load_layout(path: Path = DEFAULT_LAYOUT) -> Layout:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    template = load_gray(path.parent / data["template"])
    return Layout(data, template)
