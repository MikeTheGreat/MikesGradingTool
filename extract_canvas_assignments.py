#!/usr/bin/env python3
"""
extract_canvas_assignments.py

Read every assignment, quiz, and discussion topic (that has a due date)
from a Canvas course and emit a JSON block formatted like the
courses/{COURSE}/assignments section of config.json.

Every due date is expressed as a flat calendar-day offset from
START_OF_QUARTER, e.g.:

    "due_date": {
        "relative_to": { "type": "START_OF_QUARTER" },
        "offsets": ["+14 CALENDAR_DAY"]
    }

Items with no due date get a NO_DUE_DATE entry.

Existing config keys are reused where the canvas_name matches.

Usage
-----
    python extract_canvas_assignments.py --course 142
    python extract_canvas_assignments.py --course 142 --output assignments.json
"""

import argparse
import datetime
import json
import re
import sys
from typing import Dict, List, Optional

import canvasapi
import canvasapi.current_user
import pytz

from mikesgradingtool.utils.config_json import get_app_config
from mikesgradingtool.Canvas.CanvasHelper import get_general_due_date_info_defaults


# ---------------------------------------------------------------------------
# Tiny data class for a unified Canvas item
# ---------------------------------------------------------------------------
class CanvasItem:
    __slots__ = ("name", "due_dt", "source")

    def __init__(self, name: str, due_dt: Optional[datetime.datetime], source: str):
        self.name   = " ".join(name.split())   # collapse whitespace
        self.due_dt = due_dt                    # UTC-aware datetime or None
        self.source = source                    # "assignment" | "quiz" | "discussion"

    def __repr__(self):
        return f"CanvasItem({self.name!r}, due={self.due_dt}, src={self.source})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_canvas_dt(val) -> Optional[datetime.datetime]:
    """Accept a datetime or an ISO 8601 string; return a UTC-aware datetime."""
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val if val.tzinfo else val.replace(tzinfo=datetime.timezone.utc)
    if isinstance(val, str):
        try:
            return datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def make_key(name: str) -> str:
    """Convert a Canvas name to a valid JSON config key."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")


def unique_key(base: str, used: set) -> str:
    key, n = base, 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    return key


def offset_str(days: int) -> str:
    return f"+{days} CALENDAR_DAY" if days >= 0 else f"{days} CALENDAR_DAY"


def local_time_str(dt: datetime.datetime, tz) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


# ---------------------------------------------------------------------------
# Canvas data collection
# ---------------------------------------------------------------------------
def collect_items(course) -> List[CanvasItem]:
    """
    Fetch assignments, quizzes, and discussion topics; deduplicate by name.
    All items are returned (due_dt may be None).
    """
    seen: Dict[str, CanvasItem] = {}

    # 1. Assignments (covers graded quizzes and graded discussions too)
    print("  Fetching assignments…", flush=True)
    for a in course.get_assignments():
        due = None
        if hasattr(a, "due_at_date"):
            due = parse_canvas_dt(a.due_at_date)
        elif hasattr(a, "due_at"):
            due = parse_canvas_dt(a.due_at)
        item = CanvasItem(a.name, due, "assignment")
        seen[item.name] = item

    # 2. Quizzes (catches ungraded/survey quizzes not in assignments)
    print("  Fetching quizzes…", flush=True)
    for q in course.get_quizzes():
        name = " ".join(q.title.split())
        if name in seen:
            continue
        due = parse_canvas_dt(getattr(q, "due_at", None))
        if due is not None:
            seen[name] = CanvasItem(name, due, "quiz")

    # 3. Discussion topics (only those with a due date)
    print("  Fetching discussion topics…", flush=True)
    for t in course.get_discussion_topics():
        name = " ".join(t.title.split())
        if name in seen:
            continue
        due = None
        for attr in ("todo_date", "due_at"):
            raw = getattr(t, attr, None)
            if raw:
                due = parse_canvas_dt(raw)
                break
        if due is not None:
            seen[name] = CanvasItem(name, due, "discussion")

    items = list(seen.values())
    # Sort: items with due dates first (ascending by due date), then no-due-date items
    items.sort(key=lambda i: (
        0 if i.due_dt else 1,
        i.due_dt or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc),
        i.name,
    ))
    return items


# ---------------------------------------------------------------------------
# Key lookup from existing config
# ---------------------------------------------------------------------------
def build_existing_key_lookup(config, course_name: str) -> Dict[str, str]:
    """
    Returns  canvas_name (normalised) → existing JSON key
    for any assignment already present in courses/{course_name}/assignments.
    """
    lookup: Dict[str, str] = {}
    try:
        existing = config.getKey(f"courses/{course_name}/assignments", "")
        if existing == "":
            return lookup
        for key, info in existing.items():
            try:
                cname = " ".join(str(info["canvas_api"]["canvas_name"]).split())
                lookup[cname] = str(key)
            except (KeyError, TypeError):
                pass
    except Exception:
        pass
    return lookup


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract Canvas course items and emit a config.json-style "
            "assignments block.  Every due date is expressed as a "
            "calendar-day offset from START_OF_QUARTER."
        )
    )
    parser.add_argument(
        "--course", required=True,
        help="Course key in config.json (e.g. 142)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write JSON to this file instead of stdout",
    )
    args = parser.parse_args()
    course_name = args.course

    # ── Load config ──────────────────────────────────────────────────────────
    print("Loading config…", flush=True)
    config = get_app_config()

    api_url      = config.getKey("canvas/api/url")
    api_key      = config.getKey("canvas/api/key")
    sz_re_course = config.getKey(f"courses/{course_name}/canvas_api/sz_re_course")

    general_dd = get_general_due_date_info_defaults()
    if general_dd is None:
        sys.exit(1)

    tz               = general_dd["time_zone"]
    start_of_qtr     = general_dd["date_of_first_day_of_the_quarter"]   # UTC datetime
    default_time     = general_dd["assignment_default_due_time"]         # datetime.time or None
    default_time_str = default_time.strftime("%H:%M") if default_time else "23:59"

    start_date = start_of_qtr.astimezone(tz).date()

    print(f"  Course          : {course_name}")
    print(f"  Canvas pattern  : {sz_re_course}")
    print(f"  Start of quarter: {start_date}")
    print(f"  Default due time: {default_time_str}")

    # ── Cross-reference existing assignments ─────────────────────────────────
    existing_by_canvas_name = build_existing_key_lookup(config, course_name)
    print(f"\n  Existing config keys for '{course_name}': {len(existing_by_canvas_name)}")

    # ── Connect to Canvas ─────────────────────────────────────────────────────
    print("\nConnecting to Canvas…", flush=True)
    canvas_conn = canvasapi.Canvas(api_url, api_key)
    try:
        curuser = canvasapi.current_user.CurrentUser(canvas_conn._Canvas__requester)
    except Exception as e:
        print(f"ERROR: Could not connect to Canvas: {e}", file=sys.stderr)
        sys.exit(1)

    target_course = None
    for c in curuser.get_courses(
        enrollment_type="teacher",
        state=["unpublished", "available"],
        include=["term"],
    ):
        if hasattr(c, "name") and re.search(sz_re_course, c.name):
            target_course = c
            break

    if target_course is None:
        print(f"ERROR: No course matched pattern {sz_re_course!r}", file=sys.stderr)
        sys.exit(1)

    print(f"  Found course: {target_course.name!r}")

    # ── Collect all items ────────────────────────────────────────────────────
    print("\nCollecting Canvas items…", flush=True)
    all_items = collect_items(target_course)

    with_due    = [i for i in all_items if i.due_dt is not None]
    without_due = [i for i in all_items if i.due_dt is None]
    print(f"  Items with due dates   : {len(with_due)}")
    print(f"  Items without due dates: {len(without_due)}")

    # ── Build JSON entries ────────────────────────────────────────────────────
    used_keys: set = set()

    def resolve_key(item: CanvasItem) -> str:
        if item.name in existing_by_canvas_name:
            k = existing_by_canvas_name[item.name]
        else:
            k = unique_key(make_key(item.name), used_keys)
        used_keys.add(k)
        return k

    result: Dict[str, dict] = {}

    # Items with due dates — sorted ascending by due date
    for item in with_due:
        key       = resolve_key(item)
        item_date = item.due_dt.astimezone(tz).date()
        days      = (item_date - start_date).days

        offsets = [offset_str(days)]
        t = local_time_str(item.due_dt, tz)
        if t != default_time_str:
            offsets.append(f"{t} ABS_TIME")

        result[key] = {
            "name":       key,
            "canvas_api": {"canvas_name": item.name},
            "due_date": {
                "relative_to": {"type": "START_OF_QUARTER"},
                "offsets":     offsets,
            },
        }

    # Items with no due date
    for item in without_due:
        key = resolve_key(item)
        result[key] = {
            "name":       key,
            "canvas_api": {"canvas_name": item.name},
            "due_date": {
                "relative_to": {"type": "NO_DUE_DATE"},
                "offsets":     [],
            },
        }

    # ── Output ────────────────────────────────────────────────────────────────
    output_json = json.dumps(result, indent=4)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
            f.write("\n")
        print(f"\nWrote {len(result)} entries to {args.output!r}")
    else:
        print("\n" + "=" * 70)
        print(output_json)

    reused = sum(1 for k in result if k in set(existing_by_canvas_name.values()))
    print(f"\nSummary: {len(result)} total  "
          f"({len(with_due)} with due date, {len(without_due)} without)  "
          f"{reused} keys reused from existing config")


if __name__ == "__main__":
    main()
