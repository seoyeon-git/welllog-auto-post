"""
매일 GitHub Actions가 실행하는 '용어 생성 + 배경사진 검색 + 카드 렌더링 + 큐 등록' 스크립트.

동작:
1. content/queue/ 에 아직 처리 안 된 항목이 있으면 아무것도 안 하고 종료
   (이전 발행이 실패해서 남아있는 항목을 먼저 처리하도록 하기 위함 — 중복/누락 방지)
2. content/used_terms.json 에서 이미 다룬 용어 목록을 읽음
3. Anthropic API(Claude)를 호출해서 새 경제/금융 용어 콘텐츠를 구조화된 형태로 생성
   (이미 다룬 용어는 제외하도록 프롬프트에 전달, 슬라이드별 배경사진 검색 키워드도 함께 생성)
4. Unsplash API로 슬라이드별 배경사진 4장을 검색·다운로드 (실존 인물/브랜드 없는 무료 스톡사진)
5. 카드 4장을 렌더링해서 content/queue/NNN/images/01~04.png 로 저장
6. content/queue/NNN/caption.json 작성 (Unsplash 사진 출처 크레딧 포함)
7. content/used_terms.json 에 새 용어 추가

필요한 환경변수:
- ANTHROPIC_API_KEY
- UNSPLASH_ACCESS_KEY (unsplash.com/developers 에서 무료 발급)

이후 scripts/publish_to_instagram.py 가 이 큐 항목을 그대로 집어서 게시합니다.
"""

import os
import re
import sys
import json
import asyncio

import anthropic
import requests
from playwright.async_api import async_playwright

import templates

MODEL = os.environ.get("CONTENT_MODEL", "claude-haiku-4-5")
QUEUE_DIR = "content/queue"
POSTED_DIR = "content/posted"
USED_TERMS_PATH = "content/used_terms.json"
USED_IMAGES_PATH = "content/used_images.json"

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
UNSPLASH_API = "https://api.unsplash.com"

# Unsplash 검색이 실패하거나 결과가 없을 때 슬라이드별로 쓸 안전한 대체 키워드
FALLBACK_QUERIES = {
    "cover": "city life window light",
    "explain": "notebook desk coffee",
    "compare": "coins jar savings",
    "closing": "sunrise window hope",
}

