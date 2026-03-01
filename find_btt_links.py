#!/usr/bin/env python3
"""
Scan a Canvas LMS course for all links pointing to https://third-bit.com/btt/
Searches through Assignments and Pages, printing:
  - The Canvas URL where the link lives
  - The link text
  - The target URL (under https://third-bit.com/btt/)
"""

import argparse
from collections import defaultdict
import json
import re
import sys
from html.parser import HTMLParser

import canvasapi


TARGET_PREFIX = "https://third-bit.com/btt/"

# ---------- config helpers ----------


def load_config():
    import os

    config_path = os.path.expanduser("~/.config/mikesgradingtool/config.json")
    with open(config_path) as f:
        # Strip JS-style // comments before parsing
        lines = f.readlines()
        cleaned = []
        for line in lines:
            line_original = line

            # Remove // comments that aren't inside strings
            line = (
                re.sub(
                    r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')|//.*',
                    lambda m: m.group(1) or "",
                    line,
                )
                + "\n"
            )
            if line.strip():
                cleaned.append(line)

        config_data = "".join(cleaned)
        return json.loads(config_data)


def get_canvas_connection(config):
    canvas_cfg = config["canvas"]
    api_url = canvas_cfg["api"]["url"]
    api_key = canvas_cfg["api"]["key"]
    return canvasapi.Canvas(api_url, api_key), api_url.rstrip("/")


# ---------- HTML link extractor ----------


class LinkExtractor(HTMLParser):
    """Pull out <a href="...">text</a> pairs where href starts with TARGET_PREFIX."""

    def __init__(self):
        super().__init__()
        self.results = []  # list of (href, link_text)
        self._current_href = None
        self._current_text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href.startswith(TARGET_PREFIX):
                self._current_href = href
                self._current_text_parts = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._current_text_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current_href is not None:
            text = "".join(self._current_text_parts).strip()
            self.results.append((self._current_href, text))
            self._current_href = None
            self._current_text_parts = []


def strip_html(html):
    """Return plain text from an HTML fragment."""
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, data):
            self.parts.append(data)
    p = TextExtractor()
    p.feed(html)
    return "".join(p.parts).strip()


def extract_btt_links(html):
    """Return list of (href, link_text, line_text) for links to third-bit.com/btt/."""
    if not html:
        return []
    parser = LinkExtractor()
    parser.feed(html)

    # For each match, find the surrounding HTML line and extract its plain text
    results_with_context = []
    for href, link_text in parser.results:
        # Find the HTML line containing this link
        line_text = ""
        for html_line in html.splitlines():
            if href in html_line:
                line_text = strip_html(html_line)
                break
        results_with_context.append((href, link_text, line_text))

    return results_with_context


# ---------- BTT table of contents ----------

BTT_CHAPTERS = [
    ("intro/", "Introduction"),
    ("important/", "The Important Stuff"),
    ("starting/", "Starting"),
    ("teams/", "Teams"),
    ("conflict/", "Managing Conflict"),
    ("git-solo/", "Using Git On Your Own"),
    ("git-team/", "Using Git Together"),
    ("ip/", "Intellectual Property"),
    ("communicate/", "Communicating"),
    ("testing/", "Testing"),
    ("design/", "Software Design"),
    ("security/", "Security"),
    ("errors/", "Error Handling"),
    ("debugging/", "Debugging"),
    ("automation/", "Automation"),
    ("tooling/", "Tooling"),
    ("process/", "Process"),
    ("research/", "Research"),
    ("fairness/", "Fair Play"),
    ("delivery/", "Wrapping Up"),
    ("finale/", "Conclusion"),
]

