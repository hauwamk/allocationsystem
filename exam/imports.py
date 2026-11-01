"""Shared CSV/Excel parsing and template generation for bulk imports."""

import csv
import datetime as dt
import logging
import re
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xlsm")
ROW_NUMBER_KEY = "__row_number"

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

HEADER_FILL = PatternFill("solid", fgColor="0B3B6F")
HEADER_FONT = Font(color="FFFFFF", bold=True)
HEADER_ALIGNMENT = Alignment(vertical="center")


class ImportFileError(ValueError):
    """Raised when an uploaded import file cannot be read."""


@dataclass(frozen=True)
class TabularData:
    headers: list[str]
    rows: list[dict[str, str]]


def normalize_header(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def normalize_cell(value):
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        if value.time() == dt.time.min:
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        timespec = "seconds" if value.second or value.microsecond else "minutes"
        return value.isoformat(timespec=timespec)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def get_field(row, *possible_names):
    for name in possible_names:
        value = row.get(normalize_header(name), "")
        if value not in (None, ""):
            return str(value).strip()
    return ""


def validate_tabular_upload(upload):
    suffix = Path(getattr(upload, "name", "") or "").suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return
    if suffix == ".xls":
        raise ValidationError(
            "Legacy .xls files are not supported. Save the file as .xlsx or CSV and try again."
        )
    raise ValidationError("Upload a CSV (.csv) or Excel (.xlsx) file.")


def tabular_upload_field(label="Select a CSV or Excel file"):
    return forms.FileField(
        label=label,
        validators=[validate_tabular_upload],
        help_text="Accepted formats: .csv, .xlsx",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx,.xlsm"}),
    )


def read_tabular_upload(upload):
    suffix = Path(getattr(upload, "name", "") or "").suffix.lower()
    if suffix == ".csv":
        return _read_csv(upload)
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(upload)
    if suffix == ".xls":
        raise ImportFileError(
            "Legacy .xls files are not supported. Save the file as .xlsx or CSV and try again."
        )
    raise ImportFileError("Upload a CSV (.csv) or Excel (.xlsx) file.")


def _rewind(upload):
    try:
        upload.seek(0)
    except (AttributeError, OSError):
        pass


def _read_csv(upload):
    _rewind(upload)
    raw = upload.read()
    if isinstance(raw, str):
        text = raw
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportFileError(
                "The CSV file is not valid UTF-8. Save it as a UTF-8 CSV and try again."
            ) from exc

    try:
        return _build_table(csv.reader(StringIO(text, newline="")))
    except csv.Error as exc:
        raise ImportFileError(
            "The CSV file could not be read. Check that it is a valid CSV file."
        ) from exc


def _read_xlsx(upload):
    _rewind(upload)
    try:
        workbook = load_workbook(upload, read_only=True, data_only=True)
    except Exception as exc:
        logger.warning("Could not read Excel import file: %s", exc)
        raise ImportFileError(
            "The Excel file could not be read. Make sure it is a valid .xlsx workbook."
        ) from exc

    try:
        if not workbook.worksheets:
            return TabularData(headers=[], rows=[])
        worksheet = workbook.worksheets[0]
        return _build_table(worksheet.iter_rows(values_only=True))
    except Exception as exc:
        logger.warning("Could not read Excel worksheet: %s", exc)
        raise ImportFileError(
            "The Excel worksheet could not be read. Save it as a new .xlsx file and try again."
        ) from exc
    finally:
        workbook.close()


def _build_table(row_iterator):
    iterator = iter(row_iterator)
    try:
        header_row = next(iterator)
    except StopIteration:
        return TabularData(headers=[], rows=[])

    headers = [normalize_cell(value) for value in header_row]
    normalized_headers = [normalize_header(value) for value in headers]
    if not any(normalized_headers):
        return TabularData(headers=[], rows=[])

    rows = []
    for source_row_number, raw_values in enumerate(iterator, start=2):
        values = [normalize_cell(value) for value in raw_values]
        if not any(values):
            continue

        row = {}
        for key, value in zip(normalized_headers, values):
            if key and key not in row:
                row[key] = value

        if not row:
            continue
        row[ROW_NUMBER_KEY] = str(source_row_number)
        rows.append(row)

    return TabularData(headers=headers, rows=rows)


IMPORT_TEMPLATES = {
    "students": {
        "title": "Students",
        "filename": "students-import-template.xlsx",
        "sheet_title": "Students",
        "headers": [
            "Registration Number",
            "First Name",
            "Last Name",
            "Department",
            "Level",
            "Gender",
            "Email",
        ],
        "widths": [24, 18, 18, 18, 10, 12, 32],
        "text_columns": [1],
        "validations": [
            {
                "column": 4,
                "values": "COM,SWE,IFT,CBS,CS,SE,IT,CY",
            },
            {"column": 5, "values": "100,200,300,400"},
            {"column": 6, "values": "M,F"},
        ],
        "notes": [
            "Registration Number is required. It becomes the student's username and starting password.",
            "Department accepts COM/CS, SWE/SE, IFT/IT, or CBS/CY.",
            "Level must be 100, 200, 300, or 400. Gender must be M or F.",
            "Email is optional. Existing students are not overwritten; their missing login is created.",
        ],
        "example": [
            "CST/22/SWE/00001",
            "Aisha",
            "Bello",
            "SWE",
            "200",
            "F",
            "aisha.bello@example.com",
        ],
    },
    "courses": {
        "title": "Courses",
        "filename": "courses-import-template.xlsx",
        "sheet_title": "Courses",
        "headers": [
            "Course Code",
            "Course Title",
            "Department",
            "Level",
            "Semester",
        ],
        "widths": [18, 42, 18, 10, 16],
        "text_columns": [1],
        "validations": [
            {
                "column": 3,
                "values": "COM,SWE,IFT,CBS,ALL,CS,SE,IT,CY",
            },
            {"column": 4, "values": "100,200,300,400"},
            {"column": 5, "values": "First,Second"},
        ],
        "notes": [
            "Course Code is required and must be unique.",
            "Department accepts COM/CS, SWE/SE, IFT/IT, CBS/CY, or ALL for a shared course.",
            "Level must be 100, 200, 300, or 400. Semester must be First or Second.",
            "Existing course codes are skipped; their details are never overwritten.",
        ],
        "example": [
            "SWE301",
            "Software Engineering",
            "SWE",
            "300",
            "First",
        ],
    },
    "invigilators": {
        "title": "Invigilators",
        "filename": "invigilators-import-template.xlsx",
        "sheet_title": "Invigilators",
        "headers": ["Staff ID", "Full Name", "Phone Number"],
        "widths": [20, 36, 20],
        "text_columns": [1, 3],
        "validations": [],
        "notes": [
            "Staff ID is required and must be unique.",
            "Each newly-created invigilator gets a login with the Staff ID as both username and starting password.",
            "Phone Number is optional. Keep it as text so leading zeros are preserved.",
            "Existing Staff IDs are skipped and their details are not overwritten.",
        ],
        "example": ["STF-001", "Dr. Aisha Bello", "08030000000"],
    },
    "registrations": {
        "title": "Course Registrations",
        "filename": "course-registrations-import-template.xlsx",
        "sheet_title": "Registrations",
        "headers": ["Reg No", "Full Name"],
        "widths": [24, 36],
        "text_columns": [1],
        "validations": [],
        "notes": [
            "Pick the course on the import page before uploading this file.",
            "Reg No is required and must match a student already in the system.",
            "Full Name is optional, but it is checked against the student's name to catch reg-number typos.",
            "Leave 'Replace the existing list' unticked to add students and keep the current list.",
        ],
        "example": ["CST/22/SWE/00001", "Aisha Bello"],
    },
    "timetable": {
        "title": "Timetable Exams",
        "filename": "timetable-exams-import-template.xlsx",
        "sheet_title": "Exams",
        "headers": ["Course Code", "Date", "Time", "Duration"],
        "widths": [18, 16, 12, 18],
        "text_columns": [1],
        "number_formats": {2: "yyyy-mm-dd", 3: "hh:mm"},
        "validations": [],
        "notes": [
            "Course Code is required and must already exist in Courses.",
            "Date can be an Excel date or text in YYYY-MM-DD format.",
            "Time can be an Excel time or text in 24-hour HH:MM format.",
            "Duration is in minutes and must be a whole number.",
            "Open a draft timetable and upload this file from its upload card.",
        ],
        "example": ["SWE301", "2026-12-07", "09:00", "120"],
    },
}


def build_import_template_response(kind):
    config = IMPORT_TEMPLATES[kind]
    workbook = _build_template_workbook(config)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()

    response = HttpResponse(buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = (
        f'attachment; filename="{config["filename"]}"'
    )
    return response


def _build_template_workbook(config):
    workbook = Workbook()
    workbook.properties.title = f"{config['title']} import template"
    workbook.properties.creator = "Exam Allocation System"

    worksheet = workbook.active
    worksheet.title = config["sheet_title"]
    worksheet.append(config["headers"])
    worksheet.row_dimensions[1].height = 26
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = (
        f"A1:{get_column_letter(len(config['headers']))}1"
    )
    worksheet.sheet_properties.tabColor = "0B3B6F"

    for cell in worksheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGNMENT

    for index, width in enumerate(config["widths"], start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = width

    for index in config.get("text_columns", []):
        worksheet.column_dimensions[
            get_column_letter(index)
        ].number_format = "@"

    for index, number_format in config.get("number_formats", {}).items():
        worksheet.column_dimensions[
            get_column_letter(index)
        ].number_format = number_format

    for validation in config.get("validations", []):
        data_validation = DataValidation(
            type="list",
            formula1=f'"{validation["values"]}"',
            allow_blank=True,
            showErrorMessage=True,
            errorTitle="Invalid value",
            error="Choose one of the values from the drop-down list.",
        )
        column = get_column_letter(validation["column"])
        worksheet.add_data_validation(data_validation)
        data_validation.add(f"{column}2:{column}1000")

    _add_instructions_sheet(workbook, config)
    return workbook


def _add_instructions_sheet(workbook, config):
    worksheet = workbook.create_sheet("Instructions")
    worksheet.sheet_view.showGridLines = False
    worksheet.column_dimensions["A"].width = 24
    worksheet.column_dimensions["B"].width = 105

    title = worksheet["A1"]
    title.value = f"{config['title']} import template"
    title.font = Font(size=16, bold=True, color="0B3B6F")
    worksheet.merge_cells("A1:B1")

    rows = [
        (
            "Data sheet",
            f"Fill the '{config['sheet_title']}' sheet, which is the first sheet in this workbook. "
            "The import reads only the first sheet.",
        ),
        (
            "Accepted files",
            "Save and upload this .xlsx workbook, or save the data sheet as a .csv file with the same headers.",
        ),
        (
            "Header row",
            "Do not rename or delete the first row: "
            + ", ".join(config["headers"])
            + ".",
        ),
        (
            "Blank rows",
            "Blank rows are ignored. Keep one record per row.",
        ),
    ]
    rows.extend(("Note", note) for note in config["notes"])
    rows.append(
        (
            "Example row",
            " | ".join(config["example"]),
        )
    )
    rows.append(
        (
            "Important",
            "The example is for reference only. Do not paste it into the data sheet unless it is real data.",
        )
    )

    row_number = 3
    for label, text in rows:
        label_cell = worksheet.cell(row=row_number, column=1, value=label)
        label_cell.font = Font(bold=True, color="0B3B6F")
        label_cell.alignment = Alignment(vertical="top")
        text_cell = worksheet.cell(row=row_number, column=2, value=text)
        text_cell.alignment = Alignment(wrap_text=True, vertical="top")
        row_number += 1
