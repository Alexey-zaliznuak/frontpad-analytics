"""Скрипт для вывода списка листов в Google Таблице."""

import os
from dotenv import load_dotenv

load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SERVICE_ACCOUNT_FILE = "service_account.json"


def main():
    if not SPREADSHEET_ID:
        print("Задайте SPREADSHEET_ID в .env")
        return

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)

    print(f"Таблица: {sh.title}\nЛисты:")
    for i, ws in enumerate(sh.worksheets(), 1):
        print(f"  {i}. {repr(ws.title)} (id={ws.id})")


if __name__ == "__main__":
    main()
