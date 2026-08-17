import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


load_dotenv()

PRODUCT_URL = os.getenv(
    "PRODUCT_URL",
    "https://www.flipkart.com/horlicks-nutrition-drink-jar/p/itmfaa093d013a02?pid=MDMETGMUEHP2YJDZ&marketplace=GROCERY",
)
PRODUCT_NAME = os.getenv("PRODUCT_NAME", "Horlicks Nutrition Drink Jar")
TARGET_PRICE = float(os.getenv("TARGET_PRICE", "380"))
PIN_CODE = os.getenv("PIN_CODE", "827009")
CHECK_MINUTES = max(30, int(os.getenv("CHECK_MINUTES", "60")))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true"

STATE_FILE = Path("alert_state.json")


def validate_settings():
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise RuntimeError(".env mein ye values bhariye: " + ", ".join(missing))


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


def set_delivery_pin(page):
    selectors = [
        'input[placeholder*="pincode" i]',
        'input[placeholder*="pin code" i]',
        'input[placeholder*="delivery" i]',
    ]
    for selector in selectors:
        field = page.locator(selector).first
        try:
            if field.count() and field.is_visible(timeout=1500):
                field.fill(PIN_CODE)
                field.press("Enter")
                page.wait_for_timeout(3500)
                return True
        except Exception:
            continue
    return False


def read_price():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1365, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # Login popup dikhe to band karne ki koshish.
        for selector in ['button:has-text("✕")', 'button[aria-label="Close"]']:
            try:
                button = page.locator(selector).first
                if button.count() and button.is_visible(timeout=500):
                    button.click()
                    break
            except Exception:
                pass

        pin_applied = set_delivery_pin(page)

        price = price_from_json_ld(page)
        if not price:
            selectors = [
                '[itemprop="price"]',
                'meta[property="product:price:amount"]',
                'div.Nx9bqj.CxhGGd',
                'div.Nx9bqj',
                'div._30jeq3',
            ]
            for selector in selectors:
                node = page.locator(selector).first
                try:
                    if not node.count():
                        continue
                    value = node.get_attribute("content") or node.text_content()
                    price = money_to_float(value)
                    if price:
                        break
                except Exception:
                    continue

        title = page.title().split("-")[0].strip() or PRODUCT_NAME
        screenshot = "last_check.png"
        page.screenshot(path=screenshot, full_page=False)
        browser.close()

    if not price:
        raise RuntimeError(
            "Price page par nahi mili. last_check.png dekhkar HEADLESS=false se test karein."
        )
    return title, price, pin_applied


def load_state():
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(state, dict):
            return state
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"last_alert_price": None, "last_check_date": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def check_once():
    title, current_price, pin_applied = read_price()
    timestamp = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    print(f"[{timestamp}] {title}: ₹{current_price:,.2f} | PIN applied: {pin_applied}")

    state = load_state()
    last_alert_price = state.get("last_alert_price")
    if current_price <= TARGET_PRICE and current_price != last_alert_price:
        send_telegram(
            "🔥 Flipkart Price Alert!\n\n"
            f"{PRODUCT_NAME}\n"
            f"Current price: ₹{current_price:,.0f}\n"
            f"Target price: ₹{TARGET_PRICE:,.0f}\n"
            f"Delivery PIN: {PIN_CODE}\n\n"
            f"Buy now: {PRODUCT_URL}"
        )
        state["last_alert_price"] = current_price
    elif current_price > TARGET_PRICE and last_alert_price is not None:
        state["last_alert_price"] = None

    # Cloud workflow isse din mein ek status commit karta hai. Isse scheduled
    # workflow inactive nahi hota aur duplicate-alert state bhi safe rehti hai.
    state["last_check_date"] = date.today().isoformat()
    save_state(state)


def main():
    validate_settings()
    if RUN_ONCE:
        check_once()
        return

    send_telegram(
        "✅ Flipkart Price Alert Bot start ho gaya.\n"
        f"Product: {PRODUCT_NAME}\n"
        f"Target: ₹{TARGET_PRICE:,.0f}\n"
        f"PIN: {PIN_CODE}"
    )
    while True:
        try:
            check_once()
        except Exception as error:
            print("Check failed:", error)
        time.sleep(CHECK_MINUTES * 60)


if __name__ == "__main__":
    main()
