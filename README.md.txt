# welllog-auto-post

@welllog.kr 인스타그램 계정(경제/금융 지식사전 컨셉)에 매일 자동으로 게시물을 올리기 위한 저장소입니다.

콘텐츠 생성부터 게시까지 **사람 손 없이 완전 자동**으로 돌아갑니다.

## 구조

- `scripts/generate_and_queue.py` — 매일 Claude(Anthropic API)를 호출해 새 경제/금융 용어 카드뉴스(4장)를 만들고 `content/queue/NNN/`에 등록합니다.
- `scripts/templates.py` — 카드 4장(표지/설명/비교/마무리)의 HTML/CSS 템플릿.
- `scripts/publish_to_instagram.py` — 큐에서 다음 항목을 골라 인스타그램에 게시하는 로직. 이미지는 이 저장소의 GitHub raw URL을 그대로 사용합니다 (**저장소가 Public이어야 동작**).
- `scripts/refresh_token.py` — 인스타그램 액세스 토큰 갱신용 (45~50일 주기로 수동 실행 권장).
- `content/queue/NNN/` — 아직 게시 안 한 콘텐츠 대기열 (평소엔 비어있는 게 정상 — 매일 자동으로 채워지고 바로 비워짐).
- `content/posted/` — 게시가 끝난 항목이 자동으로 옮겨지는 곳 (기록용, 신경 안 쓰셔도 돼요).
- `content/used_terms.json` — 지금까지 다룬 용어 목록 (같은 용어가 중복되지 않도록 관리).
- `.github/workflows/publish.yml` — 매일 정해진 시간에 자동 실행되는 GitHub Actions 워크플로.

## 최초 1회 설정

저장소 **Settings → Secrets and variables → Actions → New repository secret** 에서 아래 3개를 등록하세요.

| Secret 이름 | 값 |
|---|---|
| `IG_ACCESS_TOKEN` | 인스타그램 장기(60일) 액세스 토큰 |
| `IG_USER_ID` | Instagram-scoped User ID (숫자) |
| `ANTHROPIC_API_KEY` | console.anthropic.com에서 발급받은 API 키 |

## 동작 방식 (매일 자동 반복)

1. 매일 정해진 시간(KST 11:07)에 GitHub Actions가 자동 실행됩니다.
2. `generate_and_queue.py`가 Claude를 호출해 아직 안 다룬 새 경제/금융 용어 하나를 골라 카드 4장(표지/설명/비교/마무리)을 만들고 큐에 등록합니다.
3. `publish_to_instagram.py`가 그 큐 항목을 바로 인스타그램에 캐러셀(4장)로 게시합니다.
4. 게시 완료된 항목은 `content/posted/`로, 사용한 용어는 `content/used_terms.json`에 자동 기록됩니다.
5. 만약 전날 게시가 실패해서 큐에 항목이 남아있으면, 새로 생성하지 않고 그 항목을 먼저 재시도합니다.

**즉, 평소엔 아무것도 안 하셔도 매일 새 콘텐츠가 자동으로 올라갑니다.** Actions 탭에서 실행 기록만 가끔 확인하시면 돼요.

## 게시 시간 변경

`.github/workflows/publish.yml` 파일의 `cron` 값을 수정하세요. (UTC 기준이라 한국 시간에서 9시간을 빼야 해요.)

## 콘텐츠 톤 수정

`scripts/generate_and_queue.py` 안의 `SYSTEM_PROMPT` 문구를 수정하면 톤/규칙을 바꿀 수 있어요. `scripts/templates.py`를 수정하면 디자인(색상, 레이아웃)을 바꿀 수 있어요.

## 토큰 갱신

인스타그램 액세스 토큰은 60일 후 만료됩니다. 45~50일 주기로 `scripts/refresh_token.py`를 실행해 새 토큰을 받고, 위 Secrets의 `IG_ACCESS_TOKEN` 값을 갱신해주세요.
