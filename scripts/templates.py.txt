"""
카드 4장(표지/설명/비교/마무리) HTML 템플릿.
플레이스홀더는 %%NAME%% 형식 — CSS의 중괄호와 충돌하지 않도록 .format() 대신
단순 문자열 치환(str.replace)을 사용합니다.
"""

BASE_STYLE = """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1080px; height:1350px; font-family:'Noto Sans KR','Noto Sans CJK KR',sans-serif; overflow:hidden; }
.card {
  position:relative; width:1080px; height:1350px;
  background: linear-gradient(165deg, #faf6ee 0%, #f3ece0 100%);
  color:#1f2a24;
}
.topbar { position:absolute; top:56px; left:56px; right:56px; display:flex; justify-content:space-between; align-items:center; }
.label-pill { color:#c07a45; font-size:24px; font-weight:700; letter-spacing:2px; text-transform:uppercase; }
.wordmark { color:#1f2a24; font-size:32px; font-weight:800; letter-spacing:0.5px; }
.wordmark .well { font-style:italic; font-weight:500; font-family:'Georgia', serif; color:#5c7a68; }
.idx { position:absolute; top:110px; right:56px; color:rgba(31,42,36,0.4); font-size:18px; font-weight:600; letter-spacing:1px; }
.disclaimer { font-size:14px; color:rgba(31,42,36,0.4); }
"""

