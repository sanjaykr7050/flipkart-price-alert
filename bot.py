import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


load_dotenv()

CHECK_MINUTES = max(30, int(os.getenv("CHECK_MINUTES", "60")))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true"

STATE_FILE = Path("alert_state.json")
PRODUCTS_FILE = Path("products.json")


def validate_settings():
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise RuntimeError("Missing settings: " + ", ".join(missing))


def load_products():
    if PRODUCTS_FILE.exists():
        products = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    else:
        products = [
            {
                "name": os.getenv("PRODUCT_NAME", "Horlicks Nutrition Drink Jar"),
                "url": os.getenv(
                    "PRODUCT_URL",
                    "https://www.flipkart.com/horlicks-nutrition-drink-jar/p/itmfaa093d013a02?pid=MDMETGMUEHP2YJDZ&marketplace=GROCERY",
                ),
                "target_price": float(os.getenv("TARGET_PRICE", "380")),
                "pin_code": os.getenv("PIN_CODE", "827009"),
            }
        ]

    if not isinstance(products, list) or not products:
        raise RuntimeError("products.json mein kam-se-kam ek product hona chahiye.")

    required = {"name", "url", "target_price", "pin_code"}
    for index, product in enumerate(products, start=1):
        missing = required - set(product)
        if missing:
            raise RuntimeError(
                f"Product {index} mein missing fields: {', '.join(sorted(missing))}"
            )
        product["target_price"] = float(product["target_price"])
        product["pin_code"] = str(product["pin_code"])
    return products


def product_key(product):
    pid = parse_qs(urlparse(product["url"]).query).get("pid", [])
    if pid:
        return pid[0]
    return re.sub(r"[^a-zA-Z0-9]+", "-", product["name"]).strip("-").lower()


def send_telegram(message):
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    response.raise_for_status()


def money_to_float(value):
    if value is None:
        return None
    match = re.search(r"(?:₹|Rs\.?\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)", str(value))
    return float(match.group(1).replace(",", "")) if match else None


def price_from_json_ld(page):
    for raw in page.locator('script[type="application/ld+json"]').all_text_contents():
        try:
            objects = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(objects, list):
            objects = [objects]
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            offers = obj.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                price = money_to_float(offers.get("price") or offers.get("lowPrice"))
                if price:
                    return price
    return None


def set_delivery_pin(page, pin_code):
    selectors = [
        'input[placeholder*="pincode" i]',
        'input[placeholder*="pin code" i]',
        'input[placeholder*="delivery" i]',
    ]
    for selector in selectors:
        field = page.locator(selector).first
        try:
            if field.count() and field.is_visible(timeout=1500):
                field.fill(pin_code)
                field.press("Enter")
                page.wait_for_timeout(3500)
                return True
        except Exception:
            continue
    return False


