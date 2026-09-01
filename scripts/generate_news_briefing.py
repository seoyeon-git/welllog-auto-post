"""
매일 GitHub Actions가 하루 한 번 실행하는 '오늘의 경제 이슈 브리핑' 생성 스크립트.

기존 용어 사전 카드(generate_and_queue.py)와 콘텐츠 성격이 다릅니다 — 이건 실제로 오늘
국내 경제 언론사에 보도된 진짜 기사 하나를 요약하는 콘텐츠라, 사실관계를 지어내면 안 됩니다.

동작:
1. content/queue/ 에 아직 처리 안 된 항목이 있으면 종료 (용어 카드와 큐를 공유하므로 동일 규칙)
2. 국내 경제 언론사 RSS(한국경제 우선, 매일경제 보조)에서 기사 목록을 가져와
   이미 다룬 기사(content/used_news.json, URL 기준)를 제외하고 하나를 고름
3. trafilatura로 그 기사의 실제 본문 텍스트를 최대한 추출
4. Claude에게 "제공된 기사 원문 안에 있는 사실만 사용해서" 카드뉴스 콘텐츠를 만들게 함
   (원문에 없는 수치·사실 지어내기 금지, 원문 그대로 베끼기 금지 — 반드시 패러프레이즈)
5. Unsplash로 배경사진 4장 검색·다운로드, 카드 4장 렌더링
   (3번째 슬라이드는 막대그래프(SLIDE3_COMPARE) 대신 SLIDE3_NEWS_IMPACT 사용 — 실제 기사에
   없는 수치를 그래프로 시각화하며 지어낼 위험을 원천 차단하기 위함)
6. content/queue/NNN/caption.json 작성 (출처 언론사·기사 제목 표기 포함)
7. content/used_news.json 에 기사 URL 추가 (동일 기사 재사용 방지)

필요한 환경변수 (기존 term-card 파이프라인과 동일한 Secrets 재사용):
- ANTHROPIC_API_KEY
- UNSPLASH_ACCESS_KEY

이후 scripts/publish_to_instagram.py 가 이 큐 항목을 그대로 집어서 게시합니다
(용어 카드와 발행 로직을 공유 — 큐에 먼저 들어온 것부터 순서대로 게시됨).
"""

import os
import re
import sys
import json
import asyncio
import xml.etree.ElementTree as ET

import anthropic
import requests
import trafilatura
from playwright.async_api import async_playwright

import templates

MODEL = os.environ.get("CONTENT_MODEL", "claude-haiku-4-5")
QUEUE_DIR = "content/queue"
POSTED_DIR = "content/posted"
USED_NEWS_PATH = "content/used_news.json"
USED_IMAGES_PATH = "content/used_images.json"

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
UNSPLASH_API = "https://api.unsplash.com"

FALLBACK_QUERIES = {
    "cover": "newspaper morning coffee desk",
    "explain": "city skyline finance district",
    "impact": "hand holding smartphone chart",
    "closing": "sunrise window hope",
}

# 국내 경제 언론사 RSS — 순서대로 시도. 하나가 막히거나 결과가 없어도 다음 걸로 넘어감.
NEWS_FEEDS = [
    {"name": "한국경제", "url": "https://www.hankyung.com/feed/economy"},
    {"name": "매일경제", "url": "https://file.mk.co.kr/news/rss/rss_30100041.xml"},
]

# 브리핑에 부적합한 기사(사진/영상 모음, 부고, 인사 등) 걸러내는 제목 패턴
SKIP_TITLE_PATTERNS = ["[포토", "[영상", "[사진", "부고", "인사>", "[표]", "[알림]", "[전문]"]


