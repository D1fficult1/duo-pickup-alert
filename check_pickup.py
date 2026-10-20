import os
import json
import urllib.request
import urllib.parse
import subprocess

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PARTS = [
    "MK244AH/A", "MK254AH/A",
    "MK264AH/A", "MK274AH/A",
    "MK284AH/A", "MK294AH/A",
    "MK2A4AH/A", "MK2C4AH/A",
]

# Проверяем основные города ОАЭ.
LOCATIONS = [
    "Dubai", "Abu Dhabi", "Sharjah", "Al Ain",
    "Ajman", "Ras Al Khaimah", "Fujairah"
]

STATE_FILE = "availability_state.json"

def telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()

def get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def persist_state():
    subprocess.run(["git", "config", "user.name", "Duo Pickup Bot"], check=True)
    subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
    subprocess.run(["git", "add", STATE_FILE], check=True)
    changed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"]
    ).returncode != 0
    if changed:
        subprocess.run(
            ["git", "commit", "-m", "Update pickup availability state"],
            check=True
        )
        subprocess.run(["git", "push"], check=True)

def main():
    old_state = set(load_state())
    now_available = set()
    product_names = {}

    for location in LOCATIONS:
        params = [("pl", "true"), ("location", location)]
        params += [
            (f"parts.{i}", part)
            for i, part in enumerate(PARTS)
        ]
        url = (
            "https://www.apple.com/ae/shop/retail/pickup-message?"
            + urllib.parse.urlencode(params)
        )

        try:
            data = get_json(url)
        except Exception as e:
            print(f"Ошибка для {location}: {e}")
            continue

        stores = data.get("body", {}).get("stores", [])
        for store in stores:
            store_name = store.get("storeName", "Apple Store")
            city = store.get("city", location)
            availability = store.get("partsAvailability", {})

            for part, info in availability.items():
                display = str(info.get("pickupDisplay", "")).lower()
                quote = str(info.get("pickupSearchQuote", "")).lower()
                eligible = info.get("storePickEligible") is True

                # Не считаем доступным, если Apple явно пишет unavailable.
                available = (
                    eligible
                    and display not in ("", "unavailable")
                    and "currently unavailable" not in quote
                )

                if available:
                    key = f"{store.get('storeNumber', store_name)}|{part}"
                    now_available.add(key)
                    regular = info.get("messageTypes", {}).get("regular", {})
                    product_names[key] = (
                        regular.get("storePickupProductTitle", part)
                    )
                    product_names[key] += f" — {store_name}, {city}"

    newly_available = now_available - old_state

    if newly_available:
        lines = ["🎉 Apple Duo: появился самовывоз!\n"]
        for key in sorted(newly_available):
            lines.append("• " + product_names.get(key, key))
        lines.append("\nПроверь наличие на сайте Apple UAE.")
        telegram("\n".join(lines))
    else:
        print("Новых доступных вариантов не найдено.")

    save_state(sorted(now_available))
    persist_state()

if __name__ == "__main__":
    main()
