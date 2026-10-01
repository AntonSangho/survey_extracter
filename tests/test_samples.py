"""합성 샘플로 추출 파이프라인의 기대 동작을 검증한다(samples/truth.csv 기준)."""

import csv
import tempfile
import unittest
from pathlib import Path

from survey_extract.cli import main

ROOT = Path(__file__).resolve().parents[1]
QIDS = ["q1", "q2", "q3", "q4"]
# 사람이 판단해야 하는 사례. OMR은 이 경우 자동 확정하지 않고 플래그를 달아야 한다.
AMBIGUOUS = {"double": "q2", "blank": "q3", "scribble": "q1", "x_cancel": "q4"}


class SamplePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        main(["extract", str(ROOT / "samples/scans"), "-o", cls.tmp.name])
        with open(Path(cls.tmp.name) / "responses.csv", newline="", encoding="utf-8-sig") as f:
            cls.rows = {r["file"]: r for r in csv.DictReader(f)}
        with open(ROOT / "samples/truth.csv", newline="", encoding="utf-8-sig") as f:
            cls.truth = list(csv.DictReader(f))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_aligned_and_flip_detected(self):
        for t in self.truth:
            r = self.rows[t["file"]]
            self.assertEqual(r["align_ok"], "True", t["file"])
            self.assertEqual(r["rotated_180"], str(t["case"] in ("flipped", "noisy")), t["file"])

    def test_clear_answers_are_read_correctly(self):
        for t in self.truth:
            r = self.rows[t["file"]]
            for q in QIDS:
                if AMBIGUOUS.get(t["case"]) == q:
                    continue
                self.assertEqual(r[q], t[q], f"{t['file']} {q}")

    def test_ambiguous_cases_are_flagged_not_guessed(self):
        for t in self.truth:
            q = AMBIGUOUS.get(t["case"])
            if not q:
                continue
            r = self.rows[t["file"]]
            self.assertEqual(r[q], "", f"{t['case']}: 자동 확정하면 안 됨")
            self.assertEqual(r["omr_status"], "needs_review", t["case"])

    def test_clean_samples_need_no_review(self):
        for t in self.truth:
            if t["case"] in ("clean", "flipped", "tilted", "noisy"):
                self.assertEqual(self.rows[t["file"]]["omr_status"], "auto", t["file"])


if __name__ == "__main__":
    unittest.main()