SLIDE1_COVER = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.center { position:absolute; left:0; right:0; top:50%; transform:translateY(-50%); text-align:center; }
.term-en { font-size:26px; font-weight:600; color:#5c7a68; letter-spacing:4px; text-transform:uppercase; margin-bottom:26px; }
.term-kr { font-size:180px; font-weight:800; letter-spacing:-4px; line-height:1.05; color:#1f2a24; }
.term-kr .accent { color:#c07a45; }
.hook { margin-top:44px; font-size:30px; font-weight:500; color:#5a6b60; padding:0 90px; line-height:1.5; }
.footer { position:absolute; left:56px; right:56px; bottom:66px; text-align:center; }
.swipe { font-size:20px; color:rgba(31,42,36,0.45); font-weight:600; letter-spacing:1px; }
</style></head>
<body>
  <div class="card">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="idx">MONEY WELLNESS · DAY %%DAY_INDEX%%</div>
    <div class="center">
      <div class="term-en">%%TERM_EN%%</div>
      <div class="term-kr">%%TERM_KR_HTML%%</div>
      <div class="hook">%%HOOK%%</div>
    </div>
    <div class="footer"><div class="swipe">옆으로 넘겨서 확인하기 →</div></div>
  </div>
</body></html>
"""

SLIDE2_EXPLAIN = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.heading { position:absolute; top:190px; left:56px; right:56px; font-size:54px; font-weight:800; letter-spacing:-1px; }
.heading .accent { color:#c07a45; }
.def { position:absolute; top:300px; left:56px; right:56px; font-size:28px; line-height:1.62; color:#33403a; }
.def b { color:#c07a45; font-weight:700; }
.diagram { position:absolute; top:560px; left:56px; right:56px; height:560px; }
.node {
  position:absolute; width:280px; height:150px; border-radius:16px;
  background: rgba(192,122,69,0.08); border:1.5px solid rgba(192,122,69,0.35);
  display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
}
.node .n-label { font-size:19px; color:#c07a45; font-weight:700; margin-bottom:8px; letter-spacing:1px; }
.node .n-value { font-size:28px; color:#1f2a24; font-weight:800; white-space:nowrap; }
.n1 { top:0; left:0; }
.n2 { top:0; right:0; }
.n3 { top:280px; left:50%; transform:translateX(-50%); width:460px; height:170px; background:rgba(192,122,69,0.14); border-color:#c07a45; }
.n3 .n-value { font-size:30px; }
.loop-label { position:absolute; top:495px; left:50%; transform:translateX(-50%); font-size:18px; color:rgba(31,42,36,0.55); font-weight:600; text-align:center; width:440px; }
.footer { position:absolute; left:56px; right:56px; bottom:60px; }
.swipe { font-size:18px; color:rgba(31,42,36,0.45); font-weight:600; text-align:right; }
</style></head>
<body>
  <div class="card">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="idx">MONEY WELLNESS · DAY %%DAY_INDEX%%</div>
    <div class="heading">%%TERM_KR%%란 <span class="accent">뭘까?</span></div>
    <div class="def">%%DEFINITION_HTML%%</div>
    <svg class="diagram" viewBox="0 0 968 560" style="position:absolute; top:560px; left:56px;">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="#c07a45" />
        </marker>
      </defs>
      <line x1="300" y1="75" x2="668" y2="75" stroke="#c07a45" stroke-width="3" marker-end="url(#arrow)" />
      <path d="M 828 150 C 828 260, 700 300, 600 340" stroke="#c07a45" stroke-width="3" fill="none" marker-end="url(#arrow)" />
      <path d="M 380 380 C 120 340, 40 200, 140 90" stroke="rgba(192,122,69,0.55)" stroke-width="3" fill="none" stroke-dasharray="6 8" marker-end="url(#arrow)" />
    </svg>
    <div class="diagram">
      <div class="node n1"><div class="n-label">%%STEP1_LABEL%%</div><div class="n-value">%%STEP1_VALUE%%</div></div>
      <div class="node n2"><div class="n-label">%%STEP2_LABEL%%</div><div class="n-value">%%STEP2_VALUE%%</div></div>
      <div class="node n3"><div class="n-label">%%STEP3_LABEL%%</div><div class="n-value">%%STEP3_VALUE%%</div></div>
    </div>
    <div class="loop-label">%%FLOW_NOTE%%</div>
    <div class="footer"><div class="swipe">다음 장에서 비교로 확인 →</div></div>
  </div>
</body></html>
"""

SLIDE3_COMPARE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.heading { position:absolute; top:190px; left:56px; right:56px; font-size:54px; font-weight:800; letter-spacing:-1px; }
.heading .accent { color:#c07a45; }
.sub { position:absolute; top:290px; left:56px; right:56px; font-size:26px; line-height:1.6; color:#5a6b60; }
.chart { position:absolute; top:400px; left:56px; right:56px; height:560px; display:flex; align-items:flex-end; justify-content:center; gap:120px; }
.bar-col { display:flex; flex-direction:column; align-items:center; width:220px; }
.bar-value { font-size:26px; font-weight:800; color:#1f2a24; margin-bottom:14px; }
.bar { width:180px; border-radius:14px 14px 0 0; }
.bar-a { background: linear-gradient(180deg, #d99a68 0%, #c07a45 100%); }
.bar-b { background: linear-gradient(180deg, #9db3a3 0%, #5c7a68 100%); }
.bar-label { margin-top:16px; font-size:22px; font-weight:700; color:#33403a; }
.baseline { position:absolute; left:56px; right:56px; top:958px; height:2px; background:rgba(31,42,36,0.2); }
.callout {
  position:absolute; top:998px; left:56px; right:56px;
  background: rgba(192,122,69,0.08); border:1px solid rgba(192,122,69,0.3); border-radius:18px;
  padding:28px 32px; font-size:25px; line-height:1.55; color:#33403a;
}
.callout b { color:#c07a45; font-weight:800; }
.footer { position:absolute; left:56px; right:56px; bottom:60px; }
</style></head>
<body>
  <div class="card">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="idx">MONEY WELLNESS · DAY %%DAY_INDEX%%</div>
    <div class="heading">%%COMPARE_HEADING%%</div>
    <div class="sub">%%COMPARE_SETUP%%</div>
    <div class="chart">
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
    <div class="baseline"></div>
    <div class="callout">%%CALLOUT_HTML%%</div>
    <div class="footer"><div class="disclaimer" style="text-align:right;">※ 일반적인 경제 개념 설명이며 투자 조언이 아닙니다</div></div>
  </div>
</body></html>
"""

SLIDE4_CLOSING = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>
""" + BASE_STYLE + """
.center { position:absolute; left:0; right:0; top:44%; transform:translateY(-50%); text-align:center; padding:0 90px; }
.big-line { font-size:60px; font-weight:800; line-height:1.3; letter-spacing:-1px; margin-bottom:30px; }
.big-line .accent, .big-line b { color:#c07a45; font-weight:800; }
.sub-line { font-size:27px; color:#5a6b60; line-height:1.6; margin-bottom:56px; }
.cta { display:inline-block; margin:0 auto; padding:20px 46px; border-radius:100px; background:#1f2a24; color:#faf6ee; font-size:27px; font-weight:800; }
.footer { position:absolute; left:56px; right:56px; bottom:66px; text-align:center; }
.tagline { font-size:16px; color:rgba(31,42,36,0.45); line-height:1.6; }
</style></head>
<body>
  <div class="card">
    <div class="topbar">
      <div class="label-pill">Economy</div>
      <div class="wordmark"><span class="well">well</span>LOG</div>
    </div>
    <div class="center">
      <div class="big-line">%%CLOSING_HEADLINE_HTML%%</div>
      <div class="sub-line">매일 하나씩, 어려운 경제 개념을<br>1분 안에 이해되게 정리해드려요.</div>
      <div class="cta">팔로우하고 매일 받아보기 →</div>
    </div>
    <div class="footer"><div class="tagline">Welllog is a daily record of money wellness — small habits, compounded.<br>매일 하나씩 쌓는 돈 감각.</div></div>
  </div>
</body></html>
"""
