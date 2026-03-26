#!/usr/bin/env python3
"""
extract_canvas_assignments.py

Read every assignment, quiz, and discussion topic (that has a due date)
from a Canvas course and emit a JSON block formatted exactly like the
courses/{COURSE}/assignments section of config.json.

Relative-chain strategy
-----------------------
"Hybrid Participation Week N" assignments are the weekly anchors.
  • Week 6's anchor  = the Midterm exam   (there is no HP Week 6)
  • Week 11's anchor = the Final exam     (there is no HP Week 11)

Anchors are expressed relative to each other in order:
  HP Week 1  → FIRST_CLASS_OF_QUARTER  + N CALENDAR_DAY
  HP Week 2  → HP Week 1               + N CALENDAR_DAY
  ...
  Midterm    → HP Week 5               + N CALENDAR_DAY
  HP Week 7  → Midterm                 + N CALENDAR_DAY
  ...
  Final      → HP Week 10              + N CALENDAR_DAY

Every other item is expressed relative to its week's anchor:
  • If the item's name contains "Week N" → anchor to that week.
  • Otherwise → anchor to the HP/Midterm/Final whose due date falls in
    the same ISO calendar week.
  • Fallback → most-recent anchor before the item's due date.

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
from typing import Dict, List, Optional, Tuple

import canvasapi
import canvasapi.current_user
import pytz

from mikesgradingtool.utils.config_json import get_app_config
from mikesgradingtool.Canvas.CanvasHelper import get_general_due_date_info_defaults

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
HP_WEEK_RE  = re.compile(r"Hybrid\s+Participation\s+Week\s+0*(\d+)", re.IGNORECASE)
MIDTERM_RE  = re.compile(r"(?=.*\bMidterm\b)(?=.*\bExam\b)(?=.*\bPlaceholder\b)", re.IGNORECASE)
FINAL_RE    = re.compile(r"(?=.*\bFinal\b)(?=.*\bExam\b)(?=.*\bPlaceholder\b)", re.IGNORECASE)
WEEK_NUM_RE = re.compile(r"\bWeek\s+0*(\d+)\b", re.IGNORECASE)

MIDTERM_WEEK = 6
FINAL_WEEK   = 11


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
        if val.tzinfo is None:
            return val.replace(tzinfo=datetime.timezone.utc)
        return val
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


def first_class_date(start: datetime.date, class_day_abbrevs: List[str]) -> datetime.date:
    """Return the first calendar date >= start that falls on a class day."""
    abbr_to_idx = {a: i for i, a in enumerate(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])}
    class_weekdays = {abbr_to_idx[a] for a in class_day_abbrevs if a in abbr_to_idx}
    d = start
    for _ in range(14):
        if d.weekday() in class_weekdays:
            return d
        d += datetime.timedelta(days=1)
    raise ValueError(f"No class day found within 2 weeks of {start} (class days: {class_day_abbrevs})")


def build_due_date(relative_type: str,
                   assignment_name: Optional[str],
                   days_offset: int,
                   item_dt: Optional[datetime.datetime],
                   tz,
                   default_time: str) -> dict:
    """
    Build the 'due_date' dict that goes into the config JSON.
    Includes ABS_TIME offset only when the item's due time differs from default.
    """
    offsets = []
    if days_offset != 0:
        offsets.append(offset_str(days_offset))
    if item_dt is not None:
        t = local_time_str(item_dt, tz)
        if t != default_time:
            offsets.append(f"{t} ABS_TIME")

    rel: dict = {"type": relative_type}
    if assignment_name:
        rel["assignment_name"] = assignment_name

    return {"relative_to": rel, "offsets": offsets}


# ---------------------------------------------------------------------------
# Canvas data collection
# ---------------------------------------------------------------------------
def collect_items(course) -> List[CanvasItem]:
    """
    Fetch assignments, quizzes, and discussion topics; deduplicate by name.
    Returns all items, including those without a due date (due_dt=None).
    """
    seen: Dict[str, CanvasItem] = {}

    # 1. Assignments  (covers graded quizzes and graded discussions too)
    print("  Fetching assignments…", flush=True)
    for a in course.get_assignments():
        due = None
        if hasattr(a, "due_at_date"):
            due = parse_canvas_dt(a.due_at_date)
        elif hasattr(a, "due_at"):
            due = parse_canvas_dt(a.due_at)
        item = CanvasItem(a.name, due, "assignment")
        seen[item.name] = item

    # 2. Quizzes  (catches ungraded/survey quizzes not in assignments)
    print("  Fetching quizzes…", flush=True)
    for q in course.get_quizzes():
        name = " ".join(q.title.split())
        if name in seen:
            continue
        due = parse_canvas_dt(getattr(q, "due_at", None))
        if due is not None:
            seen[name] = CanvasItem(name, due, "quiz")

    # 3. Discussion topics  (only if they carry a due date)
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
    # Sort: items with due dates first (ascending), then no-due-date items
    items.sort(key=lambda i: (
        0 if i.due_dt else 1,
        i.due_dt or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc),
        i.name,
    ))
    return items


# ---------------------------------------------------------------------------
# Anchor detection
# ---------------------------------------------------------------------------
def classify_items(
    items: List[CanvasItem],
) -> Tuple[Dict[int, CanvasItem], List[CanvasItem]]:
    """
    Split items into:
      anchors      { week_number -> CanvasItem }
      non_anchors  [ CanvasItem, … ]

    HP Week N assignments are anchors for their week numbers.
    The Midterm is the anchor for MIDTERM_WEEK (replaces HP Week 6).
    The Final   is the anchor for FINAL_WEEK   (replaces HP Week 11).

    An item that matches BOTH Midterm/Final and HP_WEEK (unlikely, but
    defensive) is treated as an HP anchor.
    """
    anchors: Dict[int, CanvasItem] = {}
    non_anchors: List[CanvasItem] = []
    midterm_candidate: Optional[CanvasItem] = None
    final_candidate:   Optional[CanvasItem] = None

    for item in items:
        m = HP_WEEK_RE.search(item.name)
        if m:
            anchors[int(m.group(1))] = item
            continue

        if MIDTERM_RE.search(item.name):
            # Prefer the first Midterm match we encounter (by due date order)
            if midterm_candidate is None:
                midterm_candidate = item
            continue

        if FINAL_RE.search(item.name):
            if final_candidate is None:
                final_candidate = item
            continue

        non_anchors.append(item)

    if midterm_candidate and MIDTERM_WEEK not in anchors:
        anchors[MIDTERM_WEEK] = midterm_candidate
    elif midterm_candidate:
        # HP Week 6 already present; demote Midterm to non-anchor
        non_anchors.append(midterm_candidate)

    if final_candidate and FINAL_WEEK not in anchors:
        anchors[FINAL_WEEK] = final_candidate
    elif final_candidate:
        non_anchors.append(final_candidate)

    return anchors, non_anchors


# ---------------------------------------------------------------------------
# Anchor assignment for a non-anchor item
# ---------------------------------------------------------------------------
def find_anchor_for(
    item: CanvasItem,
    anchors: Dict[int, CanvasItem],
    anchor_keys: Dict[int, str],
) -> Tuple[Optional[str], Optional[CanvasItem]]:
    """
    Return (json_key, anchor_CanvasItem) for the best anchor to express
    `item` relative to.

    Priority:
      1. "Week N" in item's name → use that week's anchor (if present).
      2. Same ISO (year, week_number) as an anchor's due date.
      3. Most-recent anchor whose due date <= item's due date.
      4. First anchor (item is before all anchors).
    """
    # 1. Name-based
    wm = WEEK_NUM_RE.search(item.name)
    if wm:
        wn = int(wm.group(1))
        if wn in anchors:
            return anchor_keys[wn], anchors[wn]

    if item.due_dt is None:
        # No due date → no anchor
        return None, None

    # 2. Same ISO week
    item_iso = item.due_dt.isocalendar()[:2]   # (year, week)
    for wn in sorted(anchors):
        a = anchors[wn]
        if a.due_dt and a.due_dt.isocalendar()[:2] == item_iso:
            return anchor_keys[wn], a

    # 3. Most-recent anchor on or before item
    best_wn: Optional[int] = None
    for wn in sorted(anchors):
        a = anchors[wn]
        if a.due_dt and a.due_dt <= item.due_dt:
            best_wn = wn
    if best_wn is not None:
        return anchor_keys[best_wn], anchors[best_wn]

    # 4. Item is before all anchors → use the earliest anchor
    if anchors:
        first_wn = min(anchors)
        return anchor_keys[first_wn], anchors[first_wn]

    return None, None


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
            "assignments block with relative due-date chains."
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

    api_url = config.getKey("canvas/api/url")
    api_key = config.getKey("canvas/api/key")
    sz_re_course = config.getKey(f"courses/{course_name}/canvas_api/sz_re_course")

    general_dd = get_general_due_date_info_defaults()
    if general_dd is None:
        sys.exit(1)

    tz            = general_dd["time_zone"]
    start_of_qtr  = general_dd["date_of_first_day_of_the_quarter"]   # UTC datetime
    default_time  = general_dd["assignment_default_due_time"]          # datetime.time or None
    default_time_str = default_time.strftime("%H:%M") if default_time else "23:59"

    # Class days for this course (used to find the first class day)
    course_dd_raw = config.getKey(f"courses/{course_name}/due_date_info", "")
    class_day_abbrevs: List[str] = (
        list(course_dd_raw["days_of_week"])
        if course_dd_raw != "" and "days_of_week" in course_dd_raw
        else ["Mon"]
    )

    first_class = first_class_date(start_of_qtr.astimezone(tz).date(), class_day_abbrevs)

    print(f"  Course          : {course_name}")
    print(f"  Canvas pattern  : {sz_re_course}")
    print(f"  Start of quarter: {start_of_qtr.astimezone(tz).date()}")
    print(f"  First class day : {first_class}")
    print(f"  Class days      : {class_day_abbrevs}")
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

    items_with_due    = [i for i in all_items if i.due_dt is not None]
    items_without_due = [i for i in all_items if i.due_dt is None]
    print(f"  Items with due dates   : {len(items_with_due)}")
    print(f"  Items without due dates: {len(items_without_due)}")

    # ── Classify: anchors vs. non-anchors ────────────────────────────────────
    # Work only with items that have due dates for the anchor chain;
    # items without due dates get NO_DUE_DATE entries at the end.
    anchors, non_anchors = classify_items(items_with_due)

    print(f"\n  Weekly anchors: {sorted(anchors.keys())}")
    for wn in sorted(anchors.keys()):
        a = anchors[wn]
        dt_str = a.due_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if a.due_dt else "no date"
        print(f"    Week {wn:2d}  [{dt_str}]  {a.name!r}")

    # ── Assign JSON keys ──────────────────────────────────────────────────────
    used_keys: set = set()

    def resolve_key(item: CanvasItem) -> str:
        if item.name in existing_by_canvas_name:
            k = existing_by_canvas_name[item.name]
        else:
            k = unique_key(make_key(item.name), used_keys)
        used_keys.add(k)
        return k

    anchor_keys: Dict[int, str] = {wn: resolve_key(anchors[wn]) for wn in sorted(anchors)}

    # ── Build JSON entries ───────────────────────────────────────────────────
    result: Dict[str, dict] = {}

    # ── 1. Anchors ────────────────────────────────────────────────────────────
    sorted_weeks = sorted(anchors.keys())
    for idx, wn in enumerate(sorted_weeks):
        item = anchors[wn]
        key  = anchor_keys[wn]

        item_date = item.due_dt.astimezone(tz).date()

        if idx == 0:
            # First anchor → relative to FIRST_CLASS_OF_QUARTER
            days = (item_date - first_class).days
            dd = build_due_date("FIRST_CLASS_OF_QUARTER", None, days, item.due_dt, tz, default_time_str)
        else:
            prev_wn = sorted_weeks[idx - 1]
            offsets = ["+1 CLASS_DAY"]
            t = local_time_str(item.due_dt, tz)
            if t != default_time_str:
                offsets.append(f"{t} ABS_TIME")
            dd = {
                "relative_to": {"type": "ASSIGNMENT", "assignment_name": anchor_keys[prev_wn]},
                "offsets": offsets,
            }

        result[key] = {
            "name":       key,
            "canvas_api": {"canvas_name": item.name},
            "due_date":   dd,
        }

    # ── 2. Non-anchor items that have due dates ────────────────────────────────
    for item in non_anchors:
        key = resolve_key(item)

        item_date = item.due_dt.astimezone(tz).date()

        if not anchors:
            # No anchors at all – fall back to absolute offset from start of quarter
            days = (item_date - start_of_qtr.astimezone(tz).date()).days
            dd = build_due_date("START_OF_QUARTER", None, days, item.due_dt, tz, default_time_str)
        else:
            anchor_key, anchor_item = find_anchor_for(item, anchors, anchor_keys)
            if anchor_key and anchor_item and anchor_item.due_dt:
                anchor_date = anchor_item.due_dt.astimezone(tz).date()
                days = (item_date - anchor_date).days
                dd = build_due_date("ASSIGNMENT", anchor_key, days, item.due_dt, tz, default_time_str)
            else:
                # Fallback: absolute from start of quarter
                days = (item_date - start_of_qtr.astimezone(tz).date()).days
                dd = build_due_date("START_OF_QUARTER", None, days, item.due_dt, tz, default_time_str)

        result[key] = {
            "name":       key,
            "canvas_api": {"canvas_name": item.name},
            "due_date":   dd,
        }

    # ── 3. Items without any due date ─────────────────────────────────────────
    for item in items_without_due:
        key = resolve_key(item)
        result[key] = {
            "name":       key,
            "canvas_api": {"canvas_name": item.name},
            "due_date": {
                "relative_to": {"type": "NO_DUE_DATE"},
                "offsets": [],
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

    # ── Summary ───────────────────────────────────────────────────────────────
    reused = sum(1 for k in result if k in set(existing_by_canvas_name.values()))
    print(f"\nSummary: {len(result)} total entries  "
          f"({len(anchors)} anchors, {len(non_anchors)} non-anchors, "
          f"{len(items_without_due)} no-due-date)  "
          f"{reused} keys reused from existing config")


if __name__ == "__main__":
    main()
