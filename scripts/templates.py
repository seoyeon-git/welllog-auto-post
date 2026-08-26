"""
카드 4장(표지/설명/비교/마무리) HTML 템플릿 — knewnew 매거진 감도 리뉴얼.
플레이스홀더는 %%NAME%% 형식 — CSS의 중괄호와 충돌하지 않도록 .format() 대신
단순 문자열 치환(str.replace)을 사용합니다.

디자인 방향:
- 전체 슬라이드 크림/라이트 톤 통일 (밝은 톤 유지 요청 반영)
- 얇은 rule 라인, 큰 볼드 타이포 등 매거진 감도는 유지
- No.00X 같은 이슈 번호 태그는 제거 (군더더기 없는 레이아웃)
- 2번 슬라이드는 고정폭 박스 대신 번호가 매겨진 리스트(플렉스 자동 줄바꿈)로 바꿔서
  텍스트 길이에 상관없이 절대 넘치지 않도록 함.
"""

BASE_STYLE = """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1080px; height:1350px; font-family:'Noto Sans KR','Noto Sans CJK KR',sans-serif; overflow:hidden; }

.card { position:relative; width:1080px; height:1350px; overflow:hidden; }

.card.light {
  --bg1:#faf6ee; --bg2:#f3ece0; --fg:#1f2a24; --muted:#5a6b60;
  --accent:#c07a45; --hairline:rgba(31,42,36,0.14);
  background: linear-gradient(165deg, var(--bg1) 0%, var(--bg2) 100%);
  color: var(--fg);
}
.card.dark {
  --bg1:#1f2a24; --bg2:#141c18; --fg:#faf6ee; --muted:rgba(250,246,238,0.62);
  --accent:#e3a878; --hairline:rgba(250,246,238,0.18);
  background: linear-gradient(165deg, var(--bg1) 0%, var(--bg2) 100%);
  color: var(--fg);
}

.topbar { position:absolute; top:56px; left:56px; right:56px; display:flex; justify-content:space-between; align-items:center; }
.label-pill { color:var(--accent); font-size:22px; font-weight:700; letter-spacing:3px; text-transform:uppercase; }
.wordmark { color:var(--fg); font-size:30px; font-weight:800; letter-spacing:0.5px; }
.wordmark .well { font-style:italic; font-weight:500; font-family:'Georgia', serif; color:var(--accent); }
.topbar-rule { position:absolute; top:104px; left:56px; right:56px; height:1px; background:var(--hairline); }

.footer-rule { position:absolute; left:56px; right:56px; bottom:130px; height:1px; background:var(--hairline); }
.footer { position:absolute; left:56px; right:56px; bottom:64px; display:flex; justify-content:space-between; align-items:flex-end; }
.footer .tagline-en { font-size:14px; font-style:italic; color:var(--muted); line-height:1.5; max-width:640px; }
.footer .tagline-kr { font-size:13px; color:var(--muted); margin-top:4px; }
.footer .swipe { font-size:16px; font-weight:700; letter-spacing:1px; color:var(--muted); white-space:nowrap; }

.footer-simple { position:absolute; left:56px; right:56px; bottom:64px; text-align:right; }
.footer-simple .swipe { font-size:16px; font-weight:700; color:var(--muted); letter-spacing:1px; }
"""

# ---------------------------------------------------------------------------
# 1) 표지 — 크림 톤, 큰 용어 타이포
# ---------------------------------------------------------------------------
SLIDE1_COVER = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.cover-overline { position:absolute; left:56px; right:56px; top:212px; font-size:16px; font-weight:700; letter-spacing:4px; color:var(--muted); text-transform:uppercase; }
.cover-content { position:absolute; left:56px; right:56px; bottom:270px; }
.term-en { font-size:22px; font-weight:600; color:var(--accent); letter-spacing:4px; text-transform:uppercase; margin-bottom:22px; }
.term-kr { font-size:150px; font-weight:800; letter-spacing:-3px; line-height:1.04; color:var(--fg); }
.term-kr .accent { color:var(--accent); }
.hook { margin-top:34px; font-size:28px; font-weight:500; color:var(--muted); max-width:840px; line-height:1.5; }
</style></head>
<body>
  <div class="card light">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="topbar-rule"></div>
    <div class="cover-overline">WELLLOG · MONEY DICTIONARY</div>

    <div class="cover-content">
      <div class="term-en">%%TERM_EN%%</div>
      <div class="term-kr">%%TERM_KR_HTML%%</div>
      <div class="hook">%%HOOK%%</div>
    </div>

    <div class="footer-rule"></div>
    <div class="footer">
      <div>
        <div class="tagline-en">Welllog — a daily record of money wellness.</div>
        <div class="tagline-kr">매일 하나씩 쌓는 돈 감각</div>
      </div>
      <div class="swipe">SWIPE →</div>
    </div>
  </div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 2) 설명 — 크림 배경, 번호 리스트(고정폭 박스 아님 → 텍스트 길이 상관없이 안전)
# ---------------------------------------------------------------------------
SLIDE2_EXPLAIN = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.explain-heading { position:absolute; top:190px; left:56px; right:56px; font-size:52px; font-weight:800; letter-spacing:-1px; }
.explain-heading .accent { color:var(--accent); }
.definition { position:absolute; top:290px; left:56px; right:56px; font-size:29px; line-height:1.6; color:var(--fg); }
.definition b { color:var(--accent); font-weight:800; }

