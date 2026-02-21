import json
import os
import time
import pathlib
import tomllib
import httpx


def load_config():
    path = pathlib.Path("data/config.toml")
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def get_setting(config, section, key, env_key):
    if env_key in os.environ and os.environ[env_key].strip():
        return os.environ[env_key].strip()
    return str(config.get(section, {}).get(key, "") or "").strip()


def build_payloads():
    image_payload = {
        "type": "image",
        "payload": {
            "model": "grok-imagine-1.0",
            "prompt": "test image prompt",
            "size": "1024x1024",
            "response_format": "url",
        },
    }
    video_payload = {
        "type": "video",
        "payload": {
            "model": "grok-imagine-1.0-video",
            "prompt": "test video prompt",
            "video_config": {
                "aspect_ratio": "3:2",
                "video_length": 6,
                "resolution_name": "480p",
                "preset": "normal",
            },
        },
    }
    return image_payload, video_payload


def run_case(base_url, label, token, payload):
    url = f"{base_url}/v1/admin/tasks/async"
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    start = time.time()
    res = httpx.post(url, headers=headers, json=payload, timeout=10.0)
    elapsed_ms = (time.time() - start) * 1000
    return {
        "case": label,
        "status": res.status_code,
        "elapsed_ms": round(elapsed_ms, 2),
        "body": res.text,
    }


def assert_success(item):
    body = json.loads(item["body"])
    assert item["status"] == 200, item
    assert body.get("code") == 200, item
    assert "data" in body and "taskId" in body["data"], item


def assert_auth_error(item):
    body = json.loads(item["body"])
    assert item["status"] == 401, item
    err = body.get("error", {})
    assert err.get("type") == "authentication_error", item
    assert err.get("code") == "invalid_api_key", item


def main():
    config = load_config()
    base_url = get_setting(config, "app", "app_url", "GROK2API_BASE_URL") or "http://localhost:8000"
    app_key = get_setting(config, "app", "app_key", "GROK2API_APP_KEY")
    api_key = get_setting(config, "app", "api_key", "GROK2API_API_KEY") or "permission_key"
    image_payload, video_payload = build_payloads()

    cases = [
        ("valid", app_key),
        ("missing", None),
        ("expired", "expired_key"),
        ("permission", api_key),
    ]

    results = {"image": [], "video": []}
    for label, token in cases:
        results["image"].append(run_case(base_url, label, token, image_payload))
    for label, token in cases:
        results["video"].append(run_case(base_url, label, token, video_payload))

    for item in results["image"] + results["video"]:
        if item["case"] == "valid":
            assert_success(item)
        else:
            assert_auth_error(item)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
