"""
매일 GitHub Actions가 실행하는 '용어 생성 + 카드 렌더링 + 큐 등록' 스크립트.

동작:
1. content/queue/ 에 아직 처리 안 된 항목이 있으면 아무것도 안 하고 종료
   (이전 발행이 실패해서 남아있는 항목을 먼저 처리하도록 하기 위함 — 중복/누락 방지)
2. content/used_terms.json 에서 이미 다룬 용어 목록을 읽음
3. Anthropic API(Claude)를 호출해서 새 경제/금융 용어 콘텐츠를 구조화된 형태로 생성
   (이미 다룬 용어는 제외하도록 프롬프트에 전달)
4. 4장 카드 이미지를 렌더링해서 content/queue/NNN/images/01~04.png 로 저장
5. content/queue/NNN/caption.json 작성
6. content/used_terms.json 에 새 용어 추가

필요한 환경변수:
- ANTHROPIC_API_KEY

이후 scripts/publish_to_instagram.py 가 이 큐 항목을 그대로 집어서 게시합니다.
"""

import os
import sys
import json
import asyncio

import anthropic
from playwright.async_api import async_playwright

import templates

MODEL = os.environ.get("CONTENT_MODEL", "claude-haiku-4-5")
QUEUE_DIR = "content/queue"
POSTED_DIR = "content/posted"
USED_TERMS_PATH = "content/used_terms.json"

TOOL_SCHEMA = {
    "name": "submit_finance_card",
    "description": "오늘의 경제/금융 용어 카드뉴스 콘텐츠를 제출합니다.",
    "input_schema": {
        "type": "object",
        "required": [
            "term_kr", "term_en", "hook", "definition", "definition_highlight",
            "step1_label", "step1_value", "step2_label", "step2_value",
            "step3_label", "step3_value", "flow_note",
            "compare_heading", "compare_setup",
            "bar_a_label", "bar_a_value", "bar_a_ratio",
            "bar_b_label", "bar_b_value", "bar_b_ratio",
            "callout", "callout_highlight",
            "closing_headline", "closing_highlight",
            "caption", "hashtags",
        ],
        "properties": {
            "term_kr": {"type": "string", "description": "한글 용어. 2~5글자 정도 (예: 복리, 인플레이션, 신용점수)"},
            "term_en": {"type": "string", "description": "영문 표기 (예: Compound Interest)"},
            "hook": {"type": "string", "description": "표지에 들어갈 호기심 유발 한 문장 질문"},
            "definition": {"type": "string", "description": "쉬운 말로 된 정의, 2문장 이내"},
            "definition_highlight": {"type": "string", "description": "definition 안에 실제로 등장하는 짧은 핵심 구절 (그대로 부분 문자열 일치해야 함)"},
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
            "callout_highlight": {"type": "string", "description": "callout 안에 실제 등장하는 강조할 짧은 구절"},
            "closing_headline": {"type": "string", "description": "마무리 슬라이드 헤드라인 2줄 (줄바꿈은 \\n), 용어 이름을 자연스럽게 포함"},
            "closing_highlight": {"type": "string", "description": "closing_headline 안에 실제 등장하는 강조할 짧은 구절"},
            "caption": {"type": "string", "description": "인스타그램 게시물 본문(캡션) 전체 텍스트. 이모지 약간 포함, 친근하지만 정보 중심. 마지막에 반드시 '※ 일반적인 경제 개념 설명이며 투자 조언이 아닙니다' 문구 포함"},
            "hashtags": {"type": "string", "description": "캡션 맨 끝에 붙일 해시태그 8~10개, 공백으로 구분, # 포함"},
        },
    },
}

