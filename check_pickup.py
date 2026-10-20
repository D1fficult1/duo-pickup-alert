import os
import json
import re
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BASE = "https://www.apple.com/ae/shop/buy-iphone/iphone-duo/"
VARIANTS = [
    "7.6-inch-display-256gb-night-sky",
    "7.6-inch-display-256gb-star-white",
    "7.6-inch-display-512gb-night-sky",
    "7.6-inch-display-512gb-star-white",
    "7.6-inch-display-1tb-night-sky",
    "7.6-inch-display-1tb-star-white",
    "7.6-inch-display-2tb-night-sky",
    "7.6-inch-display-2tb-star-white",
]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()

def main():
    report = ["Диагностика Apple UAE — поиск артикулов"]
    for variant in VARIANTS:
        url = BASE + variant
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8", errors="replace")
                status = r.status

            # Ищем возможные поля артикула в HTML страницы.
            found = set()
            for pattern in (
                r'"partNumber"\s*:\s*"([^"]+)"',
                r'"productPartNumber"\s*:\s*"([^"]+)"',
                r'"sku"\s*:\s*"([^"]+)"',
            ):
                found.update(re.findall(pattern, html, re.I))

            report.append(
                f"\n{variant}\nHTTP {status}; "
                f"возможные артикулы: "
                f"{', '.join(sorted(found)[:8]) or 'не найдены'}"
            )
        except Exception as e:
            report.append(f"\n{variant}\nОшибка: {type(e).__name__}")

    report.append(
        "\nЭто диагностика, не проверка наличия. "
        "Пока артикулы не подтверждены."
    )
    send_telegram("\n".join(report))

if __name__ == "__main__":
    main()
