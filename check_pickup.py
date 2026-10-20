import json
import os
import subprocess
import urllib.parse
import urllib.request

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PARTS = [
    "MK244AH/A",
    "MK254AH/A",
    "MK264AH/A",
    "MK274AH/A",
    "MK284AH/A",
    "MK294AH/A",
    "MK2A4AH/A",
    "MK2C4AH/A",
]

LOCATIONS = [
    "Dubai",
    "Abu Dhabi",
    "Sharjah",
    "Al Ain",
    "Ajman",
    "Ras Al Khaimah",
    "Fujairah",
]

STATE_FILE = "availability_state.json"
OFFSET_FILE = "telegram_update_offset.txt"


def api_json(url, data=None):
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(
            response.read().decode("utf-8", errors="replace")
        )

    if isinstance(result, dict) and result.get("ok") is False:
        raise RuntimeError(result.get("description", "API error"))

    return result


def telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message[:4000],
    }).encode()

    api_json(url, data)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as file:
            data = json.load(file)

        # Совместимость со старым файлом,
        # в котором хранился обычный список вариантов.
        if isinstance(data, list):
            return set(data)

        if isinstance(data, dict):
            return set(data.get("available", []))

    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return set()


def load_offset():
    try:
        with open(OFFSET_FILE, encoding="utf-8") as file:
            return int(file.read().strip() or "0")
    except (FileNotFoundError, ValueError):
        return 0


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(state), file, ensure_ascii=False, indent=2)


def save_offset(offset):
    with open(OFFSET_FILE, "w", encoding="utf-8") as file:
        file.write(str(offset))


def persist_files():
    subprocess.run(
        ["git", "config", "user.name", "Duo Pickup Bot"],
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "actions@github.com"],
        check=True,
    )

    subprocess.run(
        ["git", "add", STATE_FILE, OFFSET_FILE],
        check=True,
    )

    changed = (
        subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode
        != 0
    )

    if changed:
        subprocess.run(
            ["git", "commit", "-m", "Update pickup monitor state"],
            check=True,
        )
        subprocess.run(["git", "push"], check=True)


def get_manual_requests(offset):
    url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?"
        + urllib.parse.urlencode({
            "offset": offset + 1,
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        })
    )

    result = api_json(url)
    updates = result.get("result", [])

    manual_requested = False
    latest_offset = offset

    for update in updates:
        latest_offset = max(latest_offset, update.get("update_id", 0))

        message = update.get("message", {})
        chat = message.get("chat", {})
        text = str(message.get("text", "")).strip()

        if str(chat.get("id", "")) != str(CHAT_ID):
            continue

        command = text.split()[0].split("@")[0] if text else ""

        if command == "/start":
            manual_requested = True

    return manual_requested, latest_offset


def check_pickup():
    available_now = set()
    product_names = {}
    stores_found = set()
    errors = []

    for location in LOCATIONS:
        params = [
            ("pl", "true"),
            ("location", location),
        ]

        params.extend(
            (f"parts.{index}", part)
            for index, part in enumerate(PARTS)
        )

        url = (
            "https://www.apple.com/ae/shop/retail/pickup-message?"
            + urllib.parse.urlencode(params)
        )

        try:
            data = api_json(url)
            stores = data.get("body", {}).get("stores", [])

            if not stores:
                errors.append(f"{location}: Apple API returned no stores")
                continue

            for store in stores:
                store_name = store.get("storeName", "Apple Store")
                city = store.get("city", location)
                store_number = store.get("storeNumber", store_name)
                stores_found.add(str(store_number))

                availability = store.get("partsAvailability", {})

                for part, info in availability.items():
                    display = str(
                        info.get("pickupDisplay", "")
                    ).strip().lower()

                    quote = str(
                        info.get("pickupSearchQuote", "")
                    ).strip().lower()

                    eligible = info.get("storePickEligible") is True

                    is_available = (
                        eligible
                        and display not in ("", "unavailable", "none")
                        and "currently unavailable" not in quote
                    )

                    if not is_available:
                        continue

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

    if not stores_found:
        raise RuntimeError(
            "Apple API did not return any stores. "
            + "; ".join(errors[:3])
        )

    # Не сравниваем и не сохраняем неполный результат:
    # временная ошибка API не должна сбросить историю наличия.
    if errors:
        raise RuntimeError(
            "Some location checks failed; state was not updated. "
            + "; ".join(errors[:4])
        )

    return available_now, product_names, len(stores_found)


def main():
    old_state = load_state()
    old_offset = load_offset()

    manual_requested, latest_offset = get_manual_requests(old_offset)

    available_now, product_names, store_count = check_pickup()

    newly_available = available_now - old_state

    if newly_available:
        lines = [
            "🎉 Apple Duo: появился самовывоз!",
            "",
    ]

        for key in sorted(newly_available):
            lines.append("• " + product_names.get(key, key))

        lines.extend([
            "",
            "Проверь наличие и оформи Pickup на Apple UAE:",
            "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
        ])

        telegram("\n".join(lines))

    if manual_requested:
        if available_now:
            lines = [
                "🔎 Результат ручной проверки Apple Duo:",
                "",
            ]

            for key in sorted(available_now):
                lines.append("• " + product_names.get(key, key))

            lines.extend([
                "",
                "Ссылка на Apple UAE:",
                "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
            ])
        else:
            lines = [
                "🔎 Проверка завершена.",
                "Сейчас доступных вариантов для самовывоза "
                "среди проверенных конфигураций не найдено.",
                "",
                "Apple UAE:",
                "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
            ]

        telegram("\n".join(lines))

    elif os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        telegram(
            "✅ Проверка Duo Pickup Bot завершена.\n"
            f"Магазинов в результатах Apple API: {store_count}.\n"
            f"Доступных вариантов: {len(available_now)}."
        )

    save_state(available_now)
    save_offset(latest_offset)
    persist_files()

    print(f"Stores found: {store_count}")
    print(f"Available variants: {len(available_now)}")
    print(f"Newly available variants: {len(newly_available)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        try:
            telegram(
                "❌ Ошибка Duo Pickup Bot:\n"
                f"{type(error).__name__}: {error}"
            )
        finally:
            raise
