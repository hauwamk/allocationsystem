"""Draws a student's examination timetable as a PNG or JPEG image.

The web page and this image are fed by the same rows from
_build_student_exam_rows and show the same four columns: course code,
course title, date and time.
"""

from io import BytesIO
from pathlib import Path

from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1600
MARGIN = 64

NAVY = "#0B3B6F"
BRAND = "#0077A8"
INK = "#16212E"
MUTED = "#566B7D"
LINE = "#D8E4EC"
RULE = "#BFE3F0"
HEADER_BG = "#E6F5FB"
EMPTY_BG = "#F3F7FA"

COLUMNS = (
    ("Course Code", 220),
    ("Course Title", 780),
    ("Date", 260),
    ("Time", 212),
)
COLUMN_X = []
_x = MARGIN
for _label, _width in COLUMNS:
    COLUMN_X.append(_x)
    _x += _width

HEADER_RULE_Y = 196
TABLE_TOP = 232
TABLE_HEADER_HEIGHT = 56
CELL_PADDING = 18
ROW_MIN_HEIGHT = 64
LINE_HEIGHT = 28
EMPTY_BOX_HEIGHT = 180

REGULAR_FONT_PATHS = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
BOLD_FONT_PATHS = (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


def _font(size, bold=False):
    for path in BOLD_FONT_PATHS if bold else REGULAR_FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow before 10.1 has no sized default font
        return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words = str(text).split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _format_date(value):
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def _format_time(value):
    return value.strftime("%I:%M %p").lstrip("0")


def _draw_line(draw, x, top, height, text, font, fill):
    """Draws one line of text, vertically centered in a cell."""
    box = draw.textbbox((0, 0), text, font=font)
    y = top + (height - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, font=font, fill=fill)


def _draw_block(draw, x, top, height, lines, font, fill):
    block_height = len(lines) * LINE_HEIGHT
    block_top = top + (height - block_height) / 2
    for index, line in enumerate(lines):
        _draw_line(draw, x, block_top + index * LINE_HEIGHT, LINE_HEIGHT, line, font, fill)


def _draw_right(draw, right, top, text, font, fill):
    draw.text((right - draw.textlength(text, font=font), top), text, font=font, fill=fill)


def _row_values(row):
    exam = row["exam"]

    return [
        exam.course.course_code,
        exam.course.course_title,
        _format_date(exam.exam_date),
        _format_time(exam.exam_time),
    ]


def _layout_rows(draw, exam_rows):
    body_font = _font(21)
    rows = []
    for row in exam_rows:
        values = _row_values(row)
        title_lines = _wrap(
            draw, values[1], body_font, COLUMNS[1][1] - 2 * CELL_PADDING
        )
        line_count = max(len(title_lines), 1)
        height = max(ROW_MIN_HEIGHT, line_count * LINE_HEIGHT + 2 * 14)
        rows.append({
            "values": values,
            "title_lines": title_lines,
            "height": height,
        })
    return rows


def render_timetable_image(student, exam_rows, image_format="png", generated_at=None):
    """Returns the timetable as image bytes. image_format is "png" or "jpg"."""
    if generated_at is None:
        generated_at = timezone.localtime()

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    rows = _layout_rows(measure, exam_rows)

    table_height = (
        TABLE_HEADER_HEIGHT + sum(row["height"] for row in rows)
        if rows
        else EMPTY_BOX_HEIGHT
    )
    footer_y = TABLE_TOP + table_height + 34
    height = footer_y + 22 + 30 + MARGIN

    image = Image.new("RGB", (WIDTH, height), "white")
    draw = ImageDraw.Draw(image)

    # Header
    _draw_line(draw, MARGIN, 62, 22, "BAYERO UNIVERSITY KANO  \u00b7  FACULTY OF COMPUTING",
               _font(18), MUTED)
    draw.text((MARGIN, 92), "My Examination Timetable", font=_font(44, bold=True), fill=NAVY)
    draw.text(
        (MARGIN, 156),
        "Examination Venue & Seat Allocation System",
        font=_font(20),
        fill=MUTED,
    )

    right = WIDTH - MARGIN
    _draw_right(draw, right, 88, f"{student.first_name} {student.last_name}",
                _font(26, bold=True), NAVY)
    _draw_right(draw, right, 126, f"Reg. No: {student.registration_number}",
                _font(20), INK)
    _draw_right(draw, right, 156,
                f"{student.get_department_display()} \u00b7 Level {student.level}",
                _font(20), MUTED)

    draw.rectangle([MARGIN, HEADER_RULE_Y, WIDTH - MARGIN, HEADER_RULE_Y + 4], fill=BRAND)

    # Table header
    draw.rectangle(
        [MARGIN, TABLE_TOP, WIDTH - MARGIN, TABLE_TOP + TABLE_HEADER_HEIGHT],
        fill=HEADER_BG,
    )
    draw.line(
        [MARGIN, TABLE_TOP + TABLE_HEADER_HEIGHT,
         WIDTH - MARGIN, TABLE_TOP + TABLE_HEADER_HEIGHT],
        fill=RULE,
        width=2,
    )
    header_font = _font(16, bold=True)
    for index, (label, _width) in enumerate(COLUMNS):
        _draw_line(draw, COLUMN_X[index] + CELL_PADDING, TABLE_TOP,
                   TABLE_HEADER_HEIGHT, label.upper(), header_font, MUTED)

    body_font = _font(21)
    strong_font = _font(21, bold=True)

    y = TABLE_TOP + TABLE_HEADER_HEIGHT
    for row in rows:
        row_height = row["height"]
        values = row["values"]

        _draw_line(draw, COLUMN_X[0] + CELL_PADDING, y, row_height,
                   values[0], strong_font, NAVY)
        _draw_block(draw, COLUMN_X[1] + CELL_PADDING, y, row_height,
                    row["title_lines"], body_font, INK)
        _draw_line(draw, COLUMN_X[2] + CELL_PADDING, y, row_height,
                   values[2], body_font, INK)
        _draw_line(draw, COLUMN_X[3] + CELL_PADDING, y, row_height,
                   values[3], body_font, INK)

        y += row_height
        draw.line([MARGIN, y, WIDTH - MARGIN, y], fill=LINE, width=1)

    if not rows:
        draw.rounded_rectangle(
            [MARGIN, TABLE_TOP, WIDTH - MARGIN, TABLE_TOP + EMPTY_BOX_HEIGHT],
            radius=12,
            fill=EMPTY_BG,
            outline=LINE,
            width=2,
        )
        message = "You currently have no scheduled examinations."
        message_font = _font(22)
        message_width = draw.textlength(message, font=message_font)
        _draw_line(draw, (WIDTH - message_width) / 2, TABLE_TOP,
                   EMPTY_BOX_HEIGHT, message, message_font, MUTED)

    # Footer
    draw.line([MARGIN, footer_y, WIDTH - MARGIN, footer_y], fill=LINE, width=1)
    stamped = (
        f"{generated_at.strftime('%b')} {generated_at.day}, {generated_at.year}, "
        f"{generated_at.strftime('%I:%M %p').lstrip('0')}"
    )
    draw.text((MARGIN, footer_y + 22), f"Generated {stamped}",
              font=_font(18), fill=MUTED)
    _draw_right(draw, WIDTH - MARGIN, footer_y + 22,
                "Bayero University Kano \u00b7 Examination Venue & Seat Allocation System",
                _font(18), MUTED)

    buffer = BytesIO()
    if image_format == "jpg":
        image.save(buffer, format="JPEG", quality=92, optimize=True)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