TOOL_SCHEMA = {
    "name": "submit_finance_card",
    "description": "오늘의 경제/금융 용어 카드뉴스 콘텐츠를 제출합니다.",
    "input_schema": {
        "type": "object",
        "required": [
            "term_kr", "term_en", "hook_tag", "hook", "hook_highlight",
            "reveal_tag", "definition", "definition_highlights",
            "step1_label", "step1_value", "step2_label", "step2_value",
            "step3_label", "step3_value", "flow_note",
            "compare_heading", "compare_setup",
            "bar_a_label", "bar_a_value", "bar_a_ratio",
            "bar_b_label", "bar_b_value", "bar_b_ratio",
            "callout", "callout_highlights",
            "closing_tag", "closing_headline", "closing_highlight",
            "cover_image_query", "explain_image_query",
            "compare_image_query", "closing_image_query",
            "caption", "hashtags",
        ],
        "properties": {
            "term_kr": {"type": "string", "description": "한글 용어. 2~5글자 정도 (예: 복리, 인플레이션, 신용점수)"},
            "term_en": {"type": "string", "description": "영문 표기 (예: Compound Interest)"},
            "hook_tag": {"type": "string", "description": "표지 좌상단에 붙는 짧은 태그 칩 문구, 2~6글자 (예: '월급루팡 주의', '적금러 필독', '자취생 공감')"},
            "hook": {
                "type": "string",
                "description": (
                    "표지 전체를 채우는 후킹 헤드라인. 절대 용어 이름 자체를 넣지 말 것 — 대신 특정 타깃층이 "
                    "'어 이거 내 얘기인데' 하고 공감할 만한 상황·불만·궁금증을 1~2문장으로 표현. "
                    "줄바꿈은 \\n 사용, 2줄 이내 권장. (예: '월급은 그대로인데\\n왜 매달 통장이 더 가벼워질까') "
                    "중요: 줄바꿈(\\n)은 반드시 완결된 어절(띄어쓰기로 구분되는 단위) 경계에서만 넣을 것 — "
                    "절대 단어 중간을 끊어서 다음 줄로 넘기면 안 됨. "
                    "나쁜 예: '금리가 내려가면 내 지\\n갑도 내려가' (X, '지갑'이라는 단어가 쪼개짐) / "
                    "좋은 예: '금리가 내려가면\\n내 지갑도 내려가' (O, 단어가 항상 한 줄 안에 온전히 들어감)."
                ),
            },
            "hook_highlight": {"type": "string", "description": "hook 문장 안에 실제로 등장하는 짧은 구절(1~4글자 권장) — 포인트 컬러로 강조됨. 그대로 부분 문자열 일치해야 함 (예: hook에 '이자'가 있으면 '이자')"},
            "reveal_tag": {"type": "string", "description": "2번 슬라이드(용어 공개) 좌상단 태그 칩 문구, 예: '오늘의 용어'"},
            "definition": {"type": "string", "description": "쉬운 말로 된 정의, 2문장 이내"},
            "definition_highlights": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 2,
                "description": (
                    "definition 안에 실제로 등장하는 핵심 구절 1~2개(형광펜 마커로 강조됨). 줄글이 지루해 "
                    "보이지 않도록, 가능하면 서로 겹치지 않는 짧은 구절 2개를 문장 앞/뒤에서 하나씩 고르세요. "
                    "각 구절은 definition 안에 그대로 부분 문자열로 존재해야 함."
                ),
            },
            "step1_label": {"type": "string"}, "step1_value": {"type": "string"},
            "step2_label": {"type": "string"}, "step2_value": {"type": "string"},
            "step3_label": {"type": "string"}, "step3_value": {"type": "string"},
            "flow_note": {"type": "string", "description": "3단계 흐름 아래 들어갈 짧은 설명 (예: '이 과정이 반복되면서 점점 커져요')"},
            "compare_heading": {"type": "string", "description": "비교 슬라이드 제목, 예: '비교해보면'"},
            "compare_setup": {"type": "string", "description": "비교 상황을 설명하는 한 문장"},
            "bar_a_label": {"type": "string"}, "bar_a_value": {"type": "string"},
            "bar_a_ratio": {"type": "number", "description": "0.3~1.0 사이, 막대 A의 상대적 높이 비율"},
            "bar_b_label": {"type": "string"}, "bar_b_value": {"type": "string"},
            "bar_b_ratio": {"type": "number", "description": "0.3~1.0 사이, 막대 B의 상대적 높이 비율"},
            "callout": {"type": "string", "description": "비교에서 얻는 핵심 인사이트 1~2문장"},
            "callout_highlights": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 2,
                "description": (
                    "callout 안에 실제로 등장하는 핵심 구절 1~2개(형광펜 마커로 강조됨). 줄글이 지루해 "
                    "보이지 않도록, 가능하면 서로 겹치지 않는 짧은 구절 2개를 골라주세요. 각 구절은 callout "
                    "안에 그대로 부분 문자열로 존재해야 함."
                ),
            },
            "closing_tag": {"type": "string", "description": "마무리 슬라이드 좌상단 태그 칩 문구, 예: '매일 하나씩'"},
            "closing_headline": {
                "type": "string",
                "description": (
                    "마무리 슬라이드 헤드라인 2줄 (줄바꿈은 \\n), 용어 이름을 자연스럽게 포함. "
                    "줄바꿈(\\n)은 반드시 완결된 어절 경계에서만 넣을 것 — 단어 중간을 끊지 말 것. "
                    "나쁜 예: '금리가 내려가면 내 지\\n갑도 내려가' (X) / 좋은 예: '금리가 내려가면\\n내 지갑도 내려가' (O)."
                ),
            },
            "closing_highlight": {"type": "string", "description": "closing_headline 안에 실제 등장하는 강조할 짧은 구절"},
            "cover_image_query": {
                "type": "string",
                "description": (
                    "표지 배경사진을 검색할 영어 키워드 2~4단어. hook의 상황/감정을 은유하는 사물·공간·풍경 위주로 "
                    "작성 (예: 'empty wallet', 'tired commute subway'). 실존 인물 얼굴이 크게 나올 만한 표현, "
                    "유명인 이름, 브랜드/로고 이름은 절대 쓰지 말 것."
                ),
            },
            "explain_image_query": {"type": "string", "description": "2번 슬라이드(용어 설명) 배경사진 검색 영어 키워드 2~4단어. 용어의 개념을 은유하는 장면 위주, 실존 인물·브랜드명 금지."},
            "compare_image_query": {"type": "string", "description": "3번 슬라이드(비교) 배경사진 검색 영어 키워드 2~4단어. 비교/대조 느낌의 장면 위주, 실존 인물·브랜드명 금지."},
            "closing_image_query": {"type": "string", "description": "4번 슬라이드(마무리) 배경사진 검색 영어 키워드 2~4단어. 희망적/긍정적 톤의 장면 위주, 실존 인물·브랜드명 금지."},
            "caption": {
                "type": "string",
                "description": (
                    "인스타그램 게시물 본문(캡션) 전체 텍스트. 요즘 인스타 매거진/인플루언서 계정 특유의 "
                    "발랄하고 친밀한 톤으로 작성 (딱딱한 설명문 금지). 다음 구조와 장치를 반드시 사용:\n"
                    "1) 첫 줄: 시선을 끄는 후킹 문장 + 이모지/특수문자 조합으로 마무리 (예: '🔍⋆꙳', '✨⠂˖')\n"
                    "2) 공감 유도 짧은 문장 1~2줄, 말줄임표(..)나 반말 섞인 친근한 어미 활용 가능 "
                    "(예: '~잖아..', '~더라구요', '~인데요!')\n"
                    "3) 소제목을 장식 구분선으로 감싸기: '∘···ʚ [소제목] ɞ···∘' 형식\n"
                    "4) 본문: 짧고 리듬감 있게 줄바꿈 자주, 문장 끝마다 이모지 하나씩 배치\n"
                    "5) 마지막에 행동 유도 문장 1줄 (예: '지금 바로 확인하고 ~해보세요')\n"
                    "6) 그 다음 줄에 (줄바꿈 두 번으로 구분) 반드시 '※ 일반적인 경제 개념 설명이며 "
                    "투자 조언이 아닙니다' 문구를 평범한 크기의 읽기 쉬운 문장으로 포함 — 절대 생략하거나 "
                    "숨기지 말 것\n"
                    "장식 기호는 매번 똑같이 반복하지 말고 이모지/기호 조합에 살짝 변주를 줄 것."
                ),
            },
            "hashtags": {"type": "string", "description": "캡션 맨 끝에 붙일 해시태그 8~10개, 공백으로 구분, # 포함"},
        },
    },
}