NEWS_TOOL_SCHEMA = {
    "name": "submit_news_briefing",
    "description": (
        "오늘의 경제 이슈 브리핑 카드뉴스 콘텐츠를 제출합니다. "
        "반드시 사용자 메시지로 제공된 기사 원문 안에 있는 사실만 사용하세요."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "issue_kr", "hook_tag", "hook", "hook_highlight",
            "reveal_tag", "summary", "summary_highlights",
            "step1_label", "step1_value", "step2_label", "step2_value",
            "step3_label", "step3_value", "flow_note",
            "impact_tag", "impact_heading",
            "impact1_label", "impact1_value", "impact2_label", "impact2_value",
            "takeaway", "takeaway_highlights",
            "closing_tag", "closing_headline", "closing_highlight",
            "cover_image_query", "explain_image_query",
            "impact_image_query", "closing_image_query",
            "caption", "hashtags",
        ],
        "properties": {
            "issue_kr": {"type": "string", "description": "이 이슈를 부르는 짧은 한글 제목, 8~16자 (예: '미국 7월 물가 다시 꿈틀')"},
            "hook_tag": {"type": "string", "description": "표지 좌상단 태그 칩 문구, 2~6글자 (예: '월급쟁이 필독', '장바구니 주의')"},
            "hook": {
                "type": "string",
                "description": (
                    "표지 전체를 채우는 후킹 헤드라인. 이슈 제목이나 구체적 수치는 절대 넣지 말고, "
                    "특정 타깃층이 '어 이거 내 얘기인데' 하고 공감할 상황·궁금증으로 표현. "
                    "줄바꿈은 \\n 사용, 2줄 이내 권장. "
                    "중요: 줄바꿈(\\n)은 반드시 완결된 어절(띄어쓰기로 구분되는 단위) 경계에서만 넣을 것 — "
                    "절대 단어 중간을 끊어서 다음 줄로 넘기면 안 됨. "
                    "나쁜 예: '금리가 내려가면 내 지\\n갑도 내려가' (X, '지갑'이라는 단어가 쪼개짐) / "
                    "좋은 예: '금리가 내려가면\\n내 지갑도 내려가' (O, 단어가 항상 한 줄 안에 온전히 들어감)."
                ),
            },
            "hook_highlight": {"type": "string", "description": "hook 문장 안에 실제로 등장하는 짧은 구절(1~4글자 권장), 그대로 부분 문자열 일치해야 함"},
            "reveal_tag": {"type": "string", "description": "2번 슬라이드 좌상단 태그 칩 문구, 예: '오늘의 이슈'"},
            "summary": {
                "type": "string",
                "description": (
                    "이 기사에서 실제로 무슨 일이 있었는지, 제공된 기사 원문에 있는 사실만으로 2~3문장 요약. "
                    "원문 문장을 그대로 베끼지 말고 쉬운 말로 다시 풀어 쓸 것 (패러프레이즈 필수)."
                ),
            },
            "summary_highlights": {
                "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2,
                "description": "summary 안에 실제로 등장하는 핵심 구절 1~2개 (형광펜 마커 강조용, 그대로 부분 문자열 일치)",
            },
            "step1_label": {"type": "string"}, "step1_value": {"type": "string"},
            "step2_label": {"type": "string"}, "step2_value": {"type": "string"},
            "step3_label": {"type": "string"}, "step3_value": {"type": "string"},
            "flow_note": {"type": "string", "description": "3단계 흐름 아래 들어갈 짧은 정리 문장"},
            "impact_tag": {"type": "string", "description": "3번 슬라이드 좌상단 태그 칩 문구, 예: '왜 중요할까'"},
            "impact_heading": {"type": "string", "description": "3번 슬라이드 제목, 예: '이게 왜 중요할까'"},
            "impact1_label": {"type": "string"}, "impact1_value": {"type": "string"},
            "impact2_label": {"type": "string"}, "impact2_value": {"type": "string"},
            "takeaway": {"type": "string", "description": "핵심 시사점/한줄요약 1~2문장, 제공된 원문에 근거한 내용만"},
            "takeaway_highlights": {
                "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2,
                "description": "takeaway 안에 실제로 등장하는 핵심 구절 1~2개 (형광펜 마커 강조용)",
            },
            "closing_tag": {"type": "string", "description": "마무리 슬라이드 좌상단 태그 칩 문구, 예: '매일 브리핑'"},
            "closing_headline": {
                "type": "string",
                "description": (
                    "마무리 슬라이드 헤드라인 2줄 (줄바꿈은 \\n), issue_kr을 자연스럽게 포함. "
                    "줄바꿈(\\n)은 반드시 완결된 어절 경계에서만 넣을 것 — 단어 중간을 끊지 말 것. "
                    "나쁜 예: '금리가 내려가면 내 지\\n갑도 내려가' (X) / 좋은 예: '금리가 내려가면\\n내 지갑도 내려가' (O)."
                ),
            },
            "closing_highlight": {"type": "string", "description": "closing_headline 안에 실제 등장하는 강조할 짧은 구절"},
            "cover_image_query": {
                "type": "string",
                "description": (
                    "표지 배경사진 검색 영어 키워드 2~4단어. hook의 상황/감정을 은유하는 사물·공간·풍경 위주. "
                    "실존 인물 얼굴, 특정 기업 로고·브랜드명은 절대 쓰지 말 것 (기사가 특정 기업/인물 관련이어도 "
                    "이미지는 일반적인 개념 이미지로 대체)."
                ),
            },
            "explain_image_query": {"type": "string", "description": "2번 슬라이드 배경사진 검색 영어 키워드 2~4단어. 이슈를 은유하는 장면 위주, 실존 인물·브랜드명 금지."},
            "impact_image_query": {"type": "string", "description": "3번 슬라이드 배경사진 검색 영어 키워드 2~4단어. '영향/의미' 느낌의 장면 위주, 실존 인물·브랜드명 금지."},
            "closing_image_query": {"type": "string", "description": "4번 슬라이드 배경사진 검색 영어 키워드 2~4단어. 희망적/긍정적 톤, 실존 인물·브랜드명 금지."},
            "caption": {
                "type": "string",
                "description": (
                    "인스타그램 게시물 본문(캡션) 전체 텍스트. 기존 계정 톤(발랄하고 친밀한 인스타 매거진 톤)을 "
                    "그대로 따르되, 이건 실제 뉴스를 요약하는 콘텐츠이므로 과장·왜곡 없이 사실 위주로 작성:\n"
                    "1) 첫 줄: 시선을 끄는 후킹 문장 + 이모지/특수문자 조합\n"
                    "2) 공감 유도 짧은 문장 1~2줄\n"
                    "3) 소제목을 장식 구분선으로 감싸기: '∘···ʚ [소제목] ɞ···∘' 형식\n"
                    "4) 본문: 기사 요약을 짧고 리듬감 있게, 줄바꿈 자주, 문장 끝마다 이모지\n"
                    "5) 마지막에 행동 유도 문장 1줄\n"
                    "6) 그 다음 줄에 반드시 '※ 이 콘텐츠는 뉴스 요약이며 투자 조언이 아닙니다' 문구를 "
                    "읽기 쉬운 문장으로 포함 — 절대 생략 금지\n"
                    "제공된 원문에 없는 통계·인용을 캡션에 새로 지어내지 말 것."
                ),
            },
            "hashtags": {"type": "string", "description": "캡션 맨 끝에 붙일 해시태그 8~10개, 공백으로 구분, # 포함"},
        },
    },
}

