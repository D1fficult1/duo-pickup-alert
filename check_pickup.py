import os
import re
import json
import urllib.request
import urllib.parse
import html

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

URL = (
    "https://www.apple.com/ae/shop/buy-iphone/"
    "iphone-duo/7.6-inch-display-256gb-night-sky"
)

def send_telegram(message):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }).encode()
    req = urllib.request.Request(api_url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()

def main():
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.status
            page = response.read().decode("utf-8", errors="replace")

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            page, re.IGNORECASE | re.DOTALL
        )
        title = html.unescape(title_match.group(1)).strip() if title_match else "Не найден"

        # Собираем возможные артикулы из HTML.
        candidates = sorted(set(re.findall(
            r"\b[A-Z0-9]{5,10}AH/A\b", page
        )))

        message = (
            "🔎 Диагностика Apple Duo\n"
            f"HTTP: {status}\n"
            f"Заголовок страницы: {title}\n"
            f"Размер страницы: {len(page)} символов\n"
            f"Найдено возможных артикулов: {len(candidates)}\n"
        )

        if candidates:
            message += "\n".join(candidates[:40])
            message += (
                "\n\n⚠️ Это кандидаты из HTML, "
                "а не подтверждённые артикулы Duo."
            )
        else:
            message += (
                "\nАртикулы в ожидаемом формате не найдены. "
                "Возможно, страница загружается динамически."
            )

        send_telegram(message)

    except Exception as error:
        try:
            send_telegram(
                "❌ Ошибка проверки Apple Duo:\n"
                f"{type(error).__name__}: {error}"
            )
        finally:
            raise

if __name__ == "__main__":
    main()