BTT_APPENDICES = [
    ("thinking/", "Thinking"),
    ("methods/", "Research Methods"),
    ("onboarding/", "Onboarding Checklist"),
    ("eval-project/", "Project Evaluation"),
    ("eval-personal/", "Personal Evaluation"),
    ("reading/", "Recommended Reading"),
    ("rules-persuade/", "How to Talk People Into Things"),
    ("rules-comfortable/", "How to Make Yourself Comfortable"),
    ("rules-joining/", "How to Join an Existing Project"),
    ("rules-newcomers/", "How to Welcome Newcomers"),
    ("rules-research/", "How to be a Good Research Partner"),
    ("rules-fired/", "How to Handle Being Fired"),
    ("rules-handover/", "How to Hand Over and Move On"),
    ("rules-freelance/", "How to Get Started Freelancing"),
    ("rules-change/", "How to Change the World"),
    ("license/", "License"),
    ("conduct/", "Code of Conduct"),
    ("contrib/", "Contributing"),
    ("bib/", "Bibliography"),
    ("glossary/", "Glossary"),
    ("colophon/", "Colophon"),
    ("contents/", "Index"),
]


def _build_canvas_li(canvas_url, item_type, item_name, base_url):
    """Build an <li> for a Canvas assignment/page reference."""
    # Derive data attributes from the URL
    # e.g. https://cascadia.instructure.com/courses/123/assignments/456
    course_type = "assignments" if item_type == "Assignment" else "pages"
    api_returntype = "Assignment" if item_type == "Assignment" else "Page"
    api_endpoint = canvas_url.replace(base_url, base_url + "/api/v1")
    return (
        f'                                        <li>'
        f'<a title="{item_name}" href="{canvas_url}" '
        f'data-course-type="{course_type}" '
        f'data-api-endpoint="{api_endpoint}" '
        f'data-api-returntype="{api_returntype}">'
        f'{item_name}</a></li>\n'
    )


def _build_toc_html(toc_list, by_target, base_url):
    """Build <ol> HTML for one TOC list (chapters or appendices)."""
    html = '                                <li style="list-style-type: none;">\n'
    html += '                            <ol class="toc-chapters">\n'

    for slug, title in toc_list:
        full_url = TARGET_PREFIX + slug
        refs = by_target.get(full_url, [])

        if refs:
            # Deduplicate by (canvas_url, item_name) and sort by item_name
            seen = set()
            unique_refs = []
            for ref in refs:
                key = (ref[0], ref[2])  # (canvas_url, item_name)
                if key not in seen:
                    seen.add(key)
                    unique_refs.append(ref)
            unique_refs.sort(key=lambda r: r[2])  # sort by item_name

            html += (
                f'                                <li><strong>'
                f'<a href="{full_url}">{title}</a></strong>\n'
            )
            html += '                                    <ul class="toc-chapters" style="list-style-type: disc;">\n'
            for canvas_url, item_type, item_name, _link_text, _line_text in unique_refs:
                html += _build_canvas_li(canvas_url, item_type, item_name, base_url)
            html += '                                    </ul>\n'
            html += '                                </li>\n'
        else:
            html += (
                f'                                <li><a href="{full_url}">'
                f'{title}</a></li>\n'
            )

    html += '                            </ol>\n'
    html += '                        </li>\n'
    return html