SYSTEM_PROMPT = """당신은 '웰로그(@welllog.kr)'라는 인스타그램 경제/금융 지식 계정의 콘텐츠 작가입니다.
매일 경제·금융·재테크 관련 용어 하나를 골라, 2030 직장인이 1분 안에 이해할 수 있도록 쉽고 친근하게 설명하는
카드뉴스 콘텐츠를 만듭니다.

카드는 총 4장이며, 표지는 용어 이름을 바로 보여주지 않고 특정 타깃층의 공감을 자극하는 후킹 헤드라인으로
시작합니다 (예: 인플레이션 → "월급은 그대로인데 왜 매달 통장이 더 가벼워질까" 처럼 용어 대신 상황/감정을
먼저 던지고, 용어 자체는 2번째 슬라이드에서 공개). 모든 슬라이드는 배경에 관련 사진이 깔리는 포토카드
형식이라, 각 슬라이드마다 어울리는 사진을 검색할 영어 키워드도 함께 제출해야 합니다.

규칙:
- 반드시 사실에 기반한 정확한 설명만 작성하세요. 불확실하면 보수적으로, 일반적으로 통용되는 정의를 사용하세요.
- 모든 문장은 반드시 실제로 존재하는, 맞춤법이 정확한 표준 한국어 단어와 표현만으로 작성하세요.
  존재하지 않는 단어나 이상하게 조합된 신조어를 절대 만들어내지 마세요 (예: "빠듯하다"를 써야 할 자리에
  "쨌쩟하다" 같은 실재하지 않는 단어를 쓰는 것 금지). 특히 hook, closing_headline처럼 짧고 강조되는
  문장일수록 흔하고 자연스러운 실생활 단어를 쓰세요. 조금이라도 낯설거나 어색한 단어가 떠오르면 더
  평범하고 확실한 단어로 바꿔서 쓰세요. 제출하기 전에 모든 필드의 단어 하나하나가 실제 한국어 사전에
  있는 단어인지 스스로 다시 확인하세요.
- 특정 종목, 특정 상품, 특정 회사를 추천하거나 "사세요/파세요" 같은 행동을 유도하는 표현은 절대 쓰지 마세요.
- 이것은 일반 경제 상식 콘텐츠이며 투자 조언이 아닙니다. 캡션에 반드시 그 disclaimer를 평범하게 읽히는 문장으로 포함하세요 (숨기거나 생략 금지).
- 숫자 예시(bar_a_value, bar_b_value 등)는 실제 통계를 사칭하지 말고, "예를 들어" 식의 이해를 돕는 예시라는 톤으로 작성하세요.
- 카드(표지/설명/비교/마무리) 슬라이드 문구는 담백하고 신뢰감 있게 유지하세요. 단, 표지의 hook만은
  설명체가 아니라 "어 내 얘기잖아" 싶은 공감형 후킹 문장이어야 합니다.
- 이미지 검색 키워드(cover_image_query 등)에는 실존 인물 얼굴, 유명인 이름, 브랜드/로고명을 절대 쓰지
  마세요. 사물·공간·풍경·손동작 등 은유적인 장면 위주로 작성하세요.
- 반면 caption(인스타 게시물 본문)은 요즘 인스타 매거진/인플루언서 계정 특유의 발랄하고 친밀한 톤으로
  작성하세요 — 장식 구분선(∘···ʚ ... ɞ···∘), 이모지, 말줄임표, 친근한 어미를 적극 활용해서 딱딱한
  설명문처럼 읽히지 않게 하세요. caption 필드의 상세 형식 지침을 반드시 따르세요.
- 이미 다룬 용어는 절대 다시 고르지 마세요.
- definition/callout처럼 줄글이 길게 이어지는 부분은 밋밋해 보이지 않도록, 각각 서로 겹치지 않는
  핵심 구절을 1~2개씩 정해서 definition_highlights/callout_highlights에 담아주세요 (형광펜 마커로
  강조되어 읽는 사람이 지루하지 않게 시선을 끕니다).

예시 caption 톤 (형식 참고용, 이 용어를 그대로 반복하지 말 것):
"금리만 보고 예금 넣었다가 오히려 손해보는 사람 여기 주목🔍⋆꙳
숫자만 보면 이자 붙는 것 같은데 실제론 마이너스일 수도 있다는 사실..

∘···ʚ 실질금리, 이것만 기억하면 끝 ɞ···∘

명목금리에서 물가상승률만 딱 빼면
내 돈이 진짜로 불어난 건지 바로 보이거든요💡

숫자에 속지 않는 법, 지금 바로 확인하고
똑똑하게 자산 지키는 사람 되어보세요🏦✨

※ 일반적인 경제 개념 설명이며 투자 조언이 아닙니다"
"""