SYSTEM_PROMPT = """당신은 '웰로그(@welllog.kr)'라는 인스타그램 경제/금융 지식 계정의 콘텐츠 작가입니다.
매일 경제·금융·재테크 관련 용어 하나를 골라, 2030 직장인이 1분 안에 이해할 수 있도록 쉽고 친근하게 설명하는
카드뉴스 콘텐츠를 만듭니다.

규칙:
- 반드시 사실에 기반한 정확한 설명만 작성하세요. 불확실하면 보수적으로, 일반적으로 통용되는 정의를 사용하세요.
- 특정 종목, 특정 상품, 특정 회사를 추천하거나 "사세요/파세요" 같은 행동을 유도하는 표현은 절대 쓰지 마세요.
- 이것은 일반 경제 상식 콘텐츠이며 투자 조언이 아닙니다. 캡션 끝에 반드시 그 disclaimer를 포함하세요.
- 숫자 예시(bar_a_value, bar_b_value 등)는 실제 통계를 사칭하지 말고, "예를 들어" 식의 이해를 돕는 예시라는 톤으로 작성하세요.
- 톤은 친근하고 담백하게. 과장된 클릭베이트나 자극적 문구는 피하세요.
- 이미 다룬 용어는 절대 다시 고르지 마세요.
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


def bold(text: str, highlight: str) -> str:
    if highlight and highlight in text:
        return text.replace(highlight, f"<b>{highlight}</b>", 1)
    return text


def render_html(tpl: str, mapping: dict) -> str:
    out = tpl
    for k, v in mapping.items():
        out = out.replace(f"%%{k}%%", str(v))
    return out


async def render_slides(data: dict, day_index: int, out_dir: str):
    term_kr = data["term_kr"]
    term_kr_html = term_kr
    if len(term_kr) >= 2:
        term_kr_html = f'{term_kr[:-1]}<span class="accent">{term_kr[-1]}</span>'

    common = {"DAY_INDEX": f"{day_index:03d}"}

    slide1 = render_html(templates.SLIDE1_COVER, {
        **common,
        "TERM_EN": data["term_en"].upper(),
        "TERM_KR_HTML": term_kr_html,
        "HOOK": data["hook"],
    })

    slide2 = render_html(templates.SLIDE2_EXPLAIN, {
        **common,
        "TERM_KR": term_kr,
        "DEFINITION_HTML": bold(data["definition"], data.get("definition_highlight", "")),
        "STEP1_LABEL": data["step1_label"], "STEP1_VALUE": data["step1_value"],
        "STEP2_LABEL": data["step2_label"], "STEP2_VALUE": data["step2_value"],
        "STEP3_LABEL": data["step3_label"], "STEP3_VALUE": data["step3_value"],
        "FLOW_NOTE": data["flow_note"],
    })

    bar_a_ratio = max(0.3, min(1.0, float(data.get("bar_a_ratio", 0.6))))
    bar_b_ratio = max(0.3, min(1.0, float(data.get("bar_b_ratio", 0.9))))
    max_bar_px = 380

    slide3 = render_html(templates.SLIDE3_COMPARE, {
        **common,
        "COMPARE_HEADING": data["compare_heading"],
        "COMPARE_SETUP": data["compare_setup"],
        "BAR_A_LABEL": data["bar_a_label"], "BAR_A_VALUE": data["bar_a_value"],
        "BAR_A_HEIGHT": int(max_bar_px * bar_a_ratio),
        "BAR_B_LABEL": data["bar_b_label"], "BAR_B_VALUE": data["bar_b_value"],
        "BAR_B_HEIGHT": int(max_bar_px * bar_b_ratio),
        "CALLOUT_HTML": bold(data["callout"], data.get("callout_highlight", "")),
    })

    closing_headline_html = bold(
        data["closing_headline"], data.get("closing_highlight", "")
    ).replace("\\n", "<br>").replace("\n", "<br>")
    slide4 = render_html(templates.SLIDE4_CLOSING, {
        **common,
        "CLOSING_HEADLINE_HTML": closing_headline_html,
    })

    slides = [slide1, slide2, slide3, slide4]
    os.makedirs(out_dir, exist_ok=True)
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


def build_caption(data: dict) -> str:
    caption = data["caption"].strip().replace("\\n", "\n")
    hashtags = data.get("hashtags", "").strip()
    if hashtags and hashtags not in caption:
        caption = f"{caption}\n\n{hashtags}"
    return caption


def main():
    if queue_has_pending_items():
        print("큐에 아직 처리되지 않은 항목이 있어 새로 생성하지 않습니다.")
        return

    used_terms = load_used_terms()
    print(f"기존 사용 용어 {len(used_terms)}개 로드 완료")

    data = generate_content(used_terms)
    print(f"생성된 용어: {data['term_kr']} ({data['term_en']})")

    day_index = len(used_terms) + 1
    item_num = next_item_number()
    item_dir = os.path.join(QUEUE_DIR, f"{item_num:03d}")
    images_dir = os.path.join(item_dir, "images")

    asyncio.run(render_slides(data, day_index, images_dir))
    print(f"카드 이미지 4장 렌더링 완료: {images_dir}")

    caption = build_caption(data)
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
