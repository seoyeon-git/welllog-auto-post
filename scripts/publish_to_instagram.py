import os
import sys
import json
import time
import shutil
import datetime
import requests

API_VERSION = "v21.0"
IG_USER_ID = os.environ["IG_USER_ID"]
ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

# "owner/repo" 형태. GitHub Actions에서는 자동으로 채워집니다.
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "seoyeon-git/welllog-auto-post")
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

QUEUE_DIR = "content/queue"
POSTED_DIR = "content/posted"
FAILED_DIR = "content/failed"
FAIL_STATE_FILENAME = "_publish_fail_state.json"

# 같은 항목이 몇 번 연속으로 게시 실패하면 큐에서 빼서 content/failed/로 옮길지.
# 환경변수 MAX_CONSECUTIVE_FAILURES로 워크플로에서 덮어쓸 수 있음(기본 3).
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("MAX_CONSECUTIVE_FAILURES", "3"))

# media_publish 호출이 에러를 반환했을 때, 최근 N분 이내에 올라온 게시물 중
# 캡션이 일치하는 게 있는지 확인할 때 쓰는 "최근"의 기준(분).
VERIFY_RECENT_MINUTES = int(os.environ.get("VERIFY_RECENT_MINUTES", "15"))


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


def _normalize_caption(s: str) -> str:
    # 공백/줄바꿈 차이 때문에 오탐(같은데 다르다고 판단)이 생기지 않도록 다 제거하고 비교
    return "".join((s or "").split())


def check_if_already_published(caption: str, minutes: int = VERIFY_RECENT_MINUTES) -> bool:
    """media_publish 호출이 에러(예: '차단됨')를 반환해도, Meta 쪽에서는 실제로 게시가
    완료됐을 수 있습니다 (요청 처리와 응답이 서로 어긋나는 경우가 실제로 관찰됨 —
    2026-09-04, queue/018 사건: API는 403 '차단됨'을 반환했지만 인스타그램에는
    정상적으로 게시되어 있었음).

    그래서 게시 실패로 기록하기 전에, 최근 N분 이내에 올라온 게시물 중 캡션이
    똑같은 게 있는지 먼저 확인합니다. 있으면 "이미 게시된 것"으로 보고 성공 처리해서,
    다음 실행 때 같은 내용을 또 게시 시도해 중복 게시되는 걸 막습니다.
    확인 자체가 실패하면(네트워크 오류 등) 안전하게 "모름=실패"로 처리합니다.
    """
    try:
        resp = requests.get(
            f"https://graph.instagram.com/{API_VERSION}/{IG_USER_ID}/media",
            params={"fields": "caption,timestamp", "limit": "5", "access_token": ACCESS_TOKEN},
            timeout=30,
        )
        resp.raise_for_status()
        posts = resp.json().get("data", [])
    except Exception as verify_err:
        print(f"   (게시 여부 확인 중 오류 발생 — 실패로 간주합니다: {verify_err})", file=sys.stderr)
        return False

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    target = _normalize_caption(caption)

    for post in posts:
        ts = post.get("timestamp")
        if not ts:
            continue
        try:
            post_time = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if post_time >= cutoff and _normalize_caption(post.get("caption")) == target:
            return True

    return False


def publish_with_verification(creation_id: str, caption: str) -> dict:
    """publish_media()를 호출하되, 에러가 나면 바로 실패 처리하지 않고 실제로
    게시됐는지 먼저 확인합니다."""
    try:
        return publish_media(creation_id)
    except Exception as e:
        print(f"   게시 API가 에러를 반환했습니다: {e}", file=sys.stderr)
        print("   혹시 실제로는 이미 게시됐는지 최근 게시물을 확인합니다...", file=sys.stderr)
        if check_if_already_published(caption):
            print(
                "   확인 결과 방금 올라온 게시물 중 캡션이 일치하는 게 있습니다 — "
                "실제로는 게시에 성공한 것으로 보고 성공 처리합니다.",
                file=sys.stderr,
            )
            return {"id": None, "verified_published": True}
        print("   최근 게시물 중 일치하는 게 없습니다 — 실제로 실패한 것으로 처리합니다.", file=sys.stderr)
        raise