def load_used_terms():
    if os.path.isfile(USED_TERMS_PATH):
        with open(USED_TERMS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_used_terms(terms):
    os.makedirs(os.path.dirname(USED_TERMS_PATH), exist_ok=True)
    with open(USED_TERMS_PATH, "w", encoding="utf-8") as f:
        json.dump(terms, f, ensure_ascii=False, indent=2)


def load_used_images() -> set:
    """한 번 쓴 Unsplash 사진(id 기준)은 다시 배경으로 쓰지 않기 위한 기록.
    용어 카드/뉴스 브리핑이 같은 파일을 공유해서, 계정 전체 기준으로 중복을 막음."""
    if os.path.isfile(USED_IMAGES_PATH):
        with open(USED_IMAGES_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_used_images(used_ids: set) -> None:
    os.makedirs(os.path.dirname(USED_IMAGES_PATH), exist_ok=True)
    with open(USED_IMAGES_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(used_ids), f, ensure_ascii=False, indent=2)


def queue_has_pending_items():
    if not os.path.isdir(QUEUE_DIR):
        return False
    return any(
        os.path.isdir(os.path.join(QUEUE_DIR, d)) for d in os.listdir(QUEUE_DIR)
    )


def next_item_number():
    used_dirs = []
    for base in (QUEUE_DIR, POSTED_DIR):
        if os.path.isdir(base):
            used_dirs += [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    numbers = [int(d) for d in used_dirs if d.isdigit()]
    return (max(numbers) + 1) if numbers else 1


def generate_content(used_terms: list) -> dict:
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 자동 사용
    used_list_str = ", ".join(used_terms) if used_terms else "(아직 없음)"
    user_message = (
        f"이미 다룬 용어 목록 (절대 중복 금지): {used_list_str}\n\n"
        "위 목록에 없는 새로운 경제/금융 용어 하나를 골라서 submit_finance_card 도구로 제출해주세요."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "submit_finance_card"},
        messages=[{"role": "user", "content": user_message}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("모델이 구조화된 응답을 반환하지 않았습니다.")


def fetch_unsplash_photo(query: str, save_path: str, fallback_query: str, used_ids: set = None) -> dict:
    """Unsplash에서 query로 사진을 검색해 save_path에 저장.
    검색 결과가 없으면 fallback_query로 한 번 더 시도.
    used_ids에 담긴 사진(id)은 한 번 쓴 사진이라는 뜻이라 후보에서 제외하고,
    아직 안 쓴 사진이 나올 때까지 검색 결과 여러 장 중에서 고름.
    반환값: {"photographer": ..., "photographer_url": ..., "id": ...}
    """
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
        # 검색 결과가 전부 이미 쓴 사진이면(흔치 않지만) 어쩔 수 없이 1순위 결과라도 반환
        return results[0] if results else None

    photo = search(query) or search(fallback_query)
    if not photo:
        raise RuntimeError(f"Unsplash에서 '{query}' / '{fallback_query}' 검색 결과를 찾지 못했습니다.")

    img_url = photo["urls"]["regular"]
    img_resp = requests.get(img_url, timeout=30)
    img_resp.raise_for_status()
    with open(save_path, "wb") as f:
        f.write(img_resp.content)

    # Unsplash API 가이드라인: 사진을 실제로 사용할 때 download 엔드포인트를 한 번 호출해야 함
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
    """본문(정의/콜아웃)용 강조 — 형광펜 마커 스타일(<span class="mark">).
    긴 줄글이 밋밋해 보이지 않도록 여러 구절을 동시에 강조할 수 있음 (문자열 1개 또는 리스트 모두 허용)."""
    if isinstance(highlights, str):
        highlights = [highlights] if highlights else []
    # 겹치는 구절이 있을 때 중첩 태그가 생기지 않도록 긴 구절부터 먼저 처리
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
    """카드 4장을 렌더링. 반환값: Unsplash 사진 출처 크레딧 리스트 (중복 제거 전).
    used_image_ids는 계정에서 이미 한 번 쓴 사진 id 모음 — 여기 담긴 사진은 배경으로 다시
    고르지 않음 (이 함수 실행 중 새로 고른 사진의 id도 즉시 이 set에 추가해서, 카드 한 장
    안에서 같은 사진이 두 번 나오는 것도 방지함)."""
    os.makedirs(out_dir, exist_ok=True)
    used_image_ids = used_image_ids if used_image_ids is not None else set()

    term_kr = data["term_kr"]
    # 용어 전체를 포인트 컬러로 강조 (예전엔 마지막 글자만 강조되던 버그가 있었음)
    term_kr_html = f'<span class="accent-text">{term_kr}</span>'

    # 1) 배경사진 4장 먼저 검색·다운로드
    bg_files = {}
    credits = []
    slide_queries = [
        ("cover", data["cover_image_query"], "_bg1.jpg"),
        ("explain", data["explain_image_query"], "_bg2.jpg"),
        ("compare", data["compare_image_query"], "_bg3.jpg"),
        ("closing", data["closing_image_query"], "_bg4.jpg"),
    ]
    for key, query, filename in slide_queries:
        path = os.path.join(out_dir, filename)
        credit = fetch_unsplash_photo(query, path, FALLBACK_QUERIES[key], used_image_ids)
        if credit.get("id"):
            used_image_ids.add(credit["id"])
        bg_files[key] = filename
        credits.append(credit)

    # 2) HTML 렌더링
    hook_html = bold(data["hook"], data.get("hook_highlight", "")).replace("\\n", "<br>").replace("\n", "<br>")
    slide1 = render_html(templates.SLIDE1_COVER, {
        "HOOK_TAG": data["hook_tag"],
        "HOOK_HTML": hook_html,
        "COVER_BG": bg_files["cover"],
    })

    slide2 = render_html(templates.SLIDE2_EXPLAIN, {
        "TERM_EN": data["term_en"].upper(),
        "TERM_HEADING_HTML": f"{term_kr_html} 란 뭘까?",
        "REVEAL_TAG": data["reveal_tag"],
        "DEFINITION_HTML": mark(data["definition"], data.get("definition_highlights", [])),
        "STEP1_LABEL": data["step1_label"], "STEP1_VALUE": data["step1_value"],
        "STEP2_LABEL": data["step2_label"], "STEP2_VALUE": data["step2_value"],
        "STEP3_LABEL": data["step3_label"], "STEP3_VALUE": data["step3_value"],
        "FLOW_NOTE": data["flow_note"],
        "EXPLAIN_BG": bg_files["explain"],
    })

    bar_a_ratio = max(0.3, min(1.0, float(data.get("bar_a_ratio", 0.6))))
    bar_b_ratio = max(0.3, min(1.0, float(data.get("bar_b_ratio", 0.9))))
    max_bar_px = 220

    slide3 = render_html(templates.SLIDE3_COMPARE, {
        "COMPARE_HEADING": data["compare_heading"],
        "COMPARE_SETUP": data["compare_setup"],
        "BAR_A_LABEL": data["bar_a_label"], "BAR_A_VALUE": data["bar_a_value"],
        "BAR_A_HEIGHT": int(max_bar_px * bar_a_ratio),
        "BAR_B_LABEL": data["bar_b_label"], "BAR_B_VALUE": data["bar_b_value"],
        "BAR_B_HEIGHT": int(max_bar_px * bar_b_ratio),
        "CALLOUT_HTML": mark(data["callout"], data.get("callout_highlights", [])),
        "COMPARE_BG": bg_files["compare"],
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

    # 임시 파일 정리 (HTML + 원본 배경사진, 최종 PNG만 남김)
    for path in html_paths:
        os.remove(path)
    for filename in bg_files.values():
        bg_path = os.path.join(out_dir, filename)
        if os.path.isfile(bg_path):
            os.remove(bg_path)

    return credits


def build_caption(data: dict, credits: list) -> str:
    caption = data["caption"].strip().replace("\\n", "\n")

    # 해시태그 정규화: AI가 줄바꿈/쉼표/붙임표기 등으로 이상하게 출력해도
    # "#태그" 형태만 뽑아서 공백 하나로 깔끔하게 이어붙임 (중복 제거, 순서 유지)
    raw_hashtags = data.get("hashtags", "").strip()
    tags = [t.rstrip(",.;ㆍ·") for t in re.findall(r"#[^\s#]+", raw_hashtags)]
    tags = list(dict.fromkeys(t for t in tags if t and t != "#"))
    hashtags = " ".join(tags) if tags else raw_hashtags

    # Unsplash API 가이드라인에 따른 사진 출처 표기 (중복 제거)
    seen = set()
    names = []
    for c in credits:
        name = c.get("photographer")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    credit_line = f"사진: {', '.join(names)} (Unsplash)" if names else ""

    parts = [caption]
    if hashtags and hashtags not in caption:
        parts.append(hashtags)
    if credit_line:
        parts.append(credit_line)
    return "\n\n".join(parts)


def main():
    if queue_has_pending_items():
        print("큐에 아직 처리되지 않은 항목이 있어 새로 생성하지 않습니다.")
        return

    used_terms = load_used_terms()
    print(f"기존 사용 용어 {len(used_terms)}개 로드 완료")

    data = generate_content(used_terms)
    print(f"생성된 용어: {data['term_kr']} ({data['term_en']})")

    item_num = next_item_number()
    item_dir = os.path.join(QUEUE_DIR, f"{item_num:03d}")
    images_dir = os.path.join(item_dir, "images")

    used_image_ids = load_used_images()
    print(f"기존 사용 이미지 {len(used_image_ids)}장 로드 완료")

    credits = asyncio.run(render_slides(data, images_dir, used_image_ids))
    print(f"카드 이미지 4장 렌더링 완료: {images_dir}")
    save_used_images(used_image_ids)
    print(f"used_images.json 갱신 완료 (총 {len(used_image_ids)}장)")

    caption = build_caption(data, credits)
    with open(os.path.join(item_dir, "caption.json"), "w", encoding="utf-8") as f:
        json.dump({"caption": caption}, f, ensure_ascii=False, indent=2)
    print("caption.json 작성 완료")

    used_terms.append(data["term_kr"])
    save_used_terms(used_terms)
    print(f"used_terms.json 갱신 완료 (총 {len(used_terms)}개)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
