import os
import json
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PARTS = [
    "MK244AH/A", "MK254AH/A",
    "MK264AH/A", "MK274AH/A",
    "MK284AH/A", "MK294AH/A",
    "MK2A4AH/A", "MK2C4AH/A",
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
    params = [
        ("pl", "true"),
        ("location", "Dubai"),
    ]
    params += [(f"parts.{i}", p) for i, p in enumerate(PARTS)]

    url = (
        "https://www.apple.com/ae/shop/retail/pickup-message?"
        + urllib.parse.urlencode(params)
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
            body = r.read().decode("utf-8", errors="replace")

        try:
            data = json.loads(body)
            result = json.dumps(
                data, ensure_ascii=False, indent=2
            )
            send_telegram(
                f"Apple Pickup API: HTTP {status}\n"
                + result[:3500]
                + "\n\nДиагностика; наличие пока не подтверждено."
            )
        except json.JSONDecodeError:
            send_telegram(
                f"Apple вернула HTTP {status}, но ответ не JSON.\n"
                + body[:2500]
            )
    except Exception as e:
        send_telegram(
            f"Ошибка запроса Apple Pickup API: {type(e).__name__}: {e}"
        )

if __name__ == "__main__":
    main()