def generate_html(by_target, base_url, course_name):
    """Generate find_btt_matches.html showing BTT TOC with Canvas references."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>BTT Links in {course_name}</title>
</head>
<body>
    <h1>BTT Links in {course_name}</h1>
    <table>
        <tr>
            <td style="vertical-align: top;">
                <h2>Chapters</h2>
                <ol>
{_build_toc_html(BTT_CHAPTERS, by_target, base_url)}
                </ol>
            </td>
            <td style="vertical-align: top;">
                <h2>Appendices</h2>
                <ol>
{_build_toc_html(BTT_APPENDICES, by_target, base_url)}
                </ol>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    with open("find_btt_matches.html", "w") as f:
        f.write(html)
    print("Results written to find_btt_matches.html")


# ---------- main scanning logic ----------


def scan_course(course, base_url):
    course_id = course.id
    found = []

    # --- Assignments ---
    print("Scanning assignments...", flush=True)
    assignments = course.get_assignments()
    for assignment in assignments:
        links = extract_btt_links(assignment.description)
        if links:
            page_url = f"{base_url}/courses/{course_id}/assignments/{assignment.id}"
            for href, link_text, line_text in links:
                found.append((href, page_url, "Assignment", assignment.name, link_text, line_text))
                print(f'  Found in assignment "{assignment.name}"')

    # --- Pages ---
    print("Scanning pages...", flush=True)
    SKIP_PAGE_URLS = {"building-tech-together-checklist-2"}
    pages = course.get_pages()
    for page in pages:
        if page.url in SKIP_PAGE_URLS:
            continue
        full_page = course.get_page(page.url)
        links = extract_btt_links(full_page.body)
        if links:
            page_url = f"{base_url}/courses/{course_id}/pages/{page.url}"
            for href, link_text, line_text in links:
                found.append((href, page_url, "Page", full_page.title, link_text, line_text))
                print(f'  Found in page "{full_page.title}"')

    return found


def pick_course(canvas, pattern):
    """Find a course whose name matches the given regex pattern."""
    user = canvasapi.current_user.CurrentUser(canvas._Canvas__requester)
    courses = user.get_courses(
        enrollment_type="teacher",
        state=["unpublished", "available"],
    )
    matches = []
    for course in courses:
        if hasattr(course, "name"):
            print(f"Checking course: {course.name}")
            if re.search(pattern, course.name):
                matches.append(course)

    if not matches:
        print(f"No courses matched the pattern: {pattern}", file=sys.stderr)
        sys.exit(1)

    if len(matches) == 1:
        return matches[0]

    print("Multiple courses matched — please pick one:")
    for i, c in enumerate(matches, 1):
        print(f"  {i}. {c.name}  (id={c.id})")
    while True:
        choice = input("Enter number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]
        print("Invalid choice, try again.")


# ---------- entry point ----------


def main():
    parser = argparse.ArgumentParser(
        description="Find all links to https://third-bit.com/btt/ in a Canvas course"
    )
    parser.add_argument(
        "course_pattern",
        help="Regex pattern to match the Canvas course name (e.g. 'BIT 142.*Winter')",
    )
    args = parser.parse_args()

    config = load_config()
    canvas, base_url = get_canvas_connection(config)

    course = pick_course(canvas, args.course_pattern)
    print(f"\nScanning course: {course.name}\n")

    results = scan_course(course, base_url)

    # Group by target URL
    by_target = defaultdict(list)
    for target_url, canvas_url, item_type, item_name, link_text, line_text in results:
        by_target[target_url].append((canvas_url, item_type, item_name, link_text, line_text))

    print(f"\n{'='*80}")
    print(f"Found {len(results)} link(s) to {TARGET_PREFIX}")
    print(f"across {len(by_target)} distinct target URL(s)\n")

    with open("find_btt_matches.txt", "w") as out:
        out.write(f"Found {len(results)} link(s) to {TARGET_PREFIX}\n")
        out.write(f"across {len(by_target)} distinct target URL(s)\n\n")

        for target_url in sorted(by_target):
            header = f"{target_url}"
            print(header)
            out.write(f"{header}\n")
            for canvas_url, item_type, item_name, link_text, line_text in by_target[target_url]:
                item_line = f"  {item_type}: {item_name}  ({canvas_url})"
                link_line = f"\tLink text: {link_text}"
                ctx_line = f"\tLine text: {line_text}"
                print(item_line)
                print(link_line)
                print(ctx_line)
                out.write(f"{item_line}\n")
                out.write(f"{link_line}\n")
                out.write(f"{ctx_line}\n")
            print()
            out.write("\n")

    print("Results written to find_btt_matches.txt")

    # Generate HTML output
    generate_html(by_target, base_url, course.name)


if __name__ == "__main__":
    main()
