"""
카드 4장(표지/설명/비교/마무리) HTML 템플릿 — 포토카드 리뉴얼 v2 (2026-08-27).
플레이스홀더는 %%NAME%% 형식 — CSS의 중괄호와 충돌하지 않도록 .format() 대신
단순 문자열 치환(str.replace)을 사용합니다.

v2에서 반영한 사용자 피드백:
- 표지/마무리 헤드라인을 인스타그램 "피드 그리드" 정사각형 크롭 안전 영역
  (1080x1350 중 위/아래 135px씩은 그리드 썸네일에서 잘림) 안으로 이동
- 표지 헤드라인 안에 특정 단어만 강조(포인트 컬러) 가능 (hook_highlight)
- 2/3번 슬라이드 정보 패널을 "AI 보고서" 느낌의 가는 구분선+표 형태에서
  탈피 — 원형 넘버 배지, 하이라이터 마커 강조, 더 큰 타이포로 매거진 카드 느낌으로 전면 교체
- 용어 강조 시 마지막 글자 한 글자만이 아니라 단어 전체에 포인트 컬러 적용
"""

# 인스타그램 피드 그리드는 4:5(1080x1350) 이미지를 정사각형으로 가운데 크롭해서 보여줌
# → 위/아래 각 135px은 그리드 썸네일에서는 잘릴 수 있는 "안전하지 않은" 영역.
# 헤드라인 등 핵심 텍스트는 항상 이 안전 영역(135~1215) 안에 배치.
FEED_SAFE_TOP = 135
FEED_SAFE_BOTTOM = 1215

PHOTO_BAND_HEIGHT = 560  # 2/3번 슬라이드 상단 사진 밴드 높이(px)

BASE_STYLE = """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1080px; height:1350px; font-family:'Noto Sans KR','Noto Sans CJK KR',sans-serif; overflow:hidden; }

.card { position:relative; width:1080px; height:1350px; overflow:hidden; background:#141c18; color:#faf6ee; }

:root, .card {
  --accent:#e3a878; --accent-soft:rgba(227,168,120,0.4); --cream:#faf6ee;
  --muted-on-dark:rgba(250,246,238,0.75);
  --panel-bg:#faf6ee; --panel-fg:#20241e; --panel-muted:#6b7a70;
}

.photo-bg { position:absolute; top:0; left:0; width:100%; height:100%; object-fit:cover; }

/* 풀블리드 슬라이드(1,4)용 스크림 — 아래로 갈수록 진해져서 텍스트 가독성 확보 */
.scrim-full { position:absolute; inset:0;
  background: linear-gradient(180deg, rgba(10,14,12,0.15) 0%, rgba(10,14,12,0.10) 30%, rgba(10,14,12,0.62) 62%, rgba(10,14,12,0.94) 100%);
}
.scrim-top { position:absolute; top:0; left:0; right:0; height:240px;
  background: linear-gradient(180deg, rgba(10,14,12,0.5) 0%, rgba(10,14,12,0) 100%);
}
.scrim-band-bottom { position:absolute; left:0; right:0; height:180px;
  background: linear-gradient(180deg, rgba(10,14,12,0) 0%, rgba(10,14,12,0.4) 100%);
}

.topbar { position:absolute; top:56px; left:56px; right:56px; z-index:5; display:flex; justify-content:space-between; align-items:center; }
.tag-pill { display:inline-block; padding:10px 22px; border-radius:100px; background:rgba(250,246,238,0.18); backdrop-filter:blur(6px); color:var(--cream); font-size:21px; font-weight:800; letter-spacing:0.5px; }
.wordmark { color:var(--cream); font-size:28px; font-weight:800; letter-spacing:0.5px; text-shadow:0 1px 8px rgba(0,0,0,0.35); }
.wordmark .well { font-style:italic; font-weight:500; font-family:'Georgia', serif; color:var(--accent); }

.swipe-cue { position:absolute; right:56px; bottom:60px; z-index:5; font-size:18px; font-weight:800; letter-spacing:1px; color:var(--cream); text-shadow:0 1px 8px rgba(0,0,0,0.4); }

/* 하단 정보 패널 (2,3번 슬라이드) — flex 세로 흐름, 절대좌표 없이 자연스럽게 쌓임 */
.panel { position:absolute; left:0; right:0; bottom:0; background:var(--panel-bg); color:var(--panel-fg);
  padding:48px 56px 56px 56px; display:flex; flex-direction:column; }

/* 강조 단어: 밑줄 대신 형광펜(하이라이터) 마커 느낌 */
.mark { background: linear-gradient(transparent 58%, var(--accent-soft) 58%); font-weight:800; padding:0 1px; }
.accent-text { color:var(--accent); font-weight:800; }
"""

