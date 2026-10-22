import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import date, datetime

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
DATE_LIMIT = date(2027, 12, 31)

STORAGE_ORDER = {
    "256GB": 0,
    "512GB": 1,
    "1TB": 2,
    "2TB": 3,
}

COLOR_ORDER = {
    "Star White": 0,
    "Night Sky": 1,
}


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
    """Сохраняет состояние проверки в GitHub."""
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


def has_check_back_date(quote):
    """
    Исключает известные сообщения Apple о необходимости
    проверить наличие позже, если дата не позднее 31.12.2027.
    """
    quote = quote.strip().lower()

    if "check back for availability on" not in quote:
        return False

    match = re.search(
        r"check back for availability on\s+"
        r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?",
        quote,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = (
            int(match.group(3))
            if match.group(3)
            else datetime.now().year
        )

        try:
            return date(year, month, day) <= DATE_LIMIT
        except ValueError:
            # Неизвестную дату считаем неопределённой.
            return True

    date_text = quote.split(
        "check back for availability on", 1
    )[1].strip()

    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d",
        "%b %d",
        "%d %B",
        "%d %b",
    ):
        try:
            parsed = datetime.strptime(date_text, fmt).date()

            if "%Y" not in fmt:
                parsed = parsed.replace(
                    year=datetime.now().year
                )

            return parsed <= DATE_LIMIT

        except ValueError:
            continue

    # Если Apple изменит формат даты, не объявляем наличие
    # на основании непонятного сообщения.
    return True


def is_pickup_available(info):
    display = str(
        info.get("pickupDisplay", "")
    ).strip().lower()

    quote = str(
        info.get("pickupSearchQuote", "")
    ).strip().lower()

    eligible = info.get("storePickEligible") is True

    if not eligible:
        return False

    if display in ("", "default", "unavailable", "none"):
        return False

    if "currently unavailable" in quote:
        return False

    if "check back for availability on" in quote:
        if has_check_back_date(quote):
            return False

    if "unavailable" in quote:
        return False

    return True


def check_pickup():
    available_now = set()
    product_details = {}
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
                store_number = str(
                    store.get("storeNumber", store_name)
                )

                stores_found.add(store_number)

                availability = store.get("partsAvailability", {})

                for part, info in availability.items():
                    display = str(
                        info.get("pickupDisplay", "")
                    ).strip().lower()

                    quote = str(
                        info.get("pickupSearchQuote", "")
                    ).strip().lower()

                    eligible = (
                        info.get("storePickEligible") is True
                    )

                    print(
                        f"APPLE DEBUG | store={store_name} | "
                        f"city={city} | part={part} | "
                        f"pickupDisplay={info.get('pickupDisplay')!r} | "
                        f"pickupSearchQuote={info.get('pickupSearchQuote')!r} | "
                        f"storePickEligible={info.get('storePickEligible')!r}"
                    )

                    if not is_pickup_available(info):
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

                    product_details[key] = {
                        "title": title,
                        "store_number": store_number,
                        "store_name": store_name,
                        "city": city,
                    }

        except Exception as error:
            errors.append(f"{location}: {error}")

    if not stores_found:
        raise RuntimeError(
            "Apple API did not return any stores."
        )

    # Не обновляем состояние при неполной проверке.
    if errors:
        raise RuntimeError(
            "Apple API errors: " + "; ".join(errors)
        )

    return available_now, product_details, len(stores_found)


def product_sort_key(title):
    """Сортирует по памяти, затем по цвету."""
    normalized = title.upper().replace(" ", "")

    storage = next(
        (
            value for value in STORAGE_ORDER
            if value in normalized
        ),
        None,
    )

    color = next(
        (
            value for value in COLOR_ORDER
            if value.lower() in title.lower()
        ),
        None,
    )

    return (
        STORAGE_ORDER.get(storage, 99),
        COLOR_ORDER.get(color, 99),
        title.lower(),
    )


def group_by_store(keys, product_details):
    """Группирует выбранные варианты по магазинам."""
    groups = {}

    for key in keys:
        details = product_details.get(key)

        if not details:
            continue

        store_number = details["store_number"]

        if store_number not in groups:
            groups[store_number] = {
                "store_name": details["store_name"],
                "city": details["city"],
                "products": [],
            }

        groups[store_number]["products"].append(
            details["title"]
        )

    return groups


def store_sort_key(item):
    store = item[1]
    return (
        store["store_name"].lower(),
        store["city"].lower(),
    )


def build_store_message(store, heading):
    lines = [
        heading,
        "",
        f"📍 {store['store_name']} · {store['city']}",
        "",
    ]

    products = sorted(
        set(store["products"]),
        key=product_sort_key,
    )

    current_storage = None

    for title in products:
        normalized = title.upper().replace(" ", "")

        storage = next(
            (
                value for value in STORAGE_ORDER
                if value in normalized
            ),
            None,
        )

        color = next(
            (
                value for value in COLOR_ORDER
                if value.lower() in title.lower()
            ),
            None,
        )

        if storage != current_storage:
            if current_storage is not None:
                lines.append("")

            lines.append(f"{storage or 'Other'}")
            current_storage = storage

        # Показываем только цвет под заголовком памяти.
        if color:
            lines.append(f"• {color}")
        else:
            lines.append(f"• {title}")

    lines.extend([
        "",
        "Проверить наличие и оформить Pickup:",
        "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
    ])

    return "\n".join(lines)


def send_grouped_messages(keys, product_details, heading):
    """Отправляет по одному сообщению на каждый магазин."""
    groups = group_by_store(keys, product_details)

    for _, store in sorted(
        groups.items(),
        key=lambda item: store_sort_key(item),
    ):
        telegram(build_store_message(store, heading))


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
        available_now, product_details, store_count = check_pickup()
    except Exception as error:
        print(f"Skipping check due to API error: {error}")
        return

    newly_available = available_now - old_state

    # Уведомляем только о новых поступлениях.
    # Отдельное компактное сообщение для каждого магазина.
    if newly_available:
        send_grouped_messages(
            newly_available,
            product_details,
            "🎉 Apple Duo — появился самовывоз!",
        )

    # /start показывает всё текущее наличие,
    # сгруппированное по магазинам.
    for chat_id in sorted(manual_chats):
        groups = group_by_store(
            available_now,
            product_details,
        )

        if not groups:
            telegram(
                "🔎 Проверка Apple Duo завершена.\n\n"
                "Сейчас доступных вариантов самовывоза "
                "среди проверенных конфигураций не найдено.\n\n"
                "Apple UAE:\n"
                "https://www.apple.com/ae/shop/buy-iphone/iphone-duo",
                chat_id=chat_id,
            )
            continue

        for _, store in sorted(
            groups.items(),
            key=lambda item: store_sort_key(item),
        ):
            telegram(
                build_store_message(
                    store,
                    "🔎 Результат проверки Apple Duo:",
                ),
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
