"""
WellLog(@welllog.kr) 자동 게시 스크립트
- content/queue/ 안의 폴더 중 이름순으로 가장 앞선 것 하나를 골라 게시합니다.
  각 폴더는 caption.json 과 image.png 를 포함합니다.
- catbox.moe에 이미지를 업로드해 공개 URL을 확보하고 (별도 계정/키 불필요)
- Instagram Graph API(Instagram Login 방식)로 게시한 뒤,
- 사용한 폴더를 content/posted/ 로 옮깁니다 (이 변경사항은 워크플로가 자동 커밋합니다).

필요한 환경변수 (GitHub Actions Secrets에서 주입):
- IG_ACCESS_TOKEN : 장기(60일) 액세스 토큰
- IG_USER_ID      : Instagram 계정의 Instagram-scoped User ID
"""

import os
import sys
import json
import time
import shutil
import requests

API_VERSION = "v21.0"
IG_USER_ID = os.environ["IG_USER_ID"]
ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

QUEUE_DIR = "content/queue"
POSTED_DIR = "content/posted"


def pick_next_item() -> str:
    if not os.path.isdir(QUEUE_DIR):
        raise RuntimeError(f"{QUEUE_DIR} 폴더가 없습니다.")
    items = sorted(
        d for d in os.listdir(QUEUE_DIR)
        if os.path.isdir(os.path.join(QUEUE_DIR, d))
    )
    if not items:
        raise RuntimeError("큐가 비어있습니다. 게시할 콘텐츠를 채워주세요.")
    return items[0]


def upload_to_catbox(image_path: str) -> str:
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=60,
        )
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"catbox 업로드 실패: {url}")
    return url


def create_media_container(image_url: str, caption: str) -> str:
    resp = requests.post(
        f"https://graph.instagram.com/{API_VERSION}/{IG_USER_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"미디어 컨테이너 생성 실패: {resp.status_code} {resp.text}")
    return resp.json()["id"]


def wait_until_ready(creation_id: str, timeout: int = 180, interval: int = 5) -> None:
    elapsed = 0
    while elapsed < timeout:
        resp = requests.get(
            f"https://graph.instagram.com/{API_VERSION}/{creation_id}",
            params={"fields": "status_code", "access_token": ACCESS_TOKEN},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")
        print(f"  상태: {status} (경과 {elapsed}s)")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("미디어 컨테이너 처리 실패 (ERROR)")
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError("미디어 컨테이너가 시간 내에 준비되지 않았습니다")


def publish_media(creation_id: str) -> dict:
    resp = requests.post(
        f"https://graph.instagram.com/{API_VERSION}/{IG_USER_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"게시 실패: {resp.status_code} {resp.text}")
    return resp.json()


def main() -> None:
    item_id = pick_next_item()
    item_dir = os.path.join(QUEUE_DIR, item_id)
    print(f"이번에 게시할 항목: {item_id}")

    with open(os.path.join(item_dir, "caption.json"), "r", encoding="utf-8") as f:
        caption = json.load(f)["caption"]
    image_path = os.path.join(item_dir, "image.png")

    print("1) 이미지를 catbox.moe에 업로드 중...")
    image_url = upload_to_catbox(image_path)
    print(f"   -> {image_url}")

    print("2) 인스타그램 미디어 컨테이너 생성 중...")
    creation_id = create_media_container(image_url, caption)
    print(f"   -> creation_id: {creation_id}")

    print("3) 처리 완료 대기 중...")
    wait_until_ready(creation_id)

    print("4) 게시 중...")
    result = publish_media(creation_id)
    print(f"게시 완료! media id: {result.get('id')}")

    os.makedirs(POSTED_DIR, exist_ok=True)
    dest = os.path.join(POSTED_DIR, item_id)
    shutil.move(item_dir, dest)
    print(f"5) {item_id} 를 posted/ 로 이동 완료")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
