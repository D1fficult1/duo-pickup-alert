import re
import urllib.request
URL = "https://www.apple.com/ae/shop/buy-iphone/iphone-duo/7.6-inch-display-256gb-night-sky"
req = urllib.request.Request(
    URL,
    headers={"User-Agent": "Mozilla/5.0"}
)
with urllib.request.urlopen(req, timeout=30) as response:
    html = response.read().decode("utf-8", errors="replace")
patterns = [
    r'"partNumber"\s*:\s*"([^"]+)"',
    r'"productPartNumber"\s*:\s*"([^"]+)"',
    r'"sku"\s*:\s*"([^"]+)"',
]
found = set()
for pattern in patterns:
    found.update(re.findall(pattern, html))
if found:
    print("Найденные возможные артикулы:")
    for item in sorted(found):
        print(item)
else:
    print("Артикулы не найдены в HTML страницы.")
    print("Размер HTML:", len(html))
    print("Фрагмент страницы:", html[:1000])
