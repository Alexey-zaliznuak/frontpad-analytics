#!/bin/bash
# Установка зависимостей для запуска на Ubuntu-сервере

set -e

echo "=== Обновление пакетов ==="
sudo apt update

echo "=== Python 3 и venv ==="
sudo apt install -y python3 python3-venv python3-pip

echo "=== Tesseract OCR (для капчи) ==="
sudo apt install -y tesseract-ocr tesseract-ocr-rus

echo "=== Системные зависимости для Playwright/Chromium ==="
sudo apt install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2

echo "=== Создание venv (если нет) ==="
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "=== Активация venv и установка Python-пакетов ==="
source venv/bin/activate
pip install --upgrade pip
pip install pandas lxml playwright pytesseract requests pillow gspread google-auth python-dotenv

echo "=== Установка браузера Chromium для Playwright ==="
playwright install chromium
playwright install-deps chromium

echo ""
echo "=== Готово! ==="
echo ""
echo "Дальнейшие шаги:"
echo "1. Скопируйте на сервер: .env, service_account.json"
echo "2. В .env задайте SPREADSHEET_ID"
echo "3. Для headless-режима установите: export HEADLESS=true"
echo "4. Запуск: source venv/bin/activate && python main.py"
echo ""
