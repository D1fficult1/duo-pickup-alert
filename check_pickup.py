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

    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()


def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(
            response.read().decode("utf-8", errors="replace")
        )


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as file:
            return set(json.load(file))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(state), file, ensure_ascii=False, indent=2)


def persist_state():
    subprocess.run(
        ["git", "config", "user.name", "Duo Pickup Bot"],
        check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "actions@github.com"],
        check=True
    )
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
    old_state = load_state()
    available_now = set()
    product_names = {}
    stores_checked = 0
    errors = []

    try:
        for location in LOCATIONS:
            params = [
                ("pl", "true"),
                ("location", location)
            ]

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
                stores = data.get("body", {}).get("stores", [])
                stores_checked += len(stores)

                for store in stores:
                    store_name = store.get("storeName", "Apple Store")
                    city = store.get("city", location)
                    store_number = store.get("storeNumber", store_name)

                    availability = store.get("partsAvailability", {})

                    for part, info in availability.items():
                        display = str(
                            info.get("pickupDisplay", "")
                        ).lower()

                        quote = str(
                            info.get("pickupSearchQuote", "")
                        ).lower()

                        eligible = (
                            info.get("storePickEligible") is True
                        )

                        is_available = (
                            eligible
                            and display not in ("", "unavailable")
                            and "currently unavailable" not in quote
                        )

                        if is_available:
                            key = f"{store_number}|{part}"
                            available_now.add(key)

                            regular = (
                                info.get("messageTypes", {})
                                .get("regular", {})
                            )

                            title = regular.get(
                                "storePickupProductTitle", part
                            )

                            product_names[key] = (
                                f"{title} — {store_name}, {city}"
                            )

            except Exception as error:
                errors.append(
                    f"{location}: {type(error).__name__}: {error}"
                )

        # Если ни один город не удалось проверить, не стираем историю.
        if stores_checked == 0 and errors:
            raise RuntimeError("; ".join(errors[:3]))

        newly_available = available_now - old_state

        if newly_available:
            lines = [
                "🎉 Apple Duo: появился самовывоз!",
                ""
            ]

            for key in sorted(newly_available):
                lines.append(
                    "• " + product_names.get(key, key)
                )

            lines += [
                "",
                "Проверь наличие и оформи Pickup на Apple UAE:",
                "https://www.apple.com/ae/shop/buy-iphone/iphone-duo"
            ]

            telegram("\n".join(lines))

        elif os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
            telegram(
                "✅ Duo Pickup Bot запущен.\n"
                f"Проверено магазинов в ответах API: {stores_checked}.\n"
                "Новых доступных вариантов не обнаружено."
            )

        if errors:
            print("Ошибки проверки:")
            for error in errors:
                print(error)

        # Сохраняем текущее состояние после успешной проверки.
        save_state(available_now)
        persist_state()

    except Exception as error:
        message = (
            "❌ Ошибка Duo Pickup Bot:\n"
            f"{type(error).__name__}: {error}"
        )

        try:
            telegram(message)
        finally:
            raise


if __name__ == "__main__":
    main()