def read_price(product):
    last_error = None

    for attempt in range(1, 4):
        browser = None
        context = None

        try:
            print(
                f'Checking "{product["name"]}" '
                f"(attempt {attempt}/3)..."
            )

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=HEADLESS,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )

                context = browser.new_context(
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    viewport={"width": 1365, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    extra_http_headers={
                        "Accept-Language": "en-IN,en;q=0.9",
                    },
                )

                page = context.new_page()

                # Give Playwright enough time on GitHub Actions.
                page.set_default_timeout(10000)
                page.set_default_navigation_timeout(45000)

                try:
                    response = page.goto(
                        product["url"],
                        wait_until="commit",
                        timeout=45000,
                    )

                    print(
                        f'Navigation completed for "{product["name"]}" '
                        f"(status={response.status if response else 'unknown'})"
                    )

                except Exception as error:
                    raise RuntimeError(
                        f"Navigation failed: {type(error).__name__}: {error}"
                    )

                # Allow Flipkart's dynamically loaded content to appear.
                page.wait_for_timeout(5000)

                # Detect obvious block/challenge pages.
                page_text = ""
                try:
                    page_text = page.locator("body").inner_text(
                        timeout=5000
                    ).lower()
                except Exception:
                    pass

                blocked_words = [
                    "captcha",
                    "access denied",
                    "request blocked",
                    "unusual traffic",
                    "robot",
                    "verify you are human",
                ]

                if any(word in page_text for word in blocked_words):
                    raise RuntimeError(
                        "Flipkart block/challenge page detected"
                    )

                # Close popup if present.
                for selector in [
                    'button:has-text("✕")',
                    'button[aria-label="Close"]',
                ]:
                    try:
                        button = page.locator(selector).first
                        if button.count() and button.is_visible(timeout=1000):
                            button.click()
                            break
                    except Exception:
                        pass

                # Apply delivery PIN.
                pin_applied = set_delivery_pin(
                    page,
                    product["pin_code"],
                )

                # Give price information a moment to render.
                page.wait_for_timeout(2000)

                price = price_from_json_ld(page)

                # Fallback price selectors.
                if not price:
                    selectors = [
                        '[itemprop="price"]',
                        'meta[property="product:price:amount"]',
                        'div.Nx9bqj.CxhGGd',
                        'div.Nx9bqj',
                        'div._30jeq3',
                    ]

                    for selector in selectors:
                        try:
                            node = page.locator(selector).first

                            if not node.count():
                                continue

                            value = (
                                node.get_attribute("content")
                                or node.text_content()
                            )

                            price = money_to_float(value)

                            if price:
                                break

                        except Exception:
                            continue

                if not price:
                    raise RuntimeError(
                        "Price could not be verified on the page"
                    )

                title = (
                    page.title().split("-")[0].strip()
                    or product["name"]
                )

                # Save screenshot for debugging.
                try:
                    page.screenshot(
                        path=f"last_check_{product_key(product)}.png",
                        full_page=False,
                    )
                except Exception:
                    pass

                print(
                    f'Success: "{product["name"]}" '
                    f"price=₹{price:,.2f}"
                )

                return title, price, pin_applied

        except Exception as error:
            last_error = error

            print(
                f'Attempt {attempt}/3 failed for '
                f'"{product["name"]}": {error}'
            )

            if attempt < 3:
                time.sleep(5)

        finally:
            try:
                if context:
                    context.close()
            except Exception:
                pass

            try:
                if browser:
                    browser.close()
            except Exception:
                pass

    raise RuntimeError(
        f'{product["name"]}: failed after 3 attempts. '
        f"Last error: {last_error}"
    )

def load_state():
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        state = {}
    if not isinstance(state.get("alerts"), dict):
        state["alerts"] = {}
    state.setdefault("last_check_date", None)
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def check_all_products():
    products = load_products()
    state = load_state()
    errors = []
    successful_checks = 0

    for product in products:
        try:
            title, current_price, pin_applied = read_price(product)
            successful_checks += 1
            timestamp = datetime.now().strftime("%d-%m-%Y %I:%M %p")
            print(
                f"[{timestamp}] {title}: ₹{current_price:,.2f} | "
                f'PIN {product["pin_code"]}: {pin_applied}'
            )

            key = product_key(product)
            last_alert_price = state["alerts"].get(key)
            target_price = product["target_price"]

            if current_price <= target_price and current_price != last_alert_price:
                send_telegram(
                    "🔥 Flipkart Price Alert!\n\n"
                    f'{product["name"]}\n'
                    f"Current price: ₹{current_price:,.0f}\n"
                    f"Target price: ₹{target_price:,.0f}\n"
                    f'Delivery PIN: {product["pin_code"]}\n\n'
                    f'Buy now: {product["url"]}'
                )
                state["alerts"][key] = current_price
            elif current_price > target_price and last_alert_price is not None:
                state["alerts"].pop(key, None)

        except Exception as error:
            errors.append(f'{product["name"]}: {error}')
            print("Check failed:", errors[-1])

    state["last_check_date"] = date.today().isoformat()
    save_state(state)

    if errors:
        print(f"Warning: {len(errors)} product(s) skipped; next run mein retry hoga.")
    if successful_checks == 0:
        raise RuntimeError(" | ".join(errors))


def main():
    validate_settings()
    products = load_products()

    if RUN_ONCE:
        check_all_products()
        return

    send_telegram(
        "✅ Flipkart Multi-Product Alert Bot start ho gaya.\n"
        f"Total products: {len(products)}"
    )
    while True:
        try:
            check_all_products()
        except Exception as error:
            print("Check cycle failed:", error)
        time.sleep(CHECK_MINUTES * 60)


if __name__ == "__main__":
    main()