# ---------------------------------------------------------------------------
# 1) 표지 — 풀블리드 사진 + 후킹 헤드라인 (피드 크롭 안전 영역 안에 배치)
# ---------------------------------------------------------------------------
SLIDE1_COVER = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.cover-content { position:absolute; left:56px; right:80px; top:640px; z-index:5; }
.hook-headline { font-size:66px; font-weight:800; line-height:1.32; letter-spacing:-1.5px; color:var(--cream); text-shadow:0 2px 20px rgba(0,0,0,0.4); }
.hook-headline b { color:var(--accent); font-weight:800; }
</style></head>
<body>
  <div class="card">
    <img class="photo-bg" src="%%COVER_BG%%">
    <div class="scrim-full"></div>
    <div class="scrim-top"></div>

    <div class="topbar">
      <div class="tag-pill">%%HOOK_TAG%%</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>

    <div class="cover-content">
      <div class="hook-headline">%%HOOK_HTML%%</div>
    </div>
    <div class="swipe-cue">SWIPE →</div>
  </div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 2) 설명 — 상단 사진 밴드 + 하단 패널(용어 공개 + 정의 + 3단계, 매거진 스타일)
# ---------------------------------------------------------------------------
SLIDE2_EXPLAIN = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.photo-band { position:absolute; top:0; left:0; right:0; height:""" + str(PHOTO_BAND_HEIGHT) + """px; overflow:hidden; }
.panel-explain { top:""" + str(PHOTO_BAND_HEIGHT) + """px; }

.reveal-overline { font-size:17px; font-weight:800; letter-spacing:3px; color:var(--accent); text-transform:uppercase; margin-bottom:10px; }
.term-heading { font-size:56px; font-weight:800; letter-spacing:-1.5px; margin-bottom:20px; }
.term-heading .accent-text { color:var(--accent); }
.definition { font-size:31px; line-height:1.56; font-weight:500; color:var(--panel-fg); margin-bottom:30px; letter-spacing:-0.3px; }

.step-list { display:flex; flex-direction:column; gap:22px; }
.step-row { display:flex; gap:20px; align-items:flex-start; }
.step-badge { flex-shrink:0; width:48px; height:48px; border-radius:50%; background:var(--accent); color:#241a10;
  display:flex; align-items:center; justify-content:center; font-size:22px; font-weight:800; }
