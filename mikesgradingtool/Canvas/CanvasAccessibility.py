import re

from mikesgradingtool.utils.config_json import get_app_config
from mikesgradingtool.Canvas.CanvasHelper import get_canvas_course
from mikesgradingtool.utils.print_utils import printError

# TODO:
#   * What are those redirect URL things?
#
#   We do NOT scan:
#   * Replies to Announcements
#   * Outcomes
def fn_fix_accessibility(args):
    course_id = args.COURSE
    dest_dir = args.DEST

    quarter = args.QUARTER
    verbose = args.VERBOSE

    config = get_app_config()

    canvas_course, canvas = get_canvas_course(course_id, verbose)
    if canvas_course is None:
        return

    if verbose:
        print("== ALL FILES ===========================================================")
    files = canvas_course.get_files()

    all_files_dict = {}
    files_in_use_dict = {}

    for file in files:
        all_files_dict[int(file.id)] = file
    print()

    sorted_files = [all_files_dict[key] for key in sorted(all_files_dict.keys())]

    for file in sorted_files:
        print(str(file.folder_id) + ":" + str(file.id) + "  " + file.display_name)

    course_settings = canvas_course.get_settings()
    if 'image_id' in course_settings and course_settings['image_id']:
        add_to_files_in_use(all_files_dict, files_in_use_dict, course_settings['image_id'])
    if 'image_url' in course_settings and course_settings['image_url']:
        gather_used_files(all_files_dict, files_in_use_dict, course_settings['image_url'], verbose)
    if 'banner_image_id' in course_settings and course_settings['banner_image_id']:
        add_to_files_in_use(all_files_dict, files_in_use_dict, course_settings['banner_image_id'])
    if 'banner_image_url' in course_settings and course_settings['banner_image_url']:
        gather_used_files(all_files_dict, files_in_use_dict, course_settings['banner_image_url'], verbose)

    gather_used_files(all_files_dict, files_in_use_dict, canvas_course.syllabus_body, verbose)

    if verbose:
        print("\n== ANNOUNCEMENTS =======================================================")
    announcements = canvas_course.get_discussion_topics(only_announcements=True)
    for announcement in announcements:
        if verbose:
            print(f"Announcement: {announcement.title}")

        gather_used_files(all_files_dict, files_in_use_dict, announcement.message, verbose)

        # Get all replies to the announcement
        entries = announcement.get_topic_entries()
        for entry in entries:
            if verbose:
                print(f"  Message: {entry.message}\n")

            gather_used_files(all_files_dict, files_in_use_dict, entry.message, verbose)

            # todo: get replies

    if verbose:
        print("\n== ASSIGNMENTS =======================================================")
    assignments = canvas_course.get_assignments()
    for assignment in assignments:
        if verbose:
            print(f"Assignment: {assignment.name}")
        gather_used_files(all_files_dict, files_in_use_dict, assignment.description, verbose)

    if verbose:
        print("\n== DISCUSSIONS =======================================================")
    discussions = canvas_course.get_discussion_topics()
    for discussion in discussions:
        if verbose:
            print(f"Discussion: {discussion.title}")
        gather_used_files(all_files_dict, files_in_use_dict, discussion.message, verbose)

        entries = discussion.get_topic_entries()
        for entry in entries:
            # print(f"Post by: {entry.user_id}")
            gather_used_files(all_files_dict, files_in_use_dict, entry.message, verbose)

            if hasattr(entry, 'recent_replies'):
                for reply in entry.recent_replies:
                    gather_used_files(all_files_dict, files_in_use_dict, reply['message'], verbose)

    if verbose:
        print("\n== MODULES =======================================================")
    modules = canvas_course.get_modules()
    for module in modules:
        if verbose:
            print(f"Module: {module.name}")

        items = module.get_module_items()
        for item in items:
            if verbose:
                print(f"  ID: {item.id} TYPE: {item.type} ITEM: {item.title}")
            # Acc. to https://canvas.instructure.com/doc/api/modules.html#ModuleItem
            #   // the type of object referred to one of 'File', 'Page', 'Discussion',
            #   // 'Assignment', 'Quiz', 'SubHeader', 'ExternalUrl', 'ExternalTool'
            if item.type == 'File':
                add_to_files_in_use(all_files_dict, files_in_use_dict, item.content_id)
            elif item.type == 'ExternalUrl':
                gather_used_files(all_files_dict, files_in_use_dict, item.external_url, verbose)
            elif item.type == 'ExternalTool':
                gather_used_files(all_files_dict, files_in_use_dict, item.external_url, verbose)

    if verbose:
        print("\n== PAGES ===========================================================")
    pages = canvas_course.get_pages()
    for page in pages:
        full_page = canvas_course.get_page(page.url)  # Get the full page using its URL
        if verbose:
            print(f"Title: {full_page.title}")
        gather_used_files(all_files_dict, files_in_use_dict, full_page.body, verbose)

    if verbose:
        print("\n== QUIZZES ==========================================================")
    quizzes = canvas_course.get_quizzes()
    for quiz in quizzes:
        if verbose:
            print(f"Quiz: {quiz.title}")
        gather_used_files(all_files_dict, files_in_use_dict, quiz.description, verbose)

    print("\n== UNUSED FILES: ===========================================================")
    unused_sorted_files = sorted(list(all_files_dict.items() - files_in_use_dict.items()))
    for file_tuple in unused_sorted_files:
        file = file_tuple[1]
        print(str(file.folder_id) + ":" + str(file.id) + "  " + file.display_name)

    print(f"\nTotal number of files: {len(all_files_dict)}")
    print(f"Number of Unused files: {len(unused_sorted_files)}")

def gather_used_files(all_files_dict, files_in_use_dict, text_to_search, verbose: bool):
    #pattern = re.compile(r'<img[^>]+src="[^"]+/files/(\d+)/preview', re.DOTALL)
    pattern = re.compile(r'"https://cascadia.instructure.com/courses/[^"]+/files/(\d+)', re.DOTALL)

    matches = re.findall(pattern, text_to_search)
    for match in matches:
        if int(match) not in all_files_dict:
            if verbose:
                printError(f"Did not find file with id #{match}")
            continue

        file = add_to_files_in_use(all_files_dict, files_in_use_dict, match)

        if verbose:
            print(f"\t{file.id}: {file.display_name}")

def add_to_files_in_use(all_files_dict, files_in_use_dict, file_id_str):
    file_id_int = int(file_id_str)

    file = all_files_dict[file_id_int]
    files_in_use_dict[file_id_int] = file

    return file