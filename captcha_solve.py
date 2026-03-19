import io
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pytesseract
import requests
from PIL import Image

CAPTCHA_CACHE_FILE = Path("captcha.json")


def _same_30min_period(dt1: datetime, dt2: datetime) -> bool:
    """Проверяет, попадают ли два времени в один 30-минутный период."""
    if dt1.date() != dt2.date():
        return False
    slot1 = (dt1.hour * 60 + dt1.minute) // 30
    slot2 = (dt2.hour * 60 + dt2.minute) // 30
    return slot1 == slot2


def _get_cached_captcha() -> str | None:
    """Возвращает закэшированную капчу, если она ещё актуальна (в рамках текущего 30-мин периода)."""
    if not CAPTCHA_CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CAPTCHA_CACHE_FILE.read_text(encoding="utf-8"))
        solved_at = datetime.fromisoformat(data["solved_at"])
        if _same_30min_period(solved_at, datetime.now()):
            return data["code"]
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


def _save_captcha_cache(code: str) -> None:
    """Сохраняет капчу и время решения в captcha.json."""
    data = {"code": code, "solved_at": datetime.now().isoformat()}
    CAPTCHA_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def solve_captcha_with_counter(image_url, target_count=3):
    """
    Распознавание CAPTCHA с подсчетом отсортированных версий
    """
    counter = defaultdict(int)
    attempts = 0
    max_attempts = 200  # Максимальное количество попыток

    print(f"Начинаю распознавание. Цель: {target_count} совпадения...")

    while attempts < max_attempts:
        attempts += 1

        try:
            # Скачиваем изображение
            response = requests.get(image_url)
            response.raise_for_status()

            # Открываем изображение
            img = Image.open(io.BytesIO(response.content))

            # Настраиваем Tesseract
            custom_config = r'--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'

            # Распознаем текст
            text = pytesseract.image_to_string(img, config=custom_config)
            code = ''.join(c for c in text if c.isalnum()).lower()

            if not code or len(code) < 4:
                continue

            # Сортируем символы
            sorted_code = ''.join(sorted(code))

            # Увеличиваем счетчик
            counter[sorted_code] += 1
            count = counter[sorted_code]

            print(f"Попытка {attempts}: {code:10} → отсортировано: {sorted_code:10} (счетчик: {count})")

            # Проверяем, достигли ли целевого количества
            if count >= target_count:
                print(f"\n✓ Найдено! Код (отсортированный): {sorted_code}")
                print(f"  Оригинал распознавания: {code}")
                print(f"  Всего попыток: {attempts}")
                return sorted_code

        except Exception as e:
            print(f"Ошибка на попытке {attempts}: {e}")
            continue

    print(f"\n✗ Не удалось найти код за {max_attempts} попыток")
    print("\nТоп отсортированных версий:")
    for sorted_ver, count in sorted(counter.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {sorted_ver}: {count}")

    return None


def solve_captcha_cached(image_url, target_count=3) -> str | None:
    """
    Распознавание CAPTCHA с кэшированием.
    Капча одинакова в рамках 30-минутных периодов (00:00-00:29, 00:30-00:59, ...).
    Пересчёт только если получасовой период истёк.
    """
    cached = _get_cached_captcha()
    if cached is not None:
        print(f"Используется закэшированная капча: {cached}")
        return cached
    result = solve_captcha_with_counter(image_url, target_count)
    if result:
        _save_captcha_cache(result)
    return result


# Использование
if __name__ == "__main__":
    image_url = "https://app.frontpad.ru/login/blocks/code/codegen.php?a9="
    result = solve_captcha_cached(image_url, target_count=3)
    
    if result:
        print(f"\nИтоговый ответ: {result}")