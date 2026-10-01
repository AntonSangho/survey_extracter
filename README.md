# survey_extracter

워크숍 현장에서 **종이로 받은 설문지 스캔 이미지**에서 응답을 추출하는 도구입니다.

- 체크박스 문항은 OpenCV로 자동 판독합니다(OMR).
- 손글씨 항목(학년·키트명·자유의견)은 잘라낸 이미지를 Claude가 1차 판독하고, 사람이 검토합니다.
- 이중 체크·애매한 체크는 자동으로 플래그를 달아 사람이 검토합니다.
- Windows / macOS에서 Python 스크립트로 실행하거나, Claude Skill(무료 플랜 포함)로 사용할 수 있습니다.

> 🚧 개발 진행 중입니다. 진행 상황은 [Issues](../../issues)를 참고하세요.

## 개인정보 주의

원본 스캔과 추출 결과에는 학생 실명이 포함됩니다. `raw/`, `output/`은 `.gitignore`로 제외되어 있으며, 이 저장소의 샘플 이미지는 모두 **합성(가상) 데이터**입니다.

## 최종 결과에 원본 공유링크 넣기

`export`가 만드는 `responses_final.xlsx`(와 `responses_final.csv`)에는 원본 파일 경로(`file`)가 들어 있어 손글씨를 다시 확인할 수 있습니다. 원본을 구글 드라이브에 올렸다면 공유링크도 함께 넣을 수 있습니다.

1. 원본 폴더를 드라이브에 올리고, 파일마다 공유링크를 만듭니다.
2. 아래 형식의 `drive_links.csv`를 만듭니다. `file`은 `extract`가 기록한 상대경로(`학교명/파일명.png`) 또는 파일명만 써도 됩니다.

   ```csv
   file,url
   학교명/img20260101_0001.png,https://drive.google.com/file/d/.../view
   ```

3. `python -m survey_extract export output --links drive_links.csv`

`share_url` 열은 엑셀에서 클릭되는 링크로 들어가며, 링크가 없는 파일 수는 실행 결과에 표시됩니다. 링크 파일에는 실제 파일명이 들어가므로 저장소에 커밋하지 마세요.