def load_fail_state(item_dir: str) -> dict:
    path = os.path.join(item_dir, FAIL_STATE_FILENAME)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"fail_count": 0, "errors": []}


def save_fail_state(item_dir: str, state: dict) -> None:
    path = os.path.join(item_dir, FAIL_STATE_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clear_fail_state(item_dir: str) -> None:
    path = os.path.join(item_dir, FAIL_STATE_FILENAME)
    if os.path.isfile(path):
        os.remove(path)


def give_up_on_item(item_dir: str, item_id: str, state: dict) -> None:
    """N번 연속 실패한 항목을 큐에서 빼서 content/failed/로 옮깁니다.
    (같은 차단된 액션을 계속 재시도해서 Meta 쪽 제한이 더 길어지는 걸 막기 위함)"""
    save_fail_state(item_dir, state)  # 옮기기 전에 최신 실패 기록부터 저장
    os.makedirs(FAILED_DIR, exist_ok=True)
    dest = os.path.join(FAILED_DIR, item_id)
    shutil.move(item_dir, dest)
    print(
        f"⚠️  '{item_id}'가 {state['fail_count']}번 연속 게시 실패해서 "
        f"{FAILED_DIR}/{item_id} 로 옮기고 큐에서 제외합니다. "
        "같은 항목을 계속 재시도하지 않도록 하기 위한 안전장치입니다. "
        "필요하면 나중에 직접 확인 후 큐로 되돌리거나 삭제해주세요.",
        file=sys.stderr,
    )


def process_item(item_id: str, item_dir: str) -> None:
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
        result = publish_with_verification(creation_id, caption)
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
        result = publish_with_verification(creation_id, caption)

    if result.get("verified_published"):
        print("게시 완료! (media_publish는 에러를 반환했지만, 실제 게시 확인됨)")
    else:
        print(f"게시 완료! media id: {result.get('id')}")

    # 성공했으니 이전 실패 기록이 있었다면 지워둠 (다음에 이 폴더 번호가 재사용될 일도 없음 —
    # 성공한 항목은 posted/로 옮겨지므로 이 파일도 같이 딸려가지만 의미 없어져서 지움)
    clear_fail_state(item_dir)

    os.makedirs(POSTED_DIR, exist_ok=True)
    dest = os.path.join(POSTED_DIR, item_id)
    shutil.move(item_dir, dest)
    print(f"{item_id} 를 posted/ 로 이동 완료")


def main() -> None:
    item_id = pick_next_item()
    item_dir = os.path.join(QUEUE_DIR, item_id)

    try:
        process_item(item_id, item_dir)
    except Exception as e:
        # item_dir가 이미 옮겨졌을 수도 있으니(정상 케이스는 아니지만) 방어적으로 확인
        if not os.path.isdir(item_dir):
            raise

        state = load_fail_state(item_dir)
        state["fail_count"] = state.get("fail_count", 0) + 1
        state.setdefault("errors", []).append({
            "time": datetime.datetime.utcnow().isoformat() + "Z",
            "error": str(e),
        })
        state["errors"] = state["errors"][-5:]  # 최근 5개까지만 보관

        if state["fail_count"] >= MAX_CONSECUTIVE_FAILURES:
            give_up_on_item(item_dir, item_id, state)
        else:
            save_fail_state(item_dir, state)
            print(
                f"'{item_id}' 게시 실패 ({state['fail_count']}/{MAX_CONSECUTIVE_FAILURES}회) "
                "— 다음 실행 때 이 항목을 다시 시도합니다.",
                file=sys.stderr,
            )
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
