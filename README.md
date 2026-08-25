# welllog-auto-post

@welllog.kr 인스타그램 계정에 매일 자동으로 게시물을 올리기 위한 저장소입니다.

## 구조

- `content/queue/NNN/caption.json`, `content/queue/NNN/image.png` — 아직 게시 안 한 콘텐츠 대기열. 폴더 이름(001, 002, ...) 순서대로 하나씩 게시됩니다.
- `content/posted/` — 게시가 끝난 항목이 자동으로 옮겨지는 곳 (기록용, 신경 안 쓰셔도 돼요).
- `.github/workflows/publish.yml` — 매일 정해진 시간에 자동 실행되는 GitHub Actions 워크플로.
- `scripts/publish_to_instagram.py` — 큐에서 다음 항목을 골라 게시하는 로직.
- `scripts/refresh_token.py` — 액세스 토큰 갱신용 (45~50일 주기로 수동 실행 권장).

## 최초 1회 설정

저장소 **Settings → Secrets and variables → Actions → New repository secret** 에서 아래 2개를 등록하세요.

| Secret 이름 | 값 |
|---|---|
| `IG_ACCESS_TOKEN` | 인스타그램 장기(60일) 액세스 토큰 |
| `IG_USER_ID` | Instagram-scoped User ID (숫자) |

## 동작 방식

1. Claude와의 대화에서 여러 날짜분의 콘텐츠(이미지+캡션)를 미리 만들어 `content/queue/NNN/` 형태로 채워둡니다 (GitHub 웹사이트에서 파일 업로드로 추가).
2. 매일 정해진 시간에 GitHub Actions가 자동 실행되어, 큐에서 가장 앞선 항목을 골라 catbox.moe에 이미지를 업로드하고 인스타그램에 게시합니다.
3. 게시가 끝난 항목은 `content/posted/`로 자동 이동·커밋됩니다.
4. 큐가 비면 다음 실행 때 에러 로그가 남습니다 (Actions 탭에서 확인 가능) — 이땐 Claude에게 콘텐츠를 더 만들어달라고 요청하면 됩니다.

## 게시 시간 변경

`.github/workflows/publish.yml` 파일의 `cron` 값을 수정하세요. (UTC 기준이라 한국 시간에서 9시간을 빼야 해요.)

## 토큰 갱신

액세스 토큰은 60일 후 만료됩니다. 45~50일 주기로 `scripts/refresh_token.py`를 실행해 새 토큰을 받고, 위 Secrets의 `IG_ACCESS_TOKEN` 값을 갱신해주세요.
