# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

종이 설문지 스캔(5개교 422장)에서 체크박스(OpenCV OMR)와 손글씨(Claude 1차 판독 + 사람 검토)를 추출해 `responses_final.xlsx/.csv`로 내보내는 파이프라인. 사용자 대화는 한국어, 코드의 docstring·주석도 기존처럼 한국어로 쓴다.

## 명령

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # 파이프라인
pip install -r requirements-dev.txt        # tools/ (Pillow, ReportLab) — 샘플·양식 생성에만 필요

python -m unittest discover tests                              # 전체 테스트
python -m unittest tests.test_kits.NormalizeKit.test_empty     # 단일 테스트
python tools/make_samples.py samples/scans                     # 합성 샘플 + samples/truth.csv 재생성
python tools/build_expected_output.py                          # samples/expected_output/ 재생성
python tools/make_proposed_form.py templates/proposed_form.pdf # 제안 양식 PDF
python tools/make_form_markdown.py docs/form_sample.md         # 제안 양식 마크다운
```

파이프라인 단계(자세한 사용법은 README): `extract <스캔폴더> -o output [--debug]` → (Claude가 시트를 읽어 `output/transcripts/*.json` 작성, `prompt`로 지침 출력) → `merge -o output` → `review output` → 브라우저에서 검토 후 `review_decisions.csv`를 `output/`에 저장 → `export output [--links drive_links.csv]`. 린터·빌드 설정은 없다. pytest가 아니라 `unittest`를 쓴다.

## 아키텍처

한 번의 `extract`가 만드는 `responses.csv`가 중심 테이블이고, 이후 단계는 모두 이 CSV와 `output/` 아래 파일을 읽어 덮어쓰거나 덧붙인다.

1. **`cli.cmd_extract`**: 이미지 한 장마다 `align.Aligner.align`(ORB+RANSAC 호모그래피로 `survey_extract/templates/form_2026.png` 좌표계에 정렬, 180° 뒤집힘 자동 처리, 폭이 템플릿과 2% 넘게 다르면 `normalize_scale`로 맞춤) → `omr.read_all`(체크박스, 결과·플래그 `multi/blank/low_margin/filled:*`) → `crops.save_crops`(손글씨 필드 크롭, 빈 칸 판정) → 원본 사본(`output/originals`, 뒤집힌 건 180° 회전). 끝에 `crops.build_sheets`가 판독용 묶음 시트와 `sheets/manifest.json`(시트별 ID·필드)을 쓴다.
2. **`layout.json`**: 템플릿 좌표계(2481×3506, 300dpi)의 체크박스 `box`와 손글씨 `roi`. 양식이 바뀌면 템플릿과 이 파일을 같이 바꿔야 한다. 학생 이름 필드는 분석에 불필요해 제거됨.
3. **`transcribe.merge`**: `transcripts/<시트>.json`(`{ID: {필드: {text, conf: high|low}}}`)을 검증해 `responses.csv`에 `<필드>`, `<필드>_conf`, `hw_status`로 합친다. 시트 구성은 `manifest.json`이 정하므로 `extract`를 다시 돌리면 시트·transcripts 대응을 확인해야 한다.
4. **`review.build_review`**: 모든 행을 JSON으로 박은 오프라인 `review.html` 생성. 입력 상태는 브라우저 localStorage(키는 파일 경로)에만 저장되고, 결과 CSV 다운로드로만 파일이 된다.
5. **`review.export_xlsx`**: `responses.csv` + `review_decisions.csv`(브라우저 결과) + `corrections.csv`(수동 보정, 최우선) + 선택적 `--links`를 합쳐 `응답/집계/키트/검토이력`(+무효가 있으면 `검토요청`) 시트와 `responses_final.csv`를 쓴다. 키트명은 `kits.py`가 `kits.json` 키워드로 8개 표준명에 묶으며, 0개/2개 이상 매칭은 추측하지 않고 `kit_check=확인필요`로 둔다.

상태 의미: `omr_status`(auto/needs_review)는 체크박스, `hw_status`는 손글씨, 최종 `status`(auto/reviewed/needs_review)는 `export`가 계산한다. 검토 대상은 `review.needs_review`(체크박스 플래그 또는 손글씨 `low`).

## 지킬 것 / 함정

- **개인정보**: `raw/`, `output/`, 드라이브 링크 파일은 커밋 금지(.gitignore). 실제 응답 원문·학생 이름·실제 파일 ID를 커밋, 이슈, 문서에 쓰지 않는다(구체 사례는 로컬 `output/review_notes.md`). `samples/`는 전부 합성 데이터.
- **이미지 ID는 파일명(확장자 제외)**. 같은 이름이 다른 폴더에 있으면 `학교명_파일명`. 검토 결과·드라이브 링크가 이 ID에 묶이므로 추출 후 파일명을 바꾸지 않는다. 시트 이미지 라벨은 `cv2.putText`가 한글을 못 그려 ID 끝 8자리 ASCII만 쓴다.
- **한글 경로**: 이미지 입출력은 `imageio.py`(`np.fromfile`+`imdecode`)만 사용. `cv2.imread/imwrite` 직접 호출 금지.
- **`export`를 `--links` 없이 다시 실행하면 `share_url`이 비워진 파일로 덮어쓴다.** 링크가 있는 상태를 유지하려면 항상 `--links`를 같이 준다. 명령 이름 주의: `merge`는 손글씨 판독 병합이고 엑셀 생성은 `export`.
- **손글씨 전사는 보이는 그대로** 옮긴다(교정·해석 금지). 해석하다 의미가 뒤집힌 사례가 있었다. 읽기 어려우면 `conf: low`, 실명은 `[이름]`으로 가린다. 자유의견은 사람이 확인하는 것을 전제로 한다.
- 사람 검토량이 작업 비용의 대부분이다. 손글씨 판독 같은 작업은 전체를 돌리기 전에 소수 장으로 수정률을 재고 필드별 검토 건수를 먼저 보고한다.
- `tools/scan_quality.py`, 실제 데이터 실험은 로컬 `raw/`와 `output/responses_final.csv`가 있어야 한다. 테스트와 CI 성격의 검증은 `samples/`만 사용한다.
