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


def telegram(message, chat_id=None):
    target_chat = CHAT_ID if chat_id is None else str(chat_id)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": target_chat,
        "text": message[:4000],
    }).encode()

    try:
        api_json(url, data)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as file:
            data = json.load(file)

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
    """Сохраняет состояние в GitHub."""
    try:
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
            subprocess.run(
                ["git", "diff", "--cached", "--quiet"]
            ).returncode != 0
        )

        if not changed:
            print("No state changes to commit.")
            return

        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Update pickup monitor state [skip ci]",
            ],
            check=True,
        )

        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            check=True,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            check=True,
            capture_output=True,
            text=True,
        )

        print("Git state saved successfully.")

    except subprocess.CalledProcessError as e:
        print(f"Git persist failed: {e}")

        if e.stdout:
            print(f"stdout: {e.stdout}")

        if e.stderr:
            print(f"stderr: {e.stderr}")

        raise


def get_manual_requests(offset):
    try:
        params = {
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        }

        if offset > 0:
            params["offset"] = offset + 1

        url = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?"
            + urllib.parse.urlencode(params)
        )

        result = api_json(url)
        updates = result.get("result", [])

        manual_chats = set()
        latest_offset = offset

        for update in updates:
            update_id = update.get("update_id", 0)
            latest_offset = max(latest_offset, update_id)

            message = update.get("message", {})
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type", "")
            text = str(message.get("text", "")).strip()

            command = (
                text.split()[0].split("@")[0].lower()
                if text else ""
            )

            if chat_type == "private" and command == "/start":
                if chat_id is not None:
                    manual_chats.add(str(chat_id))

        print(f"Telegram updates received: {len(updates)}")
        print(f"Manual /start requests: {len(manual_chats)}")

        return manual_chats, latest_offset

    except Exception as e:
        print(f"Error fetching telegram updates: {e}")
        return set(), offset


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

                    # Диагностика ответа Apple.
                    print(
                        f"APPLE DEBUG | store={store_name} | "
                        f"city={city} | "
                        f"part={part} | "
                        f"pickupDisplay={info.get('pickupDisplay')!r} | "
                        f"pickupSearchQuote={info.get('pickupSearchQuote')!r} | "
                        f"storePickEligible={info.get('storePickEligible')!r}"
                    )

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
            errors.append(f"{location}: {error}")

    if not stores_found:
        raise RuntimeError(
            "Apple API did not return any stores."
        )

    # Не сохраняем неполные результаты проверки.
    if errors:
        raise RuntimeError(
            "Apple API errors: " + "; ".join(errors)
        )

    return available_now, product_names, len(stores_found)


def availability_message(available_now, product_names):
    if available_now:
        lines = [
            "🔎 Результат проверки Apple Duo:",
            "",
        ]

        for key in sorted(available_now):
            lines.append(
                "• " + product_names.get(key, key)
            )

        lines.extend([
            "",
            "Проверь наличие и оформи Pickup на Apple UAE:",
            "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
        ])

    else:
        lines = [
            "🔎 Проверка Apple Duo завершена.",
            "Сейчас доступных вариантов самовывоза "
            "среди проверенных конфигураций не найдено.",
            "",
            "Apple UAE:",
            "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
        ]

    return "\n".join(lines)


def main():
    old_state = load_state()
    old_offset = load_offset()

    manual_chats, latest_offset = get_manual_requests(old_offset)

    save_offset(latest_offset)
    persist_files()

    for chat_id in sorted(manual_chats):
        telegram(
            "⏳ Команда получена. Проверяю наличие Apple Duo...",
            chat_id=chat_id,
        )

    try:
        available_now, product_names, store_count = check_pickup()
    except Exception as error:
        print(f"Skipping check due to API error: {error}")
        return

    newly_available = available_now - old_state

    # Пока оставляем исходную логику уведомлений без изменений.
    if newly_available:
        lines = [
            "🎉 Apple Duo: появился самовывоз!",
            "",
        ]

        for key in sorted(newly_available):
            lines.append(
                "• " + product_names.get(key, key)
            )

        lines.extend([
            "",
            "Проверь наличие и оформи Pickup на Apple UAE:",
            "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
        ])

        telegram("\n".join(lines))

    # Отправляем результат проверки только по команде /start.
    for chat_id in sorted(manual_chats):
        telegram(
            availability_message(available_now, product_names),
            chat_id=chat_id,
        )

    print("Pickup check completed.")
    print(f"Stores found: {store_count}")
    print(f"Available variants: {len(available_now)}")
    print(f"Newly available variants: {len(newly_available)}")

    save_state(available_now)
    save_offset(latest_offset)
    persist_files()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"CRITICAL ERROR: {type(error).__name__}: {error}"
        )
        raise
