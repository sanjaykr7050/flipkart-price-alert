# Flipkart Horlicks Price Alert Bot

Yeh bot Flipkart Affiliate account ke bina product page check karta hai aur price **₹380 ya kam** hone par Telegram message bhejta hai.

Configured details:

- Product: Horlicks Nutrition Drink Jar
- Product ID: `MDMETGMUEHP2YJDZ`
- Target price: ₹380
- Delivery PIN: 827009
- Check interval: 60 minutes

## 1. Python install karein

https://www.python.org/downloads/ se Python install karein. Installation ke waqt **Add Python to PATH** tick karein.

## 2. Bot install karein

ZIP extract karein aur folder mein `install.bat` double-click karein. Chromium download hone mein kuch samay lag sakta hai.

## 3. Telegram token aur Chat ID dalein

Installation ke baad `.env` file Notepad mein kholein:

```env
TELEGRAM_BOT_TOKEN=BOTFATHER_SE_MILA_TOKEN
TELEGRAM_CHAT_ID=APNA_CHAT_ID
```

Telegram BotFather mein `/newbot` se token milta hai. Bot ko `/start` bhejne ke baad browser mein ye kholein:

```text
https://api.telegram.org/botAPNA_TOKEN/getUpdates
```

Response ke `chat` section mein jo `id` hai, wahi Chat ID hai. Token ko kisi ke saath share na karein.

## 4. Pehle test karein

Folder ke address bar mein `cmd` likhkar Enter karein, phir:

```bat
python test_once.py
```

Successful test mein current price terminal par dikhegi. `last_check.png` mein bot ka dekha hua Flipkart page save hoga.

## 5. Bot chalayein

`run_bot.bat` double-click karein. Command window khuli rehni chahiye. Computer sleep ya shutdown hua to checking ruk jayegi.

## Computer band hone par bhi alert: GitHub Cloud Setup

Is folder mein `.github/workflows/price-alert.yml` ready hai. GitHub Actions bot ko har ghante cloud mein chalata hai.

### 1. GitHub repository banayein

1. https://github.com par login karein.
2. Upar `+` par click karke **New repository** chunein.
3. Repository name `flipkart-price-alert` rakhein.
4. **Public** select karein aur **Create repository** dabayein.

Public repository mein sirf code jayega. Telegram token aur Chat ID code mein upload nahi karne hain.

### 2. Bot files upload karein

1. Repository page par **uploading an existing file** link ya **Add file → Upload files** chunein.
2. Extracted `flipkart_price_alert_bot` folder ke andar ki sab files aur folders upload karein.
3. `.env` file upload **mat** karein.
4. **Commit changes** dabayein.

Dhyan rahe: hidden `.github` folder bhi upload hona chahiye. Agar Windows upload mein hidden folder miss ho, `.github/workflows/price-alert.yml` GitHub website par manually create karein.

### 3. Telegram Secrets add karein

Repository mein:

1. **Settings → Secrets and variables → Actions** kholein.
2. **New repository secret** dabayein.
3. Name `TELEGRAM_BOT_TOKEN` aur value mein BotFather token dalein.
4. Doosra secret banayein: name `TELEGRAM_CHAT_ID` aur value mein Chat ID dalein.

### 4. Workflow permission enable karein

1. **Settings → Actions → General** kholein.
2. Neeche **Workflow permissions** mein **Read and write permissions** select karein.
3. **Save** dabayein.

### 5. Cloud test karein

1. Repository ke **Actions** tab mein jaiye.
2. Left mein **Flipkart price alert** chunein.
3. **Run workflow → Run workflow** dabayein.
4. Green tick aane par setup successful hai.

Ab computer shutdown hone par bhi GitHub har ghante check karega. GitHub schedule kabhi-kabhi kuch minute late chal sakta hai. Agar Flipkart cloud request block kare to Actions run mein error dikhega; local bot phir bhi kaam karega.

## Agar price detect na ho

`.env` mein temporary ye change karein:

```env
HEADLESS=false
```

Phir `python test_once.py` chalayein. Browser khulega, jisse delivery PIN ya Flipkart block screen verify kar sakte hain. Flipkart page layout badalne par selectors update karne pad sakte hain.

## Zaroori note

- Personal-use bot ko 30 minute se kam interval par na chalayein.
- Displayed price bank offer, exchange offer ya coupon ke baad wali effective price se alag ho sakti hai.
- Flipkart Grocery availability location aur account ke hisaab se badal sakti hai.
