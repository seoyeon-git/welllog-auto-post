"""
WellLog(@welllog.kr) 자동 게시 스크립트 (캐러셀 지원)
- content/queue/ 안의 폴더 중 이름순으로 가장 앞선 것 하나를 골라 게시합니다.
  각 폴더는 caption.json 과, 이미지 1장짜리는 image.png, 여러 장(캐러셀)이면
  images/ 폴더 안에 01.png, 02.png ... 처럼 정렬 가능한 이름으로 넣습니다.
- 이미지는 외부 업로드 없이 이 저장소(Public)의 GitHub raw URL을 그대로 사용합니다.
- Instagram Graph API(Instagram Login 방식)로 게시한 뒤,
- 사용한 폴더를 content/posted/ 로 옮깁니다 (이 변경사항은 워크플로가 자동 커밋합니다).

필요한 환경변수 (GitHub Actions Secrets에서 주입):
- IG_ACCESS_TOKEN : 장기(60일) 액세스 토큰
- IG_USER_ID      : Instagram 계정의 Instagram-scoped User ID

주의: 이 스크립트는 저장소가 Public이어야 동작합니다 (raw.githubusercontent.com URL을
인스타그램 서버가 로그인 없이 가져갈 수 있어야 하기 때문).
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

# "owner/repo" 형태. GitHub Actions에서는 자동으로 채워집니다.
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "seoyeon-git/welllog-auto-post")
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

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


def collect_image_paths(item_dir: str) -> list:
    images_subdir = os.path.join(item_dir, "images")
    if os.path.isdir(images_subdir):
        files = sorted(
            f for f in os.listdir(images_subdir)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        )
        if not files:
            raise RuntimeError(f"{images_subdir} 안에 이미지가 없습니다.")
        return [os.path.join(images_subdir, f) for f in files]

    single = os.path.join(item_dir, "image.png")
    if os.path.isfile(single):
        return [single]

    raise RuntimeError(f"{item_dir} 안에 image.png 또는 images/ 폴더가 없습니다.")


def build_raw_image_url(image_path: str) -> str:
    # 예: https://raw.githubusercontent.com/seoyeon-git/welllog-auto-post/main/content/queue/001/images/01.png
    url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_BRANCH}/{image_path}"
    resp = requests.head(url, timeout=30, allow_redirects=True)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"이미지 URL에 접근할 수 없습니다 ({resp.status_code}): {url}\n"
            "저장소가 Public인지 확인해주세요."
        )
    return url


def create_media_container(image_url: str, caption: str = None, is_carousel_item: bool = False) -> str:
    data = {"image_url": image_url, "access_token": ACCESS_TOKEN}
    if caption is not None:
        data["caption"] = caption
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    resp = requests.post(
        f"https://graph.instagram.com/{API_VERSION}/{IG_USER_ID}/media",
        data=data,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"미디어 컨테이너 생성 실패: {resp.status_code} {resp.text}")
    return resp.json()["id"]


def create_carousel_container(child_ids: list, caption: str) -> str:
    resp = requests.post(
        f"https://graph.instagram.com/{API_VERSION}/{IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"캐러셀 컨테이너 생성 실패: {resp.status_code} {resp.text}")
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

    image_paths = collect_image_paths(item_dir)
    print(f"이미지 {len(image_paths)}장 발견")

    print("1) 이미지 URL 확인 중...")
    image_urls = [build_raw_image_url(p) for p in image_paths]
    for u in image_urls:
        print(f"   -> {u}")

    if len(image_urls) == 1:
        print("2) 단일 이미지 게시물 컨테이너 생성 중...")
        creation_id = create_media_container(image_urls[0], caption=caption)
        print(f"   -> creation_id: {creation_id}")
        print("3) 처리 완료 대기 중...")
        wait_until_ready(creation_id)
        print("4) 게시 중...")
        result = publish_media(creation_id)
    else:
        print("2) 캐러셀 자식 컨테이너들 생성 중...")
        child_ids = []
        for u in image_urls:
            cid = create_media_container(u, is_carousel_item=True)
            print(f"   -> child creation_id: {cid}")
            child_ids.append(cid)

        print("3) 자식 컨테이너 처리 완료 대기 중...")
        for cid in child_ids:
            wait_until_ready(cid)

        print("4) 캐러셀(부모) 컨테이너 생성 중...")
        creation_id = create_carousel_container(child_ids, caption)
        print(f"   -> creation_id: {creation_id}")

        print("5) 캐러셀 처리 완료 대기 중...")
        wait_until_ready(creation_id)

        print("6) 게시 중...")
        result = publish_media(creation_id)

    print(f"게시 완료! media id: {result.get('id')}")

    os.makedirs(POSTED_DIR, exist_ok=True)
    dest = os.path.join(POSTED_DIR, item_id)
    shutil.move(item_dir, dest)
    print(f"{item_id} 를 posted/ 로 이동 완료")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
