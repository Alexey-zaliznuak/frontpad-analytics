#!/bin/bash
# Установка зависимостей для запуска на Ubuntu-сервере

set -e
cd "$(dirname "$0")"

echo "=== Обновление пакетов ==="
sudo apt update

echo "=== Python 3 и venv ==="
sudo apt install -y python3 python3-venv python3-pip

echo "=== Tesseract OCR (для капчи) ==="
sudo apt install -y tesseract-ocr tesseract-ocr-rus

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
echo "=== Установка системных зависимостей для Chromium (требует sudo) ==="
sudo ./venv/bin/playwright install-deps chromium

echo ""
echo "=== Готово! ==="
echo ""
echo "Дальнейшие шаги:"
echo "1. Скопируйте на сервер: .env, service_account.json"
echo "2. В .env задайте SPREADSHEET_ID"
echo "3. Для headless-режима установите: export HEADLESS=true"
echo "4. Запуск: source venv/bin/activate && python main.py"
echo ""
