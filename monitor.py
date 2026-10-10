"""補貨監控：支援 Shopify 與 Weverse Shop，缺貨變有貨時發 Discord 通知。"""
import json
import os
import re
from pathlib import Path

import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# 要 @ 的對象：填使用者 ID（多人用逗號隔開），或填 everyone；留空就不 @
MENTION_USER_ID = os.environ.get("DISCORD_USER_ID", "")
STATE_FILE = Path("state.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# Shopify 商品（網址格式：網站/products/商品名）
SHOPIFY_PRODUCTS = [
    "https://hello82.com/products/signed-tws-tws-2nd-single-album-to-us",
]

# Weverse Shop 商品
WEVERSE_PRODUCTS = [
    "https://shop.weverse.io/zh-tw/shop/USD/artists/255/sales/66914",
]

# 頁面上出現這些字就視為售完
SOLD_OUT_WORDS = ["售罄", "SOLD OUT", "Sold out", "Sold Out"]


def check_shopify(url):
    """Shopify 商品頁網址後面加 .js 會回傳 JSON，裡面有每個版本的 available。"""
    api = url.split("?")[0].rstrip("/") + ".js"
    r = requests.get(api, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    variants = {
        str(v["id"]): {
            "name": v["title"],
            "available": bool(v["available"]),
            "link": f"{url.split('?')[0]}?variant={v['id']}",
        }
        for v in data["variants"]
    }
    return data["title"], variants


def check_weverse(url):
    """抓 Weverse Shop 商品頁，看可見文字裡有沒有「售罄」。"""
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text

    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html)
    if not m:
        m = re.search(r"<title>(.*?)</title>", html, flags=re.S)
    if not m:
        raise ValueError("找不到商品標題，頁面可能被擋或改版")
    title = m.group(1).strip()

    # 先移除 script / style，避免被內嵌的翻譯字串誤判
    visible = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S | re.I)
    sold_out = any(w in visible for w in SOLD_OUT_WORDS)

    return title, {"main": {"name": "Weverse", "available": not sold_out, "link": url}}


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

    jobs = [(check_shopify, u) for u in SHOPIFY_PRODUCTS]
    jobs += [(check_weverse, u) for u in WEVERSE_PRODUCTS]

    for fn, url in jobs:
        try:
            title, variants = fn(url)
        except Exception as e:
            print(f"抓取失敗 {url}: {e}")
            continue

        for vid, info in variants.items():
            key = f"{url}#{vid}"
            was_available = state.get(key, False)
            if info["available"] and not was_available:
                try:
                    notify(title, info["name"], info["link"])
                    print(f"已通知：{title} / {info['name']}")
                except Exception as e:
                    print(f"通知失敗：{e}")
                    continue  # 沒通知成功就不更新狀態，下次再試
            state[key] = info["available"]
            print(f"{title} / {info['name']}: {'有貨' if info['available'] else '缺貨'}")

    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
