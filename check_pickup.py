import os
import json
import urllib.request
import urllib.error

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

APPLE_URL = "https://www.apple.com/ae/shop/buy-iphone/iphone-duo"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": message
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()

def main():
    request = urllib.request.Request(
        APPLE_URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status

        send_telegram(
            "Монитор iPhone Duo запущен.\n"
            f"Страница Apple UAE ответила с HTTP {status}.\n"
            "Это проверка доступности страницы, а не наличия товара. "
            "Проверка самовывоза ещё настраивается."
        )

    except urllib.error.HTTPError as error:
        send_telegram(
            "Монитор iPhone Duo: Apple вернула HTTP "
            f"{error.code}. Наличие товара не подтверждено."
        )

    except Exception as error:
        send_telegram(
            "Монитор iPhone Duo: не удалось проверить Apple. "
            f"Тип ошибки: {type(error).__name__}. "
            "Наличие товара не подтверждено."
        )

if __name__ == "__main__":
    main()