NEWS_SYSTEM_PROMPT = """당신은 '웰로그(@welllog.kr)'라는 인스타그램 경제/금융 지식 계정의 콘텐츠 작가입니다.
매일 국내 경제 언론사에 실제로 보도된 기사 하나를 골라, 2030 직장인이 1분 안에 핵심을 파악할 수 있도록
쉽고 신뢰감 있게 브리핑하는 카드뉴스를 만듭니다.

가장 중요한 규칙 (반드시 지킬 것):
- 사용자 메시지로 제공되는 "기사 원문" 안에 실제로 있는 사실·수치만 사용하세요. 원문에 없는 내용,
  수치, 인용, 예측을 절대로 지어내지 마세요. 확실하지 않은 부분은 아예 언급하지 마세요.
- 모든 문장은 반드시 실제로 존재하는, 맞춤법이 정확한 표준 한국어 단어와 표현만으로 작성하세요.
  존재하지 않는 단어나 이상하게 조합된 신조어를 절대 만들어내지 마세요 (예: "빠듯하다"를 써야 할 자리에
  "쨌쩟하다" 같은 실재하지 않는 단어를 쓰는 것 금지). 특히 hook, closing_headline처럼 짧고 강조되는
  문장일수록 흔하고 자연스러운 실생활 단어를 쓰세요. 조금이라도 낯설거나 어색한 단어가 떠오르면 더
  평범하고 확실한 단어로 바꿔서 쓰세요. 제출하기 전에 모든 필드의 단어 하나하나가 실제 한국어 사전에
  있는 단어인지 스스로 다시 확인하세요.
- 원문 문장을 그대로 베끼지 말고, 반드시 쉬운 말로 다시 풀어서 쓰세요 (표절 금지, 패러프레이즈 필수).
- 특정 종목을 사라/팔라고 권유하거나 이 기사를 근거로 투자 결정을 유도하는 표현은 절대 쓰지 마세요.
  이것은 뉴스 요약이며 투자 조언이 아닙니다 — 캡션에 그 disclaimer를 반드시 포함하세요.
- 카드는 총 4장: 1) 표지 — 공감형 후킹(이슈 제목·구체 수치는 숨김) 2) 이슈 공개 + 무슨 일이 있었는지
  3단계 설명 3) 왜 중요한지 2가지 포인트 + 핵심 요약 4) 마무리. 표지에서 절대 이슈 제목이나 구체적
  수치를 먼저 보여주지 말고, 특정 타깃층이 공감할 상황/궁금증으로 먼저 던지세요.
- 이미지 검색 키워드에는 실존 인물 얼굴, 특정 기업 로고·브랜드명을 절대 쓰지 마세요 (실제 이슈가
  특정 기업·인물에 관한 것이어도, 이미지는 일반적인 개념·사물·공간 이미지로 대체하세요).
- summary/takeaway처럼 줄글이 길게 이어지는 부분은 밋밋해 보이지 않도록 핵심 구절 1~2개씩
  강조 표시용 필드(summary_highlights/takeaway_highlights)에 담아주세요.
"""


