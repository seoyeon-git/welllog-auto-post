"""
장기 액세스 토큰 갱신용 스크립트.
토큰은 발급 후 60일간 유효하며, 발급 후 24시간이 지난 시점부터 갱신 가능합니다.
45~50일 주기로 한 번씩 실행해서, 새로 나온 토큰을 GitHub Secrets의
IG_ACCESS_TOKEN 값으로 수동 업데이트해주세요.

실행 방법:
  IG_ACCESS_TOKEN=현재토큰 python scripts/refresh_token.py
"""

import os
import sys
import requests

ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

resp = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": ACCESS_TOKEN},
    timeout=30,
)

if resp.status_code >= 400:
    print(f"갱신 실패: {resp.status_code} {resp.text}", file=sys.stderr)
    sys.exit(1)

data = resp.json()
print("새 토큰이 발급됐습니다. 이 값을 GitHub Secrets의 IG_ACCESS_TOKEN에 업데이트하세요:\n")
print(data["access_token"])
print(f"\n만료까지 약 {data['expires_in'] // 86400}일 남음")