.divider-label { position:absolute; top:478px; left:56px; font-size:15px; font-weight:700; letter-spacing:3px; color:var(--muted); text-transform:uppercase; }
.divider-rule { position:absolute; top:510px; left:56px; right:56px; height:1px; background:var(--hairline); }

.step-list { position:absolute; top:532px; left:56px; right:56px; }
.step-row { display:flex; gap:26px; align-items:flex-start; padding:26px 0; border-bottom:1px solid var(--hairline); }
.step-num { font-size:36px; font-weight:800; color:var(--accent); width:58px; flex-shrink:0; line-height:1.1; }
.step-label { font-size:15px; font-weight:700; letter-spacing:2px; color:var(--muted); text-transform:uppercase; margin-bottom:8px; }
.step-value { font-size:23px; font-weight:700; color:var(--fg); line-height:1.45; }
.flow-note { margin-top:22px; font-size:17px; font-style:italic; color:var(--muted); line-height:1.5; }
</style></head>
<body>
  <div class="card light">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="topbar-rule"></div>

    <div class="explain-heading">%%TERM_KR%%란 <span class="accent">뭘까?</span></div>
    <div class="definition">%%DEFINITION_HTML%%</div>

    <div class="divider-label">Step by step</div>
    <div class="divider-rule"></div>

    <div class="step-list">
      <div class="step-row">
        <div class="step-num">01</div>
        <div><div class="step-label">%%STEP1_LABEL%%</div><div class="step-value">%%STEP1_VALUE%%</div></div>
      </div>
      <div class="step-row">
        <div class="step-num">02</div>
        <div><div class="step-label">%%STEP2_LABEL%%</div><div class="step-value">%%STEP2_VALUE%%</div></div>
      </div>
      <div class="step-row">
        <div class="step-num">03</div>
        <div><div class="step-label">%%STEP3_LABEL%%</div><div class="step-value">%%STEP3_VALUE%%</div></div>
      </div>
      <div class="flow-note">%%FLOW_NOTE%%</div>
    </div>

    <div class="footer-simple"><div class="swipe">다음 장에서 비교로 확인 →</div></div>
  </div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 3) 비교 — 크림 배경, 플랫 컬러 바 차트 + 인용구 스타일 콜아웃
# ---------------------------------------------------------------------------
SLIDE3_COMPARE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.compare-heading { position:absolute; top:190px; left:56px; right:56px; font-size:52px; font-weight:800; letter-spacing:-1px; }
.compare-sub { position:absolute; top:288px; left:56px; right:56px; font-size:25px; line-height:1.6; color:var(--muted); }

.chart-wrap { position:absolute; top:410px; left:56px; right:56px; height:520px; display:flex; align-items:flex-end; justify-content:center; gap:90px; }
.bar-col { display:flex; flex-direction:column; align-items:center; width:240px; }
.bar-value { font-size:28px; font-weight:800; color:var(--fg); margin-bottom:14px; }
.bar { width:168px; border-radius:4px 4px 0 0; }
.bar-a { background: var(--accent); }
.bar-b { background: #9db3a3; }
.bar-label { margin-top:16px; font-size:18px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:var(--muted); }

.chart-baseline { position:absolute; left:56px; right:56px; top:930px; height:1px; background:var(--hairline); }

.callout { position:absolute; top:966px; left:56px; right:56px; border-left:3px solid var(--accent); padding:22px 30px; font-size:24px; line-height:1.6; color:var(--fg); }
.callout b { color:var(--accent); font-weight:800; }

.disclaimer-row { position:absolute; left:56px; right:56px; bottom:64px; text-align:right; }
.disclaimer-row .disclaimer { font-size:14px; color:var(--muted); }
</style></head>
<body>
  <div class="card light">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="topbar-rule"></div>

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
    <div class="chart-baseline"></div>

    <div class="callout">%%CALLOUT_HTML%%</div>
    <div class="disclaimer-row"><div class="disclaimer">※ 일반적인 경제 개념 설명이며 투자 조언이 아닙니다</div></div>
  </div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 4) 마무리 — 표지와 짝을 이루는 크림 톤
# ---------------------------------------------------------------------------
SLIDE4_CLOSING = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.closing-content { position:absolute; left:56px; right:56px; bottom:300px; }
.closing-headline { font-size:58px; font-weight:800; line-height:1.32; letter-spacing:-1px; }
.closing-headline .accent, .closing-headline b { color:var(--accent); font-weight:800; }
.closing-sub { margin-top:26px; font-size:26px; color:var(--muted); line-height:1.6; max-width:760px; }
.cta-btn { display:inline-block; margin-top:44px; padding:20px 46px; border-radius:100px; background:var(--fg); color:var(--bg1); font-size:25px; font-weight:800; }
</style></head>
<body>
  <div class="card light">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="topbar-rule"></div>

    <div class="closing-content">
      <div class="closing-headline">%%CLOSING_HEADLINE_HTML%%</div>
      <div class="closing-sub">매일 하나씩, 어려운 경제 개념을 1분 안에 이해되게 정리해드려요.</div>
      <div class="cta-btn">팔로우하고 매일 받아보기 →</div>
    </div>

    <div class="footer-rule"></div>
    <div class="footer">
      <div>
        <div class="tagline-en">Welllog is a daily record of money wellness — small habits, compounded.</div>
        <div class="tagline-kr">매일 하나씩 쌓는 돈 감각</div>
      </div>
      <div class="swipe">@welllog.kr</div>
    </div>
  </div>
</body></html>
"""
