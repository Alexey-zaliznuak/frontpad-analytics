# Развёртывание на Ubuntu-сервере

## Быстрая установка

```bash
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

## Ручная установка

### 1. Системные пакеты

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo apt install -y tesseract-ocr tesseract-ocr-rus
sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2
```

### 2. Python-окружение

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install pandas lxml playwright pytesseract requests pillow gspread google-auth python-dotenv
```

### 3. Playwright (Chromium)

```bash
playwright install chromium
playwright install-deps chromium
```

### 4. Конфигурация

Скопируйте на сервер:
- `service_account.json` — ключ для Google Sheets
- `.env` — переменные окружения

Пример `.env`:
```
SPREADSHEET_ID=ваш_id_таблицы
```

### 5. Headless-режим

На сервере без дисплея нужен headless. В `main.py` замените:
```python
browser = await p.chromium.launch(headless=True)
```
или добавьте поддержку переменной окружения:
```python
headless = os.getenv("HEADLESS", "false").lower() == "true"
browser = await p.chromium.launch(headless=headless)
```

### 6. Запуск

```bash
source venv/bin/activate
python main.py
```

## Cron (ежедневный запуск)

```bash
crontab -e
# Добавить строку (например, в 6:00):
0 6 * * * cd /path/to/anal && /path/to/anal/venv/bin/python main.py >> /path/to/anal/logs/cron.log 2>&1
```