def fetch_news_candidates() -> list:
    """RSS 피드들을 순서대로 시도해서 기사 후보 목록(dict: title, link, source)을 모음."""
    candidates = []
    for feed in NEWS_FEEDS:
        try:
            resp = requests.get(feed["url"], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if not title or not link:
                    continue
                if any(p in title for p in SKIP_TITLE_PATTERNS):
                    continue
                candidates.append({"title": title, "link": link, "source": feed["name"]})
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] {feed['name']} RSS를 가져오지 못했습니다: {e}")
    return candidates


def load_used_news() -> list:
    if os.path.isfile(USED_NEWS_PATH):
        with open(USED_NEWS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_used_news(urls: list) -> None:
    os.makedirs(os.path.dirname(USED_NEWS_PATH), exist_ok=True)
    with open(USED_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)


def load_used_images() -> set:
    """한 번 쓴 Unsplash 사진(id 기준)은 다시 배경으로 쓰지 않기 위한 기록.
    용어 카드 쪽(generate_and_queue.py)과 파일을 공유해서, 계정 전체 기준으로 중복을 막음."""
    if os.path.isfile(USED_IMAGES_PATH):
        with open(USED_IMAGES_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_used_images(used_ids: set) -> None:
    os.makedirs(os.path.dirname(USED_IMAGES_PATH), exist_ok=True)
    with open(USED_IMAGES_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(used_ids), f, ensure_ascii=False, indent=2)


def queue_has_pending_items() -> bool:
    if not os.path.isdir(QUEUE_DIR):
        return False
    return any(
        os.path.isdir(os.path.join(QUEUE_DIR, d)) for d in os.listdir(QUEUE_DIR)
    )


def next_item_number() -> int:
    used_dirs = []
    for base in (QUEUE_DIR, POSTED_DIR):
        if os.path.isdir(base):
            used_dirs += [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    numbers = [int(d) for d in used_dirs if d.isdigit()]
    return (max(numbers) + 1) if numbers else 1


def fetch_article_text(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise RuntimeError(f"기사 본문을 가져오지 못했습니다: {url}")
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text or len(text) < 200:
        raise RuntimeError(f"기사 본문 추출 결과가 너무 짧습니다: {url}")
    return text[:6000]  # 프롬프트 길이 보호를 위한 상한


def pick_article_with_text(used_urls: list, max_attempts: int = 5) -> tuple:
    """새 기사 후보 중 하나를 골라 본문 추출까지 성공하는 것을 찾음.
    특정 기사가 본문 추출에 실패해도(영상 전용 페이지 등) 다음 후보로 넘어가서
    하루치 브리핑 전체가 실패하지 않도록 최대 max_attempts번 시도."""
    candidates = [c for c in fetch_news_candidates() if c["link"] not in used_urls]
    if not candidates:
        raise RuntimeError("사용 가능한 새 기사 후보를 찾지 못했습니다 (모두 이미 다뤘거나 RSS를 못 가져왔습니다).")

    last_error = None
    for article in candidates[:max_attempts]:
        try:
            text = fetch_article_text(article["link"])
            return article, text
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 본문 추출 실패, 다음 후보로 넘어갑니다: {article['title']} ({e})")
            last_error = e
    raise RuntimeError(f"후보 {min(len(candidates), max_attempts)}개 모두 본문 추출에 실패했습니다: {last_error}")


def generate_content(article: dict, article_text: str) -> dict:
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 자동 사용
    user_message = (
        "오늘 브리핑할 기사 정보:\n"
        f"- 언론사: {article['source']}\n"
        f"- 제목: {article['title']}\n"
        f"- 원문 URL: {article['link']}\n\n"
        "기사 원문 (아래 내용에 실제로 있는 사실만 사용하세요):\n"
        f'"""\n{article_text}\n"""\n\n'
        "위 기사를 바탕으로 submit_news_briefing 도구로 카드뉴스 콘텐츠를 제출해주세요."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2200,
        system=NEWS_SYSTEM_PROMPT,
        tools=[NEWS_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "submit_news_briefing"},
        messages=[{"role": "user", "content": user_message}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("모델이 구조화된 응답을 반환하지 않았습니다.")


def fetch_unsplash_photo(query: str, save_path: str, fallback_query: str, used_ids: set = None) -> dict:
    """Unsplash에서 query로 사진을 검색해 save_path에 저장.
    검색 결과가 없으면 fallback_query로 한 번 더 시도.
    used_ids에 담긴 사진(id)은 한 번 쓴 사진이라는 뜻이라 후보에서 제외함.
    반환값: {"photographer": ..., "photographer_url": ..., "id": ...}"""
    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY 환경변수가 설정되지 않았습니다.")

    used_ids = used_ids or set()
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}

    def search(q):
        resp = requests.get(
            f"{UNSPLASH_API}/search/photos",
            headers=headers,
            params={"query": q, "per_page": 12, "orientation": "portrait", "content_filter": "high"},
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        for r in results:
            if r.get("id") not in used_ids:
                return r
        return results[0] if results else None

    photo = search(query) or search(fallback_query)
    if not photo:
        raise RuntimeError(f"Unsplash에서 '{query}' / '{fallback_query}' 검색 결과를 찾지 못했습니다.")

    img_url = photo["urls"]["regular"]
    img_resp = requests.get(img_url, timeout=30)
    img_resp.raise_for_status()
    with open(save_path, "wb") as f:
        f.write(img_resp.content)

    download_location = photo.get("links", {}).get("download_location")
    if download_location:
        try:
            requests.get(download_location, headers=headers, timeout=10)
        except requests.RequestException:
            pass

    user = photo.get("user", {})
    return {
        "id": photo.get("id"),
        "photographer": user.get("name", "Unsplash"),
        "photographer_url": (user.get("links", {}).get("html", "https://unsplash.com") + "?utm_source=welllog&utm_medium=referral"),
    }


def bold(text: str, highlight: str) -> str:
    """헤드라인용 강조 — 포인트 컬러 텍스트(<b>)."""
    if highlight and highlight in text:
        return text.replace(highlight, f"<b>{highlight}</b>", 1)
    return text


def mark(text: str, highlights) -> str:
    """본문용 강조 — 형광펜 마커 스타일(<span class="mark">). 문자열/리스트 모두 허용."""
    if isinstance(highlights, str):
        highlights = [highlights] if highlights else []
    for h in sorted({h for h in (highlights or []) if h}, key=len, reverse=True):
        if h in text:
            text = text.replace(h, f'<span class="mark">{h}</span>', 1)
    return text


def render_html(tpl: str, mapping: dict) -> str:
    out = tpl
    for k, v in mapping.items():
        out = out.replace(f"%%{k}%%", str(v))
    return out


async def render_slides(data: dict, out_dir: str, used_image_ids: set = None) -> list:
    """카드 4장을 렌더링. 반환값: Unsplash 사진 출처 크레딧 리스트.
    used_image_ids에 담긴 사진은 배경으로 다시 고르지 않고, 새로 고른 사진의 id도
    즉시 이 set에 추가함 (카드 한 장 안에서 같은 사진이 두 번 나오는 것도 방지)."""
    os.makedirs(out_dir, exist_ok=True)
    used_image_ids = used_image_ids if used_image_ids is not None else set()

    issue_kr_html = f'<span class="accent-text">{data["issue_kr"]}</span>'

    bg_files = {}
    credits = []
    slide_queries = [
        ("cover", data["cover_image_query"], "_bg1.jpg"),
        ("explain", data["explain_image_query"], "_bg2.jpg"),
        ("impact", data["impact_image_query"], "_bg3.jpg"),
        ("closing", data["closing_image_query"], "_bg4.jpg"),
    ]
    for key, query, filename in slide_queries:
        path = os.path.join(out_dir, filename)
        credit = fetch_unsplash_photo(query, path, FALLBACK_QUERIES[key], used_image_ids)
        if credit.get("id"):
            used_image_ids.add(credit["id"])
        bg_files[key] = filename
        credits.append(credit)

    hook_html = bold(data["hook"], data.get("hook_highlight", "")).replace("\\n", "<br>").replace("\n", "<br>")
    slide1 = render_html(templates.SLIDE1_COVER, {
        "HOOK_TAG": data["hook_tag"],
        "HOOK_HTML": hook_html,
        "COVER_BG": bg_files["cover"],
    })

    slide2 = render_html(templates.SLIDE2_EXPLAIN, {
        "TERM_EN": "TODAY'S ISSUE",
        "TERM_HEADING_HTML": issue_kr_html,
        "REVEAL_TAG": data["reveal_tag"],
        "DEFINITION_HTML": mark(data["summary"], data.get("summary_highlights", [])),
        "STEP1_LABEL": data["step1_label"], "STEP1_VALUE": data["step1_value"],
        "STEP2_LABEL": data["step2_label"], "STEP2_VALUE": data["step2_value"],
        "STEP3_LABEL": data["step3_label"], "STEP3_VALUE": data["step3_value"],
        "FLOW_NOTE": data["flow_note"],
        "EXPLAIN_BG": bg_files["explain"],
    })

    slide3 = render_html(templates.SLIDE3_NEWS_IMPACT, {
        "IMPACT_TAG": data["impact_tag"],
        "IMPACT_HEADING": data["impact_heading"],
        "IMPACT1_LABEL": data["impact1_label"], "IMPACT1_VALUE": data["impact1_value"],
        "IMPACT2_LABEL": data["impact2_label"], "IMPACT2_VALUE": data["impact2_value"],
        "TAKEAWAY_HTML": mark(data["takeaway"], data.get("takeaway_highlights", [])),
        "SOURCE_NAME": data["_source_name"],
        "NEWS_IMPACT_BG": bg_files["impact"],
    })

    closing_headline_html = bold(
        data["closing_headline"], data.get("closing_highlight", "")
    ).replace("\\n", "<br>").replace("\n", "<br>")
    slide4 = render_html(templates.SLIDE4_CLOSING, {
        "CLOSING_TAG": data["closing_tag"],
        "CLOSING_HEADLINE_HTML": closing_headline_html,
        "CLOSING_BG": bg_files["closing"],
    })

    slides = [slide1, slide2, slide3, slide4]
    html_paths = []
    for i, html in enumerate(slides, start=1):
        path = os.path.join(out_dir, f"_slide{i}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        html_paths.append(path)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        for i, path in enumerate(html_paths, start=1):
            await page.goto(f"file://{os.path.abspath(path)}")
            await page.wait_for_timeout(150)
            await page.screenshot(path=os.path.join(out_dir, f"{i:02d}.png"))
        await browser.close()

    for path in html_paths:
        os.remove(path)
    for filename in bg_files.values():
        bg_path = os.path.join(out_dir, filename)
        if os.path.isfile(bg_path):
            os.remove(bg_path)

    return credits


def build_caption(data: dict, credits: list, article: dict) -> str:
    caption = data["caption"].strip().replace("\\n", "\n")

    raw_hashtags = data.get("hashtags", "").strip()
    tags = [t.rstrip(",.;ㆍ·") for t in re.findall(r"#[^\s#]+", raw_hashtags)]
    tags = list(dict.fromkeys(t for t in tags if t and t != "#"))
    hashtags = " ".join(tags) if tags else raw_hashtags

    seen = set()
    names = []
    for c in credits:
        name = c.get("photographer")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    photo_credit_line = f"사진: {', '.join(names)} (Unsplash)" if names else ""

    source_line = f'참고 기사: {article["source"]} · "{article["title"]}"'

    parts = [caption]
    if hashtags and hashtags not in caption:
        parts.append(hashtags)
    parts.append(source_line)
    if photo_credit_line:
        parts.append(photo_credit_line)
    return "\n\n".join(parts)


def main():
    if queue_has_pending_items():
        print("큐에 아직 처리되지 않은 항목이 있어 새로 생성하지 않습니다.")
        return

    used_urls = load_used_news()
    print(f"기존 다룬 기사 {len(used_urls)}개 로드 완료")

    article, article_text = pick_article_with_text(used_urls)
    print(f"오늘의 기사: [{article['source']}] {article['title']}")
    print(f"기사 본문 {len(article_text)}자 추출 완료")

    data = generate_content(article, article_text)
    data["_source_name"] = article["source"]
    print(f"생성된 이슈: {data['issue_kr']}")

    item_num = next_item_number()
    item_dir = os.path.join(QUEUE_DIR, f"{item_num:03d}")
    images_dir = os.path.join(item_dir, "images")

    used_image_ids = load_used_images()
    print(f"기존 사용 이미지 {len(used_image_ids)}장 로드 완료")

    credits = asyncio.run(render_slides(data, images_dir, used_image_ids))
    print(f"카드 이미지 4장 렌더링 완료: {images_dir}")
    save_used_images(used_image_ids)
    print(f"used_images.json 갱신 완료 (총 {len(used_image_ids)}장)")

    caption = build_caption(data, credits, article)
    with open(os.path.join(item_dir, "caption.json"), "w", encoding="utf-8") as f:
        json.dump({"caption": caption}, f, ensure_ascii=False, indent=2)
    print("caption.json 작성 완료")

    used_urls.append(article["link"])
    save_used_news(used_urls)
    print(f"used_news.json 갱신 완료 (총 {len(used_urls)}개)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
