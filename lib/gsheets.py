import os

import gspread
from gspread.utils import rowcol_to_a1

from lib.retry import retry


def _get_credentials_path():
    return os.environ.get(
        "GSPREAD_SERVICE_ACCOUNT",
        os.path.expanduser("~/.gapi/google_api_secret.json"),
    )


def _get_client():
    credentials_path = _get_credentials_path()
    if credentials_path and os.path.exists(credentials_path):
        return gspread.service_account(filename=credentials_path)
    return gspread.service_account()


@retry(gspread.exceptions.APIError)
def open_spreadsheet(spreadsheet_name):
    client = _get_client()
    return client.open(spreadsheet_name)


@retry(gspread.exceptions.APIError)
def get_worksheet(spreadsheet_name, worksheet_name, spreadsheet=None):
    if spreadsheet is None:
        spreadsheet = open_spreadsheet(spreadsheet_name)
    return spreadsheet.worksheet(worksheet_name)


class GoogleSheet:
    def __init__(self, spreadsheet_name, worksheet_name, spreadsheet=None):
        self.sheet = get_worksheet(
            spreadsheet_name, worksheet_name, spreadsheet=spreadsheet
        )

    @retry(gspread.exceptions.APIError)
    def update_cell(self, row, col, value):
        self.sheet.update_cell(row, col, value)

    @retry(gspread.exceptions.APIError)
    def insert_row(self, values, row_index=2, value_input_option="USER_ENTERED"):
        self.sheet.insert_row(values, row_index, value_input_option=value_input_option)

    @retry(gspread.exceptions.APIError)
    def append_rows(self, rows, value_input_option="USER_ENTERED"):
        if rows:
            self.sheet.append_rows(rows, value_input_option=value_input_option)

    @retry(gspread.exceptions.APIError)
    def batch_update_cells(self, updates, value_input_option="USER_ENTERED"):
        if not updates:
            return
        data = [
            {"range": rowcol_to_a1(row, col), "values": [[value]]}
            for row, col, value in updates
        ]
        self.sheet.batch_update(data, value_input_option=value_input_option)

    @retry(gspread.exceptions.APIError)
    def batch_update_rows(self, start_row, data, start_col=1):
        if not data:
            return
        num_cols = len(data[0]) if data else 0
        if num_cols == 0:
            return

        start_col_letter = _col_num_to_letter(start_col)
        end_col_letter = _col_num_to_letter(start_col + num_cols - 1)
        end_row = start_row + len(data) - 1
        range_name = f"{start_col_letter}{start_row}:{end_col_letter}{end_row}"
        self.sheet.update(range_name, data, value_input_option="USER_ENTERED")

    @retry(gspread.exceptions.APIError)
    def clean_rows(self, column, initial_row, end_row, offsets=None):
        # Clear through end_row so rows with incomplete data (e.g. empty column A) are also cleared
        if end_row < initial_row:
            return
        if offsets is None:
            offsets = [0, 1, 6, 7, 8, 9]
        ranges = []
        for offset in offsets:
            col_letter = _col_num_to_letter(column + offset)
            ranges.append(f"{col_letter}{initial_row}:{col_letter}{end_row}")
        self.sheet.batch_clear(ranges)

    def get_cell_value(self, row, col):
        return self.sheet.cell(row, col).value

    def get_range_value(self, a1_range):
        return self.sheet.get(a1_range)


def _col_num_to_letter(num):
    result = ""
    while num > 0:
        num -= 1
        result = chr(65 + (num % 26)) + result
        num //= 26
    return result
