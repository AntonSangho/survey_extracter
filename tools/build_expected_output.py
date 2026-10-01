"""합성 샘플로 전체 흐름을 한 번 돌려 samples/expected_output/ 을 만든다.

추출 → (이상적인 1차 판독 = 정답표) → 병합 → 검토 화면 → (사람이 정답으로 확정) → 내보내기.
README의 '예상 결과물'과 같은 파일이다. 사용법:

    python tools/make_samples.py samples/scans
    python tools/build_expected_output.py
"""

import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from survey_extract.cli import main  # noqa: E402
from survey_extract.review import HW_FIELDS, read_rows  # noqa: E402

SAMPLES = ROOT / "samples"
EXPECTED = SAMPLES / "expected_output"
KEEP_DEBUG = ("sample_007", "sample_009")  # 이중 체크, 지운 흔적 오버레이 예시
QIDS = ["q1", "q2", "q3", "q4"]


def main_build(work: Path) -> None:
    main(["extract", str(SAMPLES / "scans"), "-o", str(work), "--debug"])
    truth = {Path(t["file"]).stem: t for t in csv.DictReader(open(SAMPLES / "truth.csv", encoding="utf-8-sig", newline=""))}

    # 이상적인 1차 판독: 판독용 시트마다 정답표의 손글씨 값을 확신도 high로 기록
    manifest = json.loads((work / "sheets" / "manifest.json").read_text(encoding="utf-8"))
    (work / "transcripts").mkdir(exist_ok=True)
    for sheet, m in manifest.items():
        data = {sid: {f: {"text": truth[sid][f], "conf": "high"} for f in m["fields"]} for sid in m["ids"]}
        (work / "transcripts" / f"{sheet}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    main(["merge", "-o", str(work)])

    # 사람의 검토: 체크박스 플래그가 있는 행을 정답으로 확정(브라우저의 결과 CSV와 같은 형식)
    rows = read_rows(work)
    with (work / "review_decisions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "field", "auto_value", "final_value"])
        for r in rows:
            if r["omr_status"] != "needs_review":
                continue
            t = truth[r["id"]]
            for field in QIDS + HW_FIELDS:
                w.writerow([r["id"], field, r[field], t[field]])
    main(["review", str(work)])
    main(["export", str(work)])


def main_copy(work: Path) -> None:
    if EXPECTED.exists():
        shutil.rmtree(EXPECTED)
    (EXPECTED / "debug").mkdir(parents=True)
    for name in ("responses.csv", "review_decisions.csv", "responses_final.xlsx", "responses_final.csv"):
        shutil.copy(work / name, EXPECTED / name)
    shutil.copytree(work / "sheets", EXPECTED / "sheets")
    for p in (work / "debug").glob("*.jpg"):
        if any(k in p.stem for k in KEEP_DEBUG):
            shutil.copy(p, EXPECTED / "debug" / p.name)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        main_build(work)
        main_copy(work)
        # 스크린샷용으로 검토 화면이 있는 작업 폴더를 남긴다
        keep = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        if keep:
            shutil.copytree(work, keep, dirs_exist_ok=True)
    print(f"저장: {EXPECTED}")
