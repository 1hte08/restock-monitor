"""補貨監控：檢查 Shopify 商品各版本是否有貨，由缺貨變有貨時發 Discord 通知。"""
import json
import os
from pathlib import Path

import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MENTION_USER_ID = os.environ.get("DISCORD_USER_ID", "")  # 選填：要 @ 你自己的 Discord 使用者 ID
STATE_FILE = Path("state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (restock-monitor)"}

# 要監控的商品網址，之後想加就往下加
PRODUCTS = [
    "https://hello82.com/products/signed-tws-tws-2nd-single-album-to-us",
    "https://shop.kpopnara.com/collections/home-page/products/tws-2nd-single-album-to-us-closer-ver-signed",
    "https://shop.kpopnara.com/collections/home-page/products/tws-2nd-single-album-to-us-beyond-ver-signed",
]


def fetch_variants(url):
    """Shopify 商品頁網址後面加 .js 會回傳 JSON，裡面有每個版本的 available。"""
    api = url.split("?")[0].rstrip("/") + ".js"
    r = requests.get(api, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    variants = {
        str(v["id"]): {"name": v["title"], "available": bool(v["available"])}
        for v in data["variants"]
    }
    return data["title"], variants


def notify(title, variant_name, link):
    if not WEBHOOK_URL:
        print("沒有設定 DISCORD_WEBHOOK_URL，略過通知")
        return
    ids = [i.strip() for i in MENTION_USER_ID.split(",") if i.strip()]
    parts = ["@everyone" if i.lower() == "everyone" else f"<@{i}>" for i in ids]
    mention = " ".join(parts) + " " if parts else ""
    content = f"{mention}🔔 **補貨了！**\n{title}（{variant_name}）\n{link}"
    requests.post(WEBHOOK_URL, json={"content": content}, timeout=20).raise_for_status()


def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    for url in PRODUCTS:
        try:
            title, variants = fetch_variants(url)
        except Exception as e:
            print(f"抓取失敗 {url}: {e}")
            continue

        for vid, info in variants.items():
            key = f"{url}#{vid}"
            was_available = state.get(key, False)
            if info["available"] and not was_available:
                notify(title, info["name"], f"{url}?variant={vid}")
                print(f"已通知：{title} / {info['name']}")
            state[key] = info["available"]
            print(f"{title} / {info['name']}: {'有貨' if info['available'] else '缺貨'}")

    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
