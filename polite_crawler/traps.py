"""Crawler traps: URL spaces that never end (calendars, /a/a/a/... loops, page=99999).

Only clear cases are skipped before any request is sent; each skip is counted by rule.
Large URL families (one path template or one query parameter with many values) are
reported as suspected traps, not blocked: a shop's 2,000 products look the same.
"""
import re
from collections import Counter
from datetime import date, timedelta
from urllib.parse import parse_qsl, unquote, urlsplit

MAX_SEGMENTS = 20
MAX_PAGE = 500
FUTURE_DAYS = 365
REPORT_OVER = 100  # URLs per template, or values per parameter, before it is reported
DATE_PARAMS = {"date", "month", "year", "day"}
PAGE_PARAMS = {"page", "paged", "pg"}
YEAR = r"(?:19|20|21)\d\d"
# 2027-05-01, 2027_05, events-2027.05 ... inside one path segment or a query value
DATE_IN_TEXT = re.compile(rf"(?<!\d)({YEAR})[-_.](0?[1-9]|1[0-2])(?:[-_.](0?[1-9]|[12]\d|3[01]))?(?!\d)")
DIGITS = re.compile(r"\d+")


def segments(path):
    return [unquote(part) for part in path.split("/") if part]


def repeated_segments(parts):
    """The same segment 3+ times in a row, or any segment more than 3 times."""
    run = 1
    for previous, part in zip(parts, parts[1:]):
        run = run + 1 if part == previous else 1
        if run >= 3:
            return True
    return bool(parts) and Counter(parts).most_common(1)[0][1] > 3


def path_dates(parts):
    """Dates written in the last three path segments: /2027/05/01, /2027/05, /events-2027-05-01."""
    last = parts[-3:]
    for part in last:
        for year, month, day in DATE_IN_TEXT.findall(part):
            yield int(year), int(month), int(day or 1)
    for i, part in enumerate(last[:-1]):
        if re.fullmatch(YEAR, part) and re.fullmatch(r"0?[1-9]|1[0-2]", last[i + 1]):
            yield int(part), int(last[i + 1]), 1


def query_dates(query):
    for name, value in query:
        if name.lower() not in DATE_PARAMS:
            continue
        for year, month, day in DATE_IN_TEXT.findall(value):
            yield int(year), int(month), int(day or 1)
        if name.lower() == "year" and re.fullmatch(YEAR, value.strip()):
            yield int(value), 1, 1


def far_future(dates, today):
    limit = today + timedelta(days=FUTURE_DAYS)
    for year, month, day in dates:
        try:
            if date(year, month, day) > limit:  # the earliest day the URL can mean
                return True
        except ValueError:  # 2027-02-31
            continue
    return False


def trap_rule(url, today=None):
    """Name of the trap rule this URL breaks, or None to request it."""
    parts = urlsplit(url)
    path = segments(parts.path)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if len(path) > MAX_SEGMENTS:
        return "too_many_segments"
    if repeated_segments(path):
        return "repeated_segments"
    if far_future([*path_dates(path), *query_dates(query)], today or date.today()):
        return "future_date"
    pages = [value for name, value in query if name.lower() in PAGE_PARAMS]
    pages += [after for before, after in zip(path, path[1:]) if before.lower() == "page"]
    if any(page.strip().isdigit() and int(page) > MAX_PAGE for page in pages):
        return "deep_pagination"
    return None


class TrapGuard:
    def __init__(self):
        self.skipped = Counter()
        self.templates = {}  # template -> [count, examples]
        self.parameters = {}  # name -> [set of values, examples]

    def allow(self, url):
        """False (and counted) for a trap URL; otherwise noted for the suspected-trap report."""
        rule = trap_rule(url)
        if rule:
            self.skipped[rule] += 1
            return False
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        template = DIGITS.sub("N", parts.path) + ("?" + "&".join(sorted({name for name, _ in query})) if query else "")
        entry = self.templates.setdefault(template, [0, []])
        entry[0] += 1
        if len(entry[1]) < 3:
            entry[1].append(url)
        for name, value in query:
            values, examples = self.parameters.setdefault(name, [set(), []])
            if value not in values:
                values.add(value)
                if len(examples) < 3:
                    examples.append(url)
        return True

    def suspected(self):
        report = [
            {"template": template, "count": count, "examples": examples}
            for template, (count, examples) in self.templates.items() if count > REPORT_OVER
        ]
        report += [
            {"parameter": name, "count": len(values), "examples": examples}
            for name, (values, examples) in self.parameters.items() if len(values) > REPORT_OVER
        ]
        return sorted(report, key=lambda entry: -entry["count"])
