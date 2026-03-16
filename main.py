import asyncio
import logging
import os
import platform
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

from captcha_solve import solve_captcha_cached
from settings import PROFILES, SPREADSHEET_ID, SERVICE_ACCOUNT_FILE, REPORT_SHEET_NAME

DEBUG = True

# Фиксированный порядок столбцов для гарантии при перезапусках (Frontpad export)
COLUMN_ORDER = [
    "Филиал",
    "Имя",
    "Телефон",
    "Улица",
    "Дом",
    "Подъезд",
    "Этаж",
    "Квартира",
    "Комментарий",
    "Email",
    "Не отправлять SMS",
    "Дисконтная карта",
    "Скидка",
    "Лицевой счет",
    "День рождения",
    "Канал продаж",
    "Создан",
    "Заказы",
    "Сумма",
    "Последний заказ",
]


def setup_logging() -> Path:
    """Настройка логирования в logs/YYYY-MM-DD/log.log"""
    log_dir = Path("logs") / datetime.now().strftime("%Y-%m-%d")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "log.log"

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Очищаем существующие хэндлеры
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return log_dir


async def save_screenshot(page, name: str, screenshots_dir: Path) -> None:
    """Сохраняет скриншот при debug=True"""
    if DEBUG and screenshots_dir:
        path = screenshots_dir / f"{name}.png"
        await page.screenshot(path=str(path))
        logging.info(f"Скриншот сохранён: {path}")


def load_clients_dataframe(downloads_dir: Path) -> pd.DataFrame:
    """
    Собирает все XLS файлы из downloads в один DataFrame.
    Файлы .xls — HTML-таблицы. После объединения удаляет содержимое папки.
    """
    downloads_dir = Path(downloads_dir)
    if not downloads_dir.exists():
        return pd.DataFrame()

    files = list(downloads_dir.glob("*.xls*"))
    # Сортируем по start из имени (clients_1_1000 -> 1, clients_1001_2000 -> 1001)
    def sort_key(p: Path) -> int:
        m = re.search(r"clients_(\d+)_\d+", p.stem)
        return int(m.group(1)) if m else 0

    files = sorted(files, key=sort_key)

    if not files:
        logging.warning("Нет файлов для загрузки в downloads/")
        return pd.DataFrame()

    dfs = []
    for f in files:
        try:
            # .xls от Frontpad — это HTML-таблица (требуется lxml: pip install lxml)
            df = pd.read_html(str(f), encoding="utf-8")[0]
            # Если столбцы числовые (0,1,2...) — первая строка была распознана как данные, используем её как заголовки
            if len(df.columns) > 0 and df.columns[0] == 0:
                df.columns = df.iloc[0].astype(str)
                df = df.iloc[1:].reset_index(drop=True)
            dfs.append(df)
            logging.debug(f"Загружен: {f.name} ({len(df)} строк)")
        except Exception as e:
            logging.exception(f"Ошибка чтения {f}: {e}")

    if not dfs:
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    logging.info(f"Объединён датафрейм: {len(result)} строк из {len(dfs)} файлов")

    # Удаляем содержимое папки downloads
    for f in files:
        try:
            f.unlink()
            logging.debug(f"Удалён: {f.name}")
        except OSError as e:
            logging.warning(f"Не удалось удалить {f}: {e}")

    return result