.step-label { font-size:15px; font-weight:800; letter-spacing:1px; color:var(--panel-muted); margin-bottom:3px; }
.step-value { font-size:23px; font-weight:700; color:var(--panel-fg); line-height:1.42; letter-spacing:-0.2px; }
.flow-note { margin-top:26px; font-size:18px; font-weight:600; color:var(--panel-muted); line-height:1.5; }
</style></head>
<body>
  <div class="card">
    <div class="photo-band">
      <img class="photo-bg" src="%%EXPLAIN_BG%%">
      <div class="scrim-band-bottom" style="top:""" + str(PHOTO_BAND_HEIGHT - 180) + """px;"></div>
      <div class="scrim-top"></div>
    </div>

    <div class="topbar">
      <div class="tag-pill">%%REVEAL_TAG%%</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>

    <div class="panel panel-explain">
      <div class="reveal-overline">%%TERM_EN%%</div>
      <div class="term-heading">%%TERM_KR_HTML%% 란 뭘까?</div>
      <div class="definition">%%DEFINITION_HTML%%</div>

      <div class="step-list">
        <div class="step-row">
          <div class="step-badge">1</div>
          <div><div class="step-label">%%STEP1_LABEL%%</div><div class="step-value">%%STEP1_VALUE%%</div></div>
        </div>
        <div class="step-row">
          <div class="step-badge">2</div>
          <div><div class="step-label">%%STEP2_LABEL%%</div><div class="step-value">%%STEP2_VALUE%%</div></div>
        </div>
        <div class="step-row">
          <div class="step-badge">3</div>
          <div><div class="step-label">%%STEP3_LABEL%%</div><div class="step-value">%%STEP3_VALUE%%</div></div>
        </div>
      </div>
      <div class="flow-note">%%FLOW_NOTE%%</div>
    </div>
  </div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 3) 비교 — 상단 사진 밴드 + 하단 패널(바 차트 + 콜아웃, 매거진 스타일)
# ---------------------------------------------------------------------------
SLIDE3_COMPARE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.photo-band { position:absolute; top:0; left:0; right:0; height:""" + str(PHOTO_BAND_HEIGHT) + """px; overflow:hidden; }
.panel-compare { top:""" + str(PHOTO_BAND_HEIGHT) + """px; }

.compare-heading { font-size:48px; font-weight:800; letter-spacing:-1.3px; margin-bottom:12px; }
.compare-sub { font-size:23px; font-weight:500; line-height:1.5; color:var(--panel-muted); margin-bottom:28px; }

.chart-wrap { display:flex; align-items:flex-end; justify-content:center; gap:70px; height:250px; margin-bottom:26px; }
.bar-col { display:flex; flex-direction:column; align-items:center; width:210px; }
.bar-value { font-size:26px; font-weight:800; color:var(--panel-fg); margin-bottom:12px; }
.bar { width:140px; border-radius:16px 16px 6px 6px; }
.bar-a { background: var(--accent); }
.bar-b { background: #9db3a3; }
.bar-label { margin-top:14px; font-size:17px; font-weight:800; letter-spacing:0.5px; color:var(--panel-muted); }

.callout { background:rgba(227,168,120,0.16); border-radius:16px; padding:22px 26px; font-size:23px; font-weight:600; line-height:1.55; color:var(--panel-fg); margin-bottom:16px; }
.disclaimer { font-size:14px; color:var(--panel-muted); text-align:right; margin-top:auto; }
</style></head>
<body>
  <div class="card">
    <div class="photo-band">
      <img class="photo-bg" src="%%COMPARE_BG%%">
      <div class="scrim-band-bottom" style="top:""" + str(PHOTO_BAND_HEIGHT - 180) + """px;"></div>
      <div class="scrim-top"></div>
    </div>

    <div class="topbar">
      <div class="tag-pill">Compare</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>

    <div class="panel panel-compare">
      <div class="compare-heading">%%COMPARE_HEADING%%</div>
      <div class="compare-sub">%%COMPARE_SETUP%%</div>

      <div class="chart-wrap">
        <div class="bar-col">
          <div class="bar-value">%%BAR_A_VALUE%%</div>
          <div class="bar bar-a" style="height:%%BAR_A_HEIGHT%%px;"></div>
          <div class="bar-label">%%BAR_A_LABEL%%</div>
        </div>
        <div class="bar-col">
          <div class="bar-value">%%BAR_B_VALUE%%</div>
          <div class="bar bar-b" style="height:%%BAR_B_HEIGHT%%px;"></div>
          <div class="bar-label">%%BAR_B_LABEL%%</div>
        </div>
      </div>

      <div class="callout">%%CALLOUT_HTML%%</div>
      <div class="disclaimer">※ 일반적인 경제 개념 설명이며 투자 조언이 아닙니다</div>
    </div>
  </div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 4) 마무리 — 풀블리드 사진 + 헤드라인 + CTA (피드 크롭 안전 영역 안에 배치)
# ---------------------------------------------------------------------------
SLIDE4_CLOSING = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.closing-content { position:absolute; left:56px; right:80px; top:660px; z-index:5; }
.closing-headline { font-size:58px; font-weight:800; line-height:1.32; letter-spacing:-1.3px; color:var(--cream); text-shadow:0 2px 18px rgba(0,0,0,0.4); }
.closing-headline b { color:var(--accent); font-weight:800; }
.closing-sub { margin-top:24px; font-size:23px; font-weight:500; color:var(--muted-on-dark); line-height:1.6; max-width:760px; text-shadow:0 1px 10px rgba(0,0,0,0.3); }
.cta-btn { display:inline-block; margin-top:34px; padding:19px 44px; border-radius:100px; background:var(--cream); color:#1f2a24; font-size:23px; font-weight:800; }
</style></head>
<body>
  <div class="card">
    <img class="photo-bg" src="%%CLOSING_BG%%">
    <div class="scrim-full"></div>
    <div class="scrim-top"></div>

    <div class="topbar">
      <div class="tag-pill">%%CLOSING_TAG%%</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>

    <div class="closing-content">
      <div class="closing-headline">%%CLOSING_HEADLINE_HTML%%</div>
      <div class="closing-sub">매일 하나씩, 어려운 경제 개념을 1분 안에 이해되게 정리해드려요.</div>
      <div class="cta-btn">팔로우하고 매일 받아보기 →</div>
    </div>
  </div>
</body></html>
"""
