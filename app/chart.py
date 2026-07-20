from __future__ import annotations

import io
import math
from collections import defaultdict
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont

from .models import DailyReport, PeriodReport


Report = DailyReport | PeriodReport


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # Pillow < 10
            return ImageFont.load_default()


def trend_points(report: Report) -> list[dict[str, int | str]]:
    report_type = "daily" if isinstance(report, DailyReport) else report.report_type
    if report_type == "daily":
        commits_by_hour = defaultdict(list)
        for commit in report.commits:
            commits_by_hour[commit.activity_at.hour].append(commit)
        return [
            {
                "label": f"{hour:02d}:00",
                "commits": len(commits_by_hour[hour]),
                "repositories": len({commit.repository for commit in commits_by_hour[hour]}),
                "contributors": len({(commit.author_email or commit.author_name).casefold() for commit in commits_by_hour[hour]}),
            }
            for hour in range(24)
        ]

    start = date.fromisoformat(report.period_start)
    end = date.fromisoformat(report.period_end)
    if report_type == "yearly":
        commits_by_month = defaultdict(list)
        for commit in report.commits:
            commits_by_month[commit.activity_at.strftime("%Y-%m")].append(commit)
        points = []
        cursor = start.replace(day=1)
        while cursor <= end:
            key = cursor.strftime("%Y-%m")
            commits = commits_by_month[key]
            points.append({
                "label": key,
                "commits": len(commits),
                "repositories": len({commit.repository for commit in commits}),
                "contributors": len({(commit.author_email or commit.author_name).casefold() for commit in commits}),
            })
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        return points

    commits_by_day = defaultdict(list)
    for commit in report.commits:
        commits_by_day[commit.activity_at.date().isoformat()].append(commit)
    points = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        commits = commits_by_day[key]
        points.append({
            "label": key[5:],
            "commits": len(commits),
            "repositories": len({commit.repository for commit in commits}),
            "contributors": len({(commit.author_email or commit.author_name).casefold() for commit in commits}),
        })
        cursor += timedelta(days=1)
    return points


def render_trend_chart(report: Report, width: int = 960, height: int = 320) -> bytes | None:
    points = trend_points(report)
    values = [int(point["commits"]) for point in points]
    if not values or max(values) == 0:
        return None

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    font = _font(13)
    value_font = _font(12)
    left, top, right, bottom = 58, 24, 22, 46
    plot_width = width - left - right
    plot_height = height - top - bottom

    maximum = max(values)
    tick_step = max(1, math.ceil(maximum / 4))
    y_max = tick_step * 4
    for index in range(5):
        value = tick_step * index
        y = top + plot_height - (value / y_max * plot_height)
        draw.line((left, y, width - right, y), fill="#e4e7ec", width=1)
        label = str(value)
        label_width = draw.textbbox((0, 0), label, font=font)[2]
        draw.text((left - label_width - 8, y - 7), label, fill="#667085", font=font)

    x_positions = [left + (plot_width * index / max(1, len(points) - 1)) for index in range(len(points))]
    coordinates = [
        (x, top + plot_height - (value / y_max * plot_height))
        for x, value in zip(x_positions, values)
    ]
    baseline = top + plot_height
    draw.polygon([(coordinates[0][0], baseline), *coordinates, (coordinates[-1][0], baseline)], fill="#eff6ff")
    draw.line(coordinates, fill="#2563eb", width=3, joint="curve")
    for x, y in coordinates:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#ffffff", outline="#2563eb", width=2)

    label_count = min(8, len(points))
    label_indexes = {0} if label_count == 1 else {
        round(index * (len(points) - 1) / (label_count - 1)) for index in range(label_count)
    }
    for index in sorted(label_indexes):
        label = str(points[index]["label"])
        label_width = draw.textbbox((0, 0), label, font=font)[2]
        draw.text((x_positions[index] - label_width / 2, baseline + 12), label, fill="#667085", font=font)

    peak_index = values.index(maximum)
    peak_x, peak_y = coordinates[peak_index]
    peak_label = str(maximum)
    peak_width = draw.textbbox((0, 0), peak_label, font=value_font)[2]
    draw.text((peak_x - peak_width / 2, max(2, peak_y - 20)), peak_label, fill="#101828", font=value_font)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