def add_computed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Добавляет вычисляемые столбцы в датафрейм клиентов.
    Использует колонки: Телефон, Заказы, Сумма, Создан, Последний заказ.
    """
    if df.empty:
        return df

    today = pd.Timestamp.now().normalize()
    # Ключевая колонка для проверки "есть ли клиент" (как $C в Excel)
    key_col = "Телефон" if "Телефон" in df.columns else df.columns[1]

    def safe_date(s):
        """Парсит дату DD.MM.YYYY или возвращает NaT."""
        if pd.isna(s) or s == "" or str(s).strip() == "":
            return pd.NaT
        try:
            return pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
        except Exception:
            return pd.NaT

    # Последний заказ и Создан как даты
    last_order = df["Последний заказ"].apply(safe_date) if "Последний заказ" in df.columns else pd.Series([pd.NaT] * len(df))
    created = df["Создан"].apply(safe_date) if "Создан" in df.columns else pd.Series([pd.NaT] * len(df))
    orders = pd.to_numeric(df["Заказы"], errors="coerce").fillna(0) if "Заказы" in df.columns else pd.Series([0] * len(df))
    summa = pd.to_numeric(df["Сумма"].astype(str).str.replace(",", "."), errors="coerce").fillna(0) if "Сумма" in df.columns else pd.Series([0] * len(df))

    has_client = df[key_col].apply(lambda x: not (pd.isna(x) or str(x).strip() == ""))

    # Активный: заказывал в последние 30 дней (=ЕСЛИ($C=""; ""; ЕСЛИ($U>=СЕГОДНЯ()-30; 1; 0)))
    df["Активный заказывал в посл 30 дней"] = ""
    df.loc[has_client, "Активный заказывал в посл 30 дней"] = (
        (last_order >= (today - pd.Timedelta(days=30))).astype(int)
    )
    df.loc[~has_client, "Активный заказывал в посл 30 дней"] = ""

    # Постоянный: 3+ заказа (=ЕСЛИ($C=""; ""; ЕСЛИ($S>=3; 1; 0)))
    df["Постоянный 3+ заказа"] = ""
    df.loc[has_client, "Постоянный 3+ заказа"] = (orders >= 3).astype(int)
    df.loc[~has_client, "Постоянный 3+ заказа"] = ""

    # Один заказ (=ЕСЛИ($C=""; ""; ЕСЛИ($S=1; 1; 0)))
    df["Один заказ"] = ""
    df.loc[has_client, "Один заказ"] = (orders == 1).astype(int)
    df.loc[~has_client, "Один заказ"] = ""

    # LTV — сумма
    df["LTV"] = summa

    # Дней с последнего (=ЕСЛИ($C=""; ""; ЕСЛИ($U=""; ""; СЕГОДНЯ()-$U)))
    df["Дней с последнего"] = ""
    days_since_last = (today - last_order).dt.days
    valid_last = has_client & last_order.notna()
    df.loc[valid_last, "Дней с последнего"] = days_since_last.loc[valid_last].astype(int)
    df.loc[~valid_last, "Дней с последнего"] = ""

    # Возраст клиента (=ЕСЛИ($C=""; ""; ЕСЛИ($R=""; ""; СЕГОДНЯ()-$R)))
    df["Возраст клиента"] = ""
    client_age = (today - created).dt.days
    valid_created = has_client & created.notna()
    df.loc[valid_created, "Возраст клиента"] = client_age.loc[valid_created].astype(int)
    df.loc[~valid_created, "Возраст клиента"] = ""

    return df


def upload_to_google_sheet(df: pd.DataFrame) -> None:
    """
    Очищает лист Google Таблицы и заливает датафрейм (заголовки + данные).
    """
    if not SPREADSHEET_ID:
        logging.warning("SPREADSHEET_ID не задан, пропуск загрузки в Google Sheets")
        return
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(REPORT_SHEET_NAME)

        # Очищаем лист
        worksheet.clear()
        logging.info(f"Лист «{REPORT_SHEET_NAME}» очищен")

        # Подготавливаем данные: заголовки + строки
        df = df.fillna("")
        headers = df.columns.tolist()
        rows = [[str(v) if pd.notna(v) else "" for v in row] for row in df.values.tolist()]
        values = [headers] + rows

        if values:
            worksheet.update(values, "A1", value_input_option="USER_ENTERED")
            logging.info(f"Залито в Google Sheets: {len(df)} строк")
    except ImportError as e:
        logging.error(f"Установите gspread и google-auth: pip install gspread google-auth. {e}")
    except Exception as e:
        logging.exception(f"Ошибка загрузки в Google Sheets: {e}")


async def run_profile(page, profile: dict, screenshots_dir: Path | None, downloads_dir: Path) -> pd.DataFrame | None:
    """Выполняет полный цикл для одного профиля: логин, экспорт, сбор датафрейма."""
    login = profile["login"]
    password = profile["password"]
    branch_name = profile["branch_name"]

    logging.info(f"Обработка профиля: {branch_name} ({login})")

    try:
        await page.goto("https://app.frontpad.ru/login/")
        await save_screenshot(page, f"01_page_loaded_{branch_name}", screenshots_dir)

        await page.fill("#login", login)
        await page.fill('input[name="password"]', password)

        captcha_input = page.locator('input[name="login_code"]')
        if await captcha_input.count() > 0 and await captcha_input.is_visible():
            logging.info("Обнаружено поле капчи...")
            captcha_img_el = page.locator('img#login_code')
            captcha_url = "https://app.frontpad.ru/login/blocks/code/codegen.php?a9="
            if await captcha_img_el.count() > 0:
                src = await captcha_img_el.get_attribute("src")
                if src:
                    captcha_url = src if src.startswith("http") else f"https://app.frontpad.ru/login/{src}"
            captcha = await asyncio.to_thread(solve_captcha_cached, captcha_url, 3)
            if captcha:
                await captcha_input.fill(captcha)

        await page.locator('span.btn:has-text("Войти")').click()
        await page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
        logging.info("Успешный вход")

        settings_menu = page.locator("li:has(.m_settings)")
        await settings_menu.click()
        await page.wait_for_timeout(500)
        await page.locator("li[onclick*=\"menu('settings','settings')\"]").click()
        await page.wait_for_timeout(1000)

        await page.locator('span.btn.download:has-text("Скачать")').click()
        await page.wait_for_selector("#popup", state="visible", timeout=5000)

        download_links = page.locator('#popup a[href*="clients.php"]')
        links_count = await download_links.count()
        logging.info(f"Частей для скачивания: {links_count}")

        for i in range(links_count):
            link = download_links.nth(i)
            href = await link.get_attribute("href")
            start_stop = ""
            if href and "start=" in href and "stop=" in href:
                match = re.search(r"start=(\d+)&amp;stop=(\d+)", href)
                if not match:
                    match = re.search(r"start=(\d+)&stop=(\d+)", href)
                if match:
                    start_stop = f"{match.group(1)}_{match.group(2)}"
            filename = f"clients_{start_stop or i + 1}"
            async with page.expect_download() as download_info:
                await link.click()
            download = await download_info.value
            ext = Path(download.suggested_filename).suffix if download.suggested_filename else ".xls"
            save_path = downloads_dir / f"{filename}{ext}"
            await download.save_as(str(save_path))
            logging.info(f"Скачан: {save_path.name}")

        await page.locator('#popup span.btn:has-text("Закрыть")').click()

        df = load_clients_dataframe(downloads_dir)
        if df.empty:
            logging.warning(f"Нет данных для {branch_name}")
            return None

        # df = add_computed_columns(df)
        df["Филиал"] = branch_name
        # Фиксированный порядок столбцов
        cols = [c for c in COLUMN_ORDER if c in df.columns]
        cols += [c for c in df.columns if c not in cols]
        df = df[cols]
        logging.info(f"{branch_name}: {len(df)} записей")
        return df

    except Exception as e:
        logging.exception(f"Ошибка профиля {branch_name}: {e}")
        await save_screenshot(page, f"error_{branch_name}", screenshots_dir)
        return None


async def main():
    log_dir = setup_logging()
    screenshots_dir = log_dir / "screenshots" if DEBUG else None
    if screenshots_dir:
        screenshots_dir.mkdir(parents=True, exist_ok=True)

    downloads_dir = Path("downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)

    if not PROFILES:
        logging.error("Нет профилей в settings.PROFILES")
        return

    all_dfs: list[pd.DataFrame] = []

    async with async_playwright() as p:
        # Windows: headed по умолчанию, остальные ОС: headless
        _default = "false" if platform.system() == "Windows" else "true"
        headless = os.getenv("HEADLESS", _default).lower() == "true"
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        try:
            for profile in PROFILES:
                df = await run_profile(page, profile, screenshots_dir, downloads_dir)
                if df is not None:
                    all_dfs.append(df)
                # Выход из аккаунта перед следующим профилем (переход на логин)
                if profile != PROFILES[-1]:
                    await page.goto("https://app.frontpad.ru/login/")
                    await page.wait_for_timeout(1000)
        finally:
            await browser.close()

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        upload_to_google_sheet(combined)


if __name__ == "__main__":
    asyncio.run(main())
