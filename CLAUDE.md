# MikesGradingTool — Claude Context

## What this project is
A CLI grading tool for Cascadia College courses (CS 115, CS 142, CS 143, etc.).
It automates Canvas LMS interactions: setting due dates, downloading submissions,
posting announcements, and working with GitHub Classroom repos.

The tool is invoked as `mikesgradingtool` (via the `pyproject.toml` entry point)
or directly with `python -m mikesgradingtool`.

## Config file
The live config lives at `~/.config/mikesgradingtool/config.json` — this is what
the tool actually reads at runtime. The file in `mikes_config/config.json` in the
repo is the working/checked-in copy that gets symlinked or copied there.

The config uses JS-style comments (`// …`) and is parsed with `jsmin` before
being loaded as JSON. Keys are case-insensitive (via `LazyCaseInsensitiveWrapper`).

Top-level config structure:
```
app-wide_config/preferred_time_zone   — e.g. "US/Pacific"
canvas/api/url                        — Canvas instance URL
canvas/api/key                        — API token
due_date_info/                        — quarter dates, default due time, holidays
courses/
  aliases/                            — short-hand aliases (e.g. "2a1" → course 142, hw a1)
  base_course/                        — inherited defaults for all courses
  142/                                — CS 142 course config
  143/                                — CS 143 course config
  115/                                — CS 115 course config
  …
```

### courses/{COURSE}/assignments structure
Each assignment entry looks like:
```json
"a1": {
    "name": "a1",
    "full_name": "Assignment 1 - Space Needle - Opportunity #1",
    "canvas_api": { "canvas_name": "Assignment 1 - Space Needle - Opportunity #1" },
    "due_date": {
        "relative_to": { "type": "ASSIGNMENT", "assignment_name": "I3" },
        "offsets": ["+2 CALENDAR_DAY"]
    }
}
```

`due_date.relative_to.type` values:
- `START_OF_QUARTER` — offset from the first day of the quarter
- `FIRST_CLASS_OF_QUARTER` — offset from the first class meeting day
- `ASSIGNMENT` — offset from another named assignment (recursive, memoized)
- `NO_DUE_DATE` — item explicitly has no due date

`due_date.offsets` values (applied in order):
- `+N CALENDAR_DAY` / `-N CALENDAR_DAY`
- `+N CLASS_DAY` / `-N CLASS_DAY` (skips non-instructional days if configured)
- `HH:MM ABS_TIME` — sets an absolute time of day

## Key source files
| File | Purpose |
|---|---|
| `mikesgradingtool/Canvas/CanvasHelper.py` | All Canvas API interaction; `fn_canvas_calculate_all_due_dates` sets due dates; `get_canvas_course` finds a course by regex |
| `mikesgradingtool/utils/config_json.py` | Config loading (`GradingToolConfig`, `get_app_config`), key lookup with inheritance (`getKey`, `get_path`), `LazyCaseInsensitiveWrapper` |
| `mikesgradingtool/__main__.py` | CLI entry point and argument parsing |
| `mikes_config/config.json` | Working copy of the config (symlinked to `~/.config/mikesgradingtool/`) |

## Standalone scripts (project root)
### `extract_canvas_assignments.py`
Reads all assignments, quizzes, and discussion topics from a Canvas course and
emits a JSON block formatted like `courses/{COURSE}/assignments` in config.json,
with relative due-date chains automatically inferred.

**Usage:**
```bash
python extract_canvas_assignments.py --course 142
python extract_canvas_assignments.py --course 142 --output new_assignments.json
```

**Anchor chain strategy (for course 142):**
- "Hybrid Participation Week N" assignments are the weekly anchors.
- The Midterm replaces Week 6 (no "HP Week 6" exists); the Final replaces Week 11.
- Anchors are chained: HP Week 1 → `FIRST_CLASS_OF_QUARTER`, each subsequent
  anchor → previous anchor + actual calendar-day difference from Canvas dates.
- Non-anchor items attach to their week's anchor via:
  1. "Week N" in the item name
  2. Same ISO calendar week as an anchor's due date
  3. Most-recent anchor before the item's due date (fallback)
- Existing config keys (matched by `canvas_name`) are reused so short keys like
  `"C1"`, `"a1"`, `"Week_01_Forum"` survive across runs.
- Items with no due date get `NO_DUE_DATE` entries at the bottom.

### `find_btt_links.py`
Finds links to BuildingTechTogether resources within a Canvas course.

## Inheritance
Courses can inherit from other courses with `"inherits_from": "base_course"`.
`LazyCaseInsensitiveWrapper.get_path()` walks up the inheritance chain when a
key is not found in the current course.

## Canvas API notes
- `course.get_assignments()` returns all gradable items, including graded quizzes
  (`is_quiz_assignment=True`) and graded discussions (`submission_types=['discussion_topic']`).
- `course.get_quizzes()` and `course.get_discussion_topics()` are used only to
  catch ungraded items that don't appear in `get_assignments()`.
- Course lookup is cached in a `diskcache` store (11-week TTL) keyed by the
  `sz_re_course` regex to avoid repeated full-course-list scans.
