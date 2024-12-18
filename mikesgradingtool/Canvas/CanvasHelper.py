#  Need:
#       getListOfFeedbackFiles
#           - downloaded from Canvas
#           - need to be uploaded manually
#       getListOfStudentSubmissionDirs
#
#       Organize submissions into dirs
#
import calendar
import csv
from dataclasses import dataclass
import datetime
import functools
import os
import pprint
import pytz
import re
import shutil
import string
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import namedtuple
from concurrent.futures import as_completed, ThreadPoolExecutor
from typing import Callable

import canvasapi as canvasapi
import canvasapi.exceptions
from canvasapi.assignment import Assignment
from canvasapi.submission import Submission
from canvasapi.user import User

from colorama import Fore, Style, Back
from jinja2 import UndefinedError, StrictUndefined, Environment
# import win32com.client
from rich import box
from rich.console import Console
from rich.table import Table

from mikesgradingtool.utils.diskcache_utils import get_app_cache
from mikesgradingtool.utils.misc_utils import grade_list_collector
from mikesgradingtool.MiscFiles import MiscFilesHelper
from mikesgradingtool.utils.config_json import get_app_config, lookupHWInfoFromAlias
from mikesgradingtool.utils.misc_utils import cd, format_filename, is_file_locked, lock_file, print_threadsafe
from mikesgradingtool.utils.my_logging import get_logger
from mikesgradingtool.utils.print_utils import GradingToolError, print_list, printError

# cache expiration in seconds - 11 weeks
APP_CACHE_EXPIRATION = 60*60*24*7*11

#console = Console(color_system="truecolor", tab_size=4)
console = Console(color_system="auto", tab_size=4)
# list of colors: https://rich.readthedocs.io/en/latest/appendix/colors.html?highlight=list%20colors

pp = pprint.PrettyPrinter(indent=8)

logger = get_logger(__name__)


def _ignore_file_file(fp_file):
    config = get_app_config()
    new_feedbacks_dir, zip_to_reupload = config.verify_keys([
        "canvas/NewDirForMissingFeedbackFiles",
        "canvas/ZipFileToUploadToCanvas",
    ])

    if new_feedbacks_dir in fp_file \
        or zip_to_reupload in fp_file:
        return True
    else:
        return False


def _getSubmissionFolders(fp_dir):
    config = get_app_config()
    student_submission_dir_suffix = config.verify_keys([
        "canvas/StudentSubFolderMarker"
    ])

    student_subs = {_filename_to_student_key(f[:-len(student_submission_dir_suffix)]):f for f in os.listdir(fp_dir)
                    if student_submission_dir_suffix in f
                    and f.endswith(student_submission_dir_suffix)
                    and os.path.isdir(os.path.join(fp_dir, f))
                    and not MiscFilesHelper.ignore_this_file(os.path.join(fp_dir, f))
                    and not _ignore_file_file(os.path.join(fp_dir, f))}
    return student_subs


def _filename_to_student_key(file):
    config = get_app_config()
    sz_re_studentname_key, sz_late_marker = config.verify_keys([
        "canvas/StudentName",
        "canvas/LateMarker"
    ])
    re_studentname_key = re.compile("^" + sz_re_studentname_key)

    keys = re_studentname_key.findall(file)

    if len(keys) == 0:  # item does not match
        printError(f"Given file/dir to match, but it doesn't: {file}")
        return

    if len(keys) > 1:
        printError("Filename contained multiple student names (???):\n\t" + file)

    key = keys[0]
    key = key.replace(sz_late_marker, "")
    # remove dots
    key = key.replace(".", "")
    if key.endswith('_'):
        key = key[:-1]

    return key


def _extract_student_name_from_file(file):
    return file.split('_')[0]


def _extract_name_and_sid_from_file(file):
    config = get_app_config()
    sz_late_marker = config.verify_keys([
        "canvas/LateMarker"
    ])

    parts = file.split('_')
    retval = parts[0] + "_"
    if sz_late_marker in file:
        retval += parts[2]
    else:
        retval += parts[1]

    return retval

# Returns a compiled regex to identify the feedback file
# (NOT the "has it already been copied" marker file, but the feedback file itself)
# Canvas-only Examples:
#   Fierro_Valeria_5994539_225545272_INSTRUCTORFEEDBACK.docx
#   Fierro-Dax_Valeria_5994539_225545272_INSTRUCTORFEEDBACK.docx
#   Fierro_Valeria_5994539_225545272_Instructor_Feedback.docx
#   Fierro_Valeria_5994539_225545272_INSTRUCTORFEEDBACK-1.docx
#   (Fierro)_Valeria_5994539_225545272_INSTRUCTORFEEDBACK.docx
#
# "All feedbacks" examples:
#   Ezgin_Mirac_INSTRUCTORFEEDBACK.docx // this one was created by gt
#   (All the same ones listed in _getFeedbackFileRegex())
def _getFeedbackFileRegex(canvas_only=False):
    config = get_app_config()
    sz_re_studentName, \
        sz_re_studentname_id_filenum, \
        sz_re_feedback_file, \
        sz_re_sub_num, \
        sz_re_file_ext = config.verify_keys([
        "canvas/StudentName",
        "canvas/StudentNameIDFileNum",
        "canvas/InstructorFeedbackFileNameRegex",
        "canvas/OptionalFileSubmissionNumber",
        "canvas/FileExtension"
    ])

    sz_re_student = sz_re_studentname_id_filenum if canvas_only else sz_re_studentName + ".*"

    sz_re = sz_re_student + sz_re_feedback_file + sz_re_sub_num + sz_re_file_ext
    re_obj = re.compile(sz_re , re.IGNORECASE)
    return re_obj

def _getStudentFeedbackFiles(rootDir, only_canvas=True):
    submissions = dict()

    re_search_for = _getFeedbackFileRegex(canvas_only=only_canvas)

    for root, dirs, files in os.walk(rootDir):
        # ignore 'junk' files in the backup dir:
        if MiscFilesHelper.ignore_this_file(root) or _ignore_file_file(root):
            continue

        files = sorted(files)

        for file in files:
            # ignore GradingTool/canvas lock files:
            if MiscFilesHelper.ignore_this_file(file) or _ignore_file_file(root):
                continue

            if re_search_for.search(file):

                fp_new_real_item = os.path.join(root, file)

                key = _filename_to_student_key(file)

                if key in submissions:
                    print(
                        Fore.YELLOW + Style.BRIGHT + "Found multiple feedback files for student " + key + Style.RESET_ALL + " keeping " + os.path.basename(
                            fp_new_real_item))

                submissions[key] = fp_new_real_item
    return submissions

def fn_canvas_autograde(args):
    raise GradingToolError("This feature hasn't been updated, and thus won't work reliably")

    # config = get_app_config()
    # student_submission_dir_suffix = config.verify_keys([
    #     "canvas/StudentSubFolderMarker"])
    # def fn_canvas_convert_dir_to_student_sub(assign_desc, dir, now):
    #     return StudentSubmission(   str(dir),  # path to sub
    #                                 dir.name[:-len(student_submission_dir_suffix)],  # student's "last name"
    #                                 "-",  # leave first name blank since we don't have first/last name info
    #                                 assign_desc['feedback_title'],  # assignment name,
    #                                 now)
    # config = get_app_config()
    # student_submission_dir_suffix = config.verify_keys([
    #     "canvas/StudentSubFolderMarker"])
    # sz_glob_student_dir = "*"+student_submission_dir_suffix
    #
    # autograder_common_actions(args, sz_glob_student_dir, fn_canvas_organize_files, fn_canvas_convert_dir_to_student_sub)

# def get_canvas_course_and_assignment(course_name, hw_name, verbose):
#     the_course, canvas = get_canvas_course(course_name, verbose)
#     if the_course is None:
#         return None, None
#
#     the_assignment = get_canvas_assignment(course_name, hw_name, the_course, verbose)
#
#     return the_course, the_assignment


def get_canvas_assignment(course_json_abbrev, hw_name, the_course, verbose, print_error_if_not_found:bool = True):
    config = get_app_config()

    the_assignment = None
    assignment_name = config.getKey(
        f"courses/{course_json_abbrev}/assignments/{hw_name}/canvas_api/canvas_name", "")
    if assignment_name != "":
        persistent_app_cache = get_app_cache(verbose)
        assign_cache_key = f"{the_course.id}:{assignment_name}"

        if assign_cache_key in persistent_app_cache:
            assign_id = persistent_app_cache.get(assign_cache_key)

            assign = the_course.get_assignment(assign_id)
            if assign.name == assignment_name:
                the_assignment = assign
                if verbose:
                    print(f"= Found cached Canvas ID for assignment {assign_id} (aka \"{assign.name}\")")

        # If we didn't find a cached, valid match then go (re)find the Canvas ID for this assignment
        if the_assignment is None:
            print("\tSearching for the assignment, within the course")
            for assign in the_course.get_assignments():
                if assign.name == assignment_name:
                    the_assignment = assign
                    persistent_app_cache.set(assign_cache_key, the_assignment.id, expire=APP_CACHE_EXPIRATION)
                    break
    if print_error_if_not_found and the_assignment is None:
        printError(f"Couldn't find assignment matching {hw_name} in {course_json_abbrev}")
    return the_assignment


def parse_datetime_with_or_without_time(sz):
    parsed_datetime = None
    if sz is not None:
        try:
            parsed_datetime = datetime.datetime.strptime(sz, "%Y-%m-%d-%H-%M")
        except:
            try:
                general_due_date_info = get_general_due_date_info_defaults()
                if general_due_date_info == None:
                    return

                parsed_datetime = datetime.datetime.strptime(sz, "%Y-%m-%d")
                parsed_datetime = datetime.datetime.combine(parsed_datetime.date(), \
                                                            general_due_date_info['assignment_default_due_time'])
            except:
                pass

    if parsed_datetime is not None:
        config = get_app_config()
        zoneName = config.getKey(f"app-wide_config/preferred_time_zone", "")
        if zoneName == "":
            printError(f"Could not find app-wide_config/preferred_time_zone in gradingTool.json")
            return
        local_time_zone = pytz.timezone(zoneName)
        parsed_datetime = local_time_zone.localize(parsed_datetime)

    return parsed_datetime

def fn_canvas_set_assignment_due_date(args):
    print(f"Changing assignment due date to {args.DUE_DATE}")

    verbose = args.VERBOSE

    if args.DUE_DATE == 'x':
        due_date = ''
        msg_success = f"Removing the assignment's due date"
    else:
        due_date = parse_datetime_with_or_without_time(args.DUE_DATE)
        if due_date is None:
            raise GradingToolError(f"Couldn't convert this to  datetime using YYYY-MM-DD or YYYY-MM-DD-HH-MM formats: {args.DUE_DATE}")
        due_date = due_date.isoformat()
        msg_success = f"Set the assignment's due date to {due_date}"

    assignment = {'due_at': due_date}

    edit_course(args.ALIAS_OR_COURSE, args.HOMEWORK_NAME, verbose, assignment, msg_success)


# Doesn't work, so I'm removing it from the UI.  Temporarily, hopefully
# The issue is that 'hide_in_gradebook' doesn't work.  Setting it to false doesn't make the assignment visible
# and setting it to true provokes an error message from Canvas saying that
# "Hide in gradebook must be equal to false, Hide in gradebook is not included in the list"
# It's not clear what the list is
def fn_canvas_post_assignment_grades(args):
    verbose = args.VERBOSE

    hide = args.HIDE
    if hide:
        print(f"Hiding grades (in the gradebook) for an assignment")
        msg_success = f"HIDDEN: Assignment grades are NOT visible to the students in the Canvas gradebook"
    else:
        print(f"Showing grades (in the gradebook) for an assignment")
        msg_success = f"SHOWN: Assignment grades ARE visible to the students in the Canvas gradebook"

    assignment = {'hide_in_gradebook': hide} # didn't work
    #assignment = {'muted': hide} # Also didn't work

    edit_course(args.ALIAS_OR_COURSE, args.HOMEWORK_NAME, verbose, assignment, msg_success)

def fn_canvas_lock_assignment(args):
    verbose = args.VERBOSE
    lock = args.UNLOCK

    config = get_app_config()
    # TODO: Remove the following
    zoneName = config.getKey(f"app-wide_config/preferred_time_zone", "")
    if zoneName == "":
        printError(f"Could not find app-wide_config/preferred_time_zone in gradingTool.json")
        return
    local_time_zone = pytz.timezone(zoneName)

    if lock:
        print("Locking assignment")
        # Calculate the time 30 minutes before the current time for the locking time
        # This will effectively lock it now, and it's early enough that there's no risk of clocks being off slightly
        lock_at = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30))
        lock_at = lock_at.isoformat()

        msg_success = f"Locked the assignment (starting 30 mintues ago, at {lock_at})"
    else:
        print("Unlocking assignment")
        lock_at = ''
        msg_success = f"Unlocked the assignment"

    assignment = {'lock_at': lock_at}

    edit_course(args.ALIAS_OR_COURSE, args.HOMEWORK_NAME, verbose, assignment, msg_success)

def edit_course(alias_or_course, homework_name, verbose, dict_assignment_edits, msg_success):
    config = get_app_config()
    api_url = config.verify_keys([
        "canvas/api/url"
    ])

    hw_info = lookupHWInfoFromAlias(alias_or_course)
    if hw_info is not None:
        course_name = hw_info.course
        hw_name = hw_info.hw
    else:
        course_name = alias_or_course
        hw_name = homework_name

#    canvas_course, canvas_assignment = get_canvas_course_and_assignment(course_name, hw_name, verbose)
    canvas_course, canvas = get_canvas_course(course_name, verbose)
    if canvas_course is None:
        return
    canvas_assignment = get_canvas_assignment(course_name, hw_name, canvas_course, verbose)
    if canvas_assignment is None:
        return

    print(f"\tFound \"{canvas_assignment.name}\" in \"{canvas_course.name}\"")

    try:
        result = canvas_assignment.edit(assignment=dict_assignment_edits)
        print(msg_success)

    except canvasapi.exceptions.CanvasException as ce:
        printError("Couldn't post to Canvas: " + ce.message)

    print(f"Assignment URL: {api_url}courses/{canvas_course.id}/assignments/{canvas_assignment.id}")

def fn_canvas_new_announcement(args):
    config = get_app_config()

    verbose = args.VERBOSE
    template_name = args.TEMPLATE

    hw_info = lookupHWInfoFromAlias(args.ALIAS_OR_COURSE)
    if hw_info is None:
        if template_name == "":
            raise GradingToolError(f"Couldn't find an alias for {args.ALIAS_OR_COURSE} so we're assuming that's the course name, and no template was specified, so we don't know what to Announce for this course")
        else:
            print(f"Couldn't find an alias for {args.ALIAS_OR_COURSE}, using {args.ALIAS_OR_COURSE} as the course")
            course_name = args.ALIAS_OR_COURSE
    else: # found hw_info
        course_name = hw_info.course

        if args.TEMPLATE == "": # prefer CLI args over the default
            template_name = config.getKey(f"courses/{course_name}/assignments/{hw_info.hw}/default_announcement_template", "")
            if template_name == "":
                raise GradingToolError("No template specified for this assignment: Couldn't find a default_announcement_template key in gradingtool.json, nor a command line paramater")

    print(f"Posting new announcement for course {course_name} using template {template_name}")

    optional_date = parse_datetime_with_or_without_time(args.DATE)

    # Get the file path to the templates (both title and message/body)
    api_url, course_obj, fp_title_template, fp_message_template, due_date_info = config.verify_keys([
        "canvas/api/url",
        f"courses/{course_name}",
        f"courses/{course_name}/announcement_templates/title_{template_name}",
        f"courses/{course_name}/announcement_templates/message_{template_name}",
        f"due_date_info"
    ])
    assign_obj = None
    if hw_info is not None:
        assign_obj = config.getKey(f"courses/{course_name}/assignments/{hw_info.hw}", "")


    def read_template_file(path: str, title_or_msg: str):
        try:
            # Open the text file in read mode
            with open(path, 'r') as file:
                # Read the entire contents of the file into a variable
                return file.read()
        except FileNotFoundError:
            printError(f"Couldn't find the {title_or_msg} file at {path}")
        except PermissionError:
            printError(f"Permission denied for the {title_or_msg} file at {path}")
        except IOError as e:
            printError(f"When attempting to read the {title_or_msg} file at {path}, an I/O error occurred:", e)

        # if we couldn't get the template:
        return None

    sz_title_template =  read_template_file(fp_title_template, "title")
    sz_message_template = read_template_file(fp_message_template, "title")

    # Create a Jinja Template object
    # Create a Jinja2 Environment with strict undefined behavior
    env = Environment(undefined=StrictUndefined)

    # Create a Jinja Template object
    title_template = env.from_string(sz_title_template)

    message_template = env.from_string(sz_message_template)

    print("Searching for the course in Canvas:")
    the_course, canvas = get_canvas_course(course_name, verbose)
    if the_course is None:
        return

    # Define data to pass into the template
    data = {
        'assignment': assign_obj,
        'course': course_obj,
        'due_date_info': due_date_info
    }

    if optional_date:
        data['date'] = optional_date

    if hw_info:
        # We may need the Canvas ID of the Assignment (if we want to link to it)
        # so try to get it now

        next_assignment = get_canvas_assignment(course_name, hw_info.next_version, the_course, verbose, \
                                                print_error_if_not_found=False)

        if next_assignment is not None:
            next_assignment_url = f"{api_url}courses/{the_course.id}/assignments/{next_assignment.id}"
            data['next_assignment_url'] = next_assignment_url

    try:
        # Render the template with the data
        title_rendered = title_template.render(data)
        message_rendered = message_template.render(data)
    except UndefinedError as ue:
        printError(f"The template used a variable that wasn't defined: {ue.message}")
        print("data:")
        pp.pprint(data)
        raise GradingToolError(f"The template used a variable that wasn't defined: {ue.message}")

    try:
        result = the_course.create_discussion_topic(title=title_rendered, message=message_rendered, is_announcement=True)
        # result is a DiscussionTopic object, if we want to change it for some reason
        print(f"Posted announcement to Canvas at\n\t{api_url}courses/{result.course_id}/discussion_topics/{result.id}")
    except canvasapi.exceptions.CanvasException as ce:
        printError("Couldn't post to Canvas: " + ce.message)
        # Base exception class: canvasapi.exceptions.CanvasException
        # https://canvasapi.readthedocs.io/en/stable/exceptions.html



def fn_canvas_organize_files(args):
    raise GradingToolError("This feature hasn't been updated, and thus won't work reliably")

    # fp_dir_or_zip: str = args.SRC
    # fp_dest_for_zip: str = args.DEST
    #
    # zip_real_dest = None
    #
    # with tempfile.TemporaryDirectory() as zip_temp_dir:
    #
    #     if os.path.exists(fp_dir_or_zip) \
    #         and os.path.isfile(fp_dir_or_zip) \
    #         and zipfile.is_zipfile(fp_dir_or_zip):
    #
    #         if fp_dest_for_zip is not None:
    #             fp_dir_to_organize = fp_dest_for_zip
    #         else:
    #             fp_dir_to_organize = os.path.join(os.path.dirname(fp_dir_or_zip))
    #
    #         with zipfile.ZipFile(fp_dir_or_zip, 'r') as zip_ref:
    #             zip_ref.extractall(zip_temp_dir)
    #             zip_real_dest = fp_dir_to_organize
    #             fp_dir_to_organize = zip_temp_dir
    #
    #     elif os.path.exists(fp_dir_or_zip) \
    #         and os.path.isdir(fp_dir_or_zip) :
    #         fp_dir_to_organize = fp_dir_or_zip
    #     elif fp_dir_or_zip is None:
    #         # use the current directory
    #         fp_dir_to_organize = os.path.abspath(os.getcwd())
    #     else:
    #         raise GradingToolError("First param must be .ZIP to extract and organize or a directory to organize or missing (to use the current dir)  Instead, it's: \n\t"+ fp_dir_or_zip)
    #
    #     config = get_app_config()
    #     feedbackFileRegex, sz_re_user_name, sz_re_file_sub_num, Student_Submission_Dir_Suffix= config.verify_keys([
    #         "canvas/InstructorFeedbackFileNameRegex",
    #         "canvas/StudentNameIDFileNum",
    #         "canvas/FileSubmissionNumber",
    #         "canvas/StudentSubFolderMarker"
    #     ])
    #
    #     re_FEEDBACK = re.compile(feedbackFileRegex, re.IGNORECASE)
    #
    #     # RegEx for stripping the name off the front of a Canvas-submitted file:
    #     re_username = re.compile(sz_re_user_name)
    #     re_extra_numbers_at_end_of_filename = re.compile(sz_re_file_sub_num)  # to match e.g., "-1.cs" in "Program-1.cs"
    #
    #     with cd(fp_dir_to_organize):
    #
    #         # get a list of students from the files (possibly in subdirs) that look like they're from Canvas:
    #         all_files = sorted(Path().rglob("*"))
    #         students = [_filename_to_student_key(f.name) for f in all_files if re_username.match(f.name)]
    #         students = list(set(students))
    #         students.sort()
    #
    #         canvas_files = [f for f in os.listdir(fp_dir_to_organize)
    #                         if re_username.match(f)
    #                         and os.path.isfile(os.path.join(fp_dir_to_organize, f))]
    #
    #         #     # blank line for appearance:
    #         print()
    #
    #         for student in students:
    #             student_short = _extract_student_name_from_file(student)
    #             print(f"Next student: {(student_short + ' ').ljust(25, '=')} ")
    #
    #             studentDir = os.path.join(fp_dir_to_organize, student + Student_Submission_Dir_Suffix)
    #
    #             os.makedirs(studentDir, exist_ok=True)
    #
    #             filesToMove = [f for f in canvas_files if student == _extract_name_and_sid_from_file(f)]
    #
    #             #     # Next, remove the mangled names from everything that we're NOT planning on re-uploading:
    #             #     # At this point we're only planning on uploading the INSTRUCTORFEEDBACK files:
    #             #     # Also move them straight over if we find a file that doesn't match the Canvas name-mangling
    #             #     # (but did contain their name?  This is mostly for error handling, just in case)
    #             for file in filesToMove:
    #                 new_file = re_username.sub("", file, count=1)
    #                 new_file = re_extra_numbers_at_end_of_filename.sub("\g<1>", new_file, count=1)
    #
    #                 if re_FEEDBACK.search(file) or file == new_file:
    #                     print("\tMoving: ".ljust(46) + file)
    #                     shutil.move(file, studentDir)
    #                 else:
    #                     print(f"\tMoving: {new_file}".ljust(45) + f" (from {file})")
    #                     dest_file = os.path.join(studentDir, new_file)
    #                     shutil.move(file, dest_file)
    #
    #         dict_student_subs = _getSubmissionFolders(fp_dir_to_organize)
    #
    #         print(f"\n{len(dict_student_subs)} student submissions organized")
    #
    #     # Only copy when dst doesn't exist OR when src is newer than the dst:
    #     def copy_non_existant_files(src, dst, my_follow_symlinks=True):
    #         if not os.path.exists(dst):
    #             fp = shutil.copy(src, dst, follow_symlinks=my_follow_symlinks)
    #             return
    #
    #     if zip_real_dest is not None:
    #         shutil.copytree(fp_dir_to_organize, zip_real_dest,
    #                     copy_function=copy_non_existant_files,
    #                     dirs_exist_ok=True)
    #         # we don't need to rmtree b/c it's in a context-managed temp dir

def fn_canvas_download_revision_template(args):
    # print("\nDownload the assignment THEN copy revision feedback (if any) THEN copy the grading template\n")

    hw_info = lookupHWInfoFromAlias(args.alias)
    if hw_info is None:
        printError(f"Couldn't find an alias for {args.alias}")
        sys.exit(-1)

    # download:
    args.COURSE = args.alias
    args.QUARTER = None

    fn_canvas_download_homework(args)
    print() # spacer line, for aesthetics

    if hw_info.fp_dest_dir == '':
        printError("No destination dir listed in gradingTool.json. We can't copy feedback templates.")
        sys.exit(-1)

    if hw_info.fp_template == '':
        printError("No feedback template file listed in gradingTool.json. We can't copy feedback templates.")
        sys.exit(-1)

    print("Done downloading assignments; Start copying prior version feedback into this one ".ljust(150, "=") )

    # revision:
    if hw_info.prior_version == '':
        print(f"\nAssignment {hw_info.hw} in {hw_info.course} does not have a prior version ")
        print(f"\tSkipping the \"Copy initial version's feedback into the current version\" step")
    else:
        args.SRC = args.alias
        fn_canvas_copy_feedback_to_revision(args)

    print() # for aesthetics

    print("Done copying prior version feedback; Start copying template into anything without feedback yet ".ljust(150, "=") )

    # template:
    args.template_file = args.alias
    fn_canvas_copy_template(args)


def fn_canvas_copy_template(args):
    print(f"\nCopying template over student feedback files ".ljust(100, '=') + "\n")

    hw_info = lookupHWInfoFromAlias(args.template_file)
    if hw_info is not None:
        args.template_file = hw_info.fp_template
        args.SRC = hw_info.fp_dest_dir

    if not os.path.exists(args.SRC):
        printError("Destination folder does not exist: " + args.SRC)
        sys.exit(-1);

    if not os.path.exists(args.template_file):
        printError("Template file does not exist: " + args.template_file)
        sys.exit(-1);

    fp_CopyTemplateToHere: str = args.SRC
    fpTemplate = args.template_file
    template_file_ext = os.path.splitext(fpTemplate)[1]
    config = get_app_config()
    sz_new_dir_for_feedbacks, sz_feedback_file_slug = config.verify_keys([
        "canvas/NewDirForMissingFeedbackFiles",
        "canvas/InstructorFeedbackSlug"
    ])

    print("Template file:\n\t" + fpTemplate + "\n")

    dictFeedbacks = _getStudentFeedbackFiles(fp_CopyTemplateToHere, only_canvas=True)
    if len(dictFeedbacks) > 0:
        print("The following students included feedback files in their Canvas submissions\n\tReplacing them with the grading template/rubric\n")
        c_student_included, c_copied_included = MiscFilesHelper.copy_template_to_path_list(fpTemplate, list(dictFeedbacks.values()))
    else:
        print(Fore.YELLOW + "None of the students included feedback files in their Canvas submissions" + Style.RESET_ALL)
        c_student_included, c_copied_included = 0, 0

    print()

    dict_of_sub_folders = _getSubmissionFolders(fp_CopyTemplateToHere)

    #students in both:
    students_with_feedback = dictFeedbacks.keys() & dict_of_sub_folders.keys()

    # remove students from 'sub folders' list
    students_without_canvas_feedback_files = {k: v for k, v in dict_of_sub_folders.items() if k not in students_with_feedback}

    # whoever's left must have not handed in a revision
    # hand that list off to copy_template_to_path_list
    # first massage the list into a list of new files to create:
    new_feedbacks = [os.path.join(fp_CopyTemplateToHere,  students_without_canvas_feedback_files[s],
                                  _extract_name_and_sid_from_file(s) + sz_feedback_file_slug + template_file_ext)
                     for s in students_without_canvas_feedback_files.keys()]

    if len(new_feedbacks) > 0:
        print("The following students " + Fore.YELLOW + "DID NOT" + Fore.RESET +
              f" include feedback files in their Canvas submissions\n\tPlacing rubrics into each student's submission folder\n" + Style.RESET_ALL)
        c_student_missing, c_copied_missing = MiscFilesHelper.copy_template_to_path_list(fpTemplate, new_feedbacks)
    else:
        print("All of the students included feedback files in their Canvas submissions" + Style.RESET_ALL)
        c_student_missing, c_copied_missing = 0, 0

    print(f"\nFound a total of {c_student_missing + c_student_included} feedback files\n\tCopied the template into {c_copied_missing + c_copied_included} of those files")


def fn_canvas_copy_feedback_to_revision(args):

    hw_info = lookupHWInfoFromAlias(os.path.basename(args.SRC))
    if hw_info is not None:
        if hw_info.prior_version == None:
            printError(f"There is no prior version for {hw_info.hw} in {hw_info.course}")
            return

        config = get_app_config()

        src = config.getKey(f"courses/{hw_info.course}/assignments/{hw_info.prior_version}/dest_dir", '')
        src = config.ensureDestDirHasSuffix(hw_info.course, src)
        dest = config.ensureDestDirHasSuffix(hw_info.course, hw_info.fp_dest_dir)
    else:
        src = args.SRC
        dest = args.DEST

    print("\nCopying feedback files ".ljust(100, '=') + "\n\tFrom:" + src + "\n\tTo:" + dest)

    if not os.path.exists(src):
        printError("Source folder does not exist: " + src )
        sys.exit(-1);

    if not os.path.exists(dest):
        printError("Destination folder does not exist: " + dest )
        sys.exit(-1);

    config = get_app_config()
    sz_feedback_file_slug, canvas_student_subfolder_marker = config.verify_keys([
        "canvas/InstructorFeedbackSlug",
        "canvas/StudentSubFolderMarker"
    ])

    # When we're using the Canvas API the dest dir is already organized
    # So we're going to skip all this
    # This would be a good step if we get the work from a manually downloaded .ZIP file
    # # first clean up the destination dir
    # # if we forget to do this then the lock files won't work
    # # after this is finished AND THEN we call canvas-organize
    # print("\nFirst organizing the destination: " + dest)
    # args.SRC = dest
    # fn_canvas_organize_files(args)
    # print()

    # Step #1: Go through the 'originals' directory
    # & build up a dictionary of student names & their original feedback files
    logger.info("Collecting original feedbacks")

    originals = _getStudentFeedbackFiles(src, only_canvas=False)

    # Get a list of the revised submissions
    #    (DO rearrange them nicely)
    logger.info("Collecting feedback files in the newly uploaded revisions")
    new_subs_feedback_files = _getStudentFeedbackFiles(dest, only_canvas=False)

    new_submissions = _getSubmissionFolders(dest)

    # get list of people who have original feedback but lack an existing feedback file in their new submissions
    # this commonly happens when they don't include a feedback file in either submission but we create
    # one for them in the original version
    new_submissions_without_feedback_files = list( set(new_submissions) - set(new_subs_feedback_files))

    for new_sub_no_feedback in new_submissions_without_feedback_files:
        if new_sub_no_feedback in originals:
            template_file_ext = os.path.splitext(originals[new_sub_no_feedback])[1]
            existing_folder_name = os.path.basename(os.path.dirname(originals[new_sub_no_feedback]))
            new_subs_feedback_files[new_sub_no_feedback] =  os.path.join(dest,  existing_folder_name,
                                                                         new_sub_no_feedback + sz_feedback_file_slug + template_file_ext)

    missing_original = dict()  # new submissions that don't have a matching original dir
    no_revision_submitted = originals.copy()  # original submissions that don't have a matching new dir

    print("\nCopying original feedbacks over revision files for the following students:")
    for new_sub in sorted(new_subs_feedback_files):
        logger.debug("NEW SUBMISSION from: " + new_sub)

        if new_sub not in originals:
            missing_original[new_sub] = new_subs_feedback_files[new_sub]
            continue

        # since we've seen the original we should remove it from our list of no-revisions:
        del no_revision_submitted[new_sub]

        origFeedback = originals[new_sub]
        newFeedback = new_subs_feedback_files[new_sub]

        try:
            if is_file_locked(newFeedback):
                print(("* {0:<55}Feedback NOT copied (it was previously copied and we're not overwriting it)".format(
                    new_sub) + Style.RESET_ALL))
                continue

            lock_file(newFeedback)
            shutil.copy2(origFeedback, newFeedback)
            print(("* {0:<55}\n\tOrig file: {1}\n\tOrig Loc:{2}".format(
                new_sub, os.path.basename(origFeedback), os.path.dirname(os.path.relpath(origFeedback))) + Style.RESET_ALL))
        except:
            printError("\t\tUnable to create a lock file and/or copy the file for " + os.path.basename(newFeedback))

    # if len(no_revision_submitted) > 0:
    #     print(
    #         Fore.YELLOW + Style.BRIGHT + "\nThe following people did not submit a revision (but had submmitted something for the original upload):" + Style.RESET_ALL)
    #     for no_rev in no_revision_submitted:
    #         print("  {0:<20}".format(no_rev))

    if len(no_revision_submitted) > 0:
        print(
            Fore.YELLOW + Style.BRIGHT + "\nThe following people did not submit a revision (but had submmitted something for the original upload):" + Style.RESET_ALL)
        for no_rev in no_revision_submitted:
            print("  {0:<20}".format(no_rev))

    if len(missing_original) > 0:
        print(
            Fore.RED + Style.BRIGHT + "\nThe following people DID submit a revision, but did NOT have an original file:" + Style.RESET_ALL)
        for no_orig in missing_original:
            print("  {0:<20} did not have an original version!".format(no_orig))

    # print 'Finished copying feedback to revision directory'
    print("\n(" + str(len(new_subs_feedback_files)) + " feedback files were found)")


# go through all the feedback files
# Ones that can be re-uploaded to Canvas should be put into a .ZIP
# Those that can't go into a directory for ease-of-manual-uploading
def fn_canvas_package_feedback_for_upload(args):
    fp_dir_to_package: str = args.SRC

    if not os.path.exists(fp_dir_to_package):
        printError("Source folder does not exist: " + fp_dir_to_package )
        sys.exit(-1);

    config = get_app_config()
    dir_for_new_feedbacks, zip_file_name = config.verify_keys([
        "canvas/NewDirForMissingFeedbackFiles",
        "canvas/ZipFileToUploadToCanvas"
    ])
    re_canvas_feedback_file = _getFeedbackFileRegex(canvas_only=True)
    students_who_didnt_upload_feedback_files_directly_to_canvas = list()

    with cd(fp_dir_to_package):

        dictFeedbacks = _getStudentFeedbackFiles(fp_dir_to_package, only_canvas=False)

        # create empty _NEW dir
        fp_new_feedbacks_dir = os.path.join(fp_dir_to_package, dir_for_new_feedbacks)
        os.makedirs(fp_new_feedbacks_dir, exist_ok=True)

        # create new .ZIP file for re-upload:
        # https://docs.python.org/3/library/zipfile.html#module-zipfile
        new_zip_file = os.path.join(fp_dir_to_package, zip_file_name)

        with zipfile.ZipFile(new_zip_file, mode='w', compression=zipfile.ZIP_DEFLATED) as canvas_reupload:

            for student, feedback_file in dictFeedbacks.items():
                # if it looks like a canvas file then add to zip
                # TODO Tacking the underscore back onto the end is such a hack :(
                filename = os.path.basename(feedback_file)
                if re_canvas_feedback_file.search(filename):
                    print(f"Student: {student}")
                    print(f"\tAdding to .ZIP file for bulk re-upload")
                    canvas_reupload.write(feedback_file, arcname=filename)
                else:
                    # if it does NOT look like a canvas file then add to _NEW
                    print(Fore.YELLOW +f"Student: {student}" + Style.RESET_ALL)
                    print( f"\tMoving to 'new feedbacks' dir for manual upload")
                    dest = os.path.join(fp_new_feedbacks_dir, filename)
                    shutil.copy2(feedback_file, dest)

                    students_who_didnt_upload_feedback_files_directly_to_canvas.append(student)

                print(f"\t{feedback_file}\n")

        if len(students_who_didnt_upload_feedback_files_directly_to_canvas) > 0:
            print(Fore.RED + f"\nDon't forget to manually upload the {len(students_who_didnt_upload_feedback_files_directly_to_canvas)} brand-new feedback files:" + Style.RESET_ALL)
            for student in students_who_didnt_upload_feedback_files_directly_to_canvas:
                print(f"\t{student}")
            print(f"\nNew feedbacks are found in:\n\tNew Dir: {fp_new_feedbacks_dir}")
        else:
            print(Fore.GREEN + "\nThere were zero new feedback files; all the feedback files are in the new .ZIP file"+ Style.RESET_ALL)
            os.rmdir(fp_new_feedbacks_dir)

        print(f"\nFinished Packaging files:\n\tNew Zip: {new_zip_file}\n")


def fn_canvas_upload_feedback_via_CAPI(args):
    config = get_app_config()

    hw_info = lookupHWInfoFromAlias(args.ALIAS)
    if hw_info is not None:
        course = hw_info.course
        hw_name = hw_info.hw
        dest_dir = hw_info.fp_dest_dir
    else:
        printError(f"Couldn't find alias matching {args.ALIAS}")
        sys.exit(-1);

    # only_student_to_upload will be None or the abs path to the directory to uplaod
    only_student_to_upload = args.DEST

    verbose = args.VERBOSE

    if not os.path.exists(dest_dir):
        printError("Homework folder does not exist: " + dest_dir )
        sys.exit(-1);

    hw_full_name = config.getKey(f"courses/{course}/assignments/{hw_name}/full_name")

    if not confirm_choice("Do you want to upload feedback for this course?", hw_full_name, \
                   "Uploading homework feedback files to Canvas", \
                   "Operation canceled - NO FILES UPLOADED"):
        return

    with cd(dest_dir):

        dictFeedbacks = _getStudentFeedbackFiles(dest_dir, only_canvas=False)

        def upload_feedback(sub: Submission, user: User, assign: Assignment,
                              dest_dir:str, results_lists: grade_list_collector):

            # print(f"uploading for {user.name} (ID={user.id})")
            if only_student_to_upload is not None \
                and not dest_dir.startswith(only_student_to_upload):
                # skipping non-target student
                return

            the_feedback = list(filter(lambda fp_feedback: fp_feedback.startswith(dest_dir), dictFeedbacks.values()))

            # No feedback for this student:
            if len(the_feedback) == 0:
                results_lists.no_submission.append(dest_dir)
                return

            # Too many feedbacks for this student - list as an error for the user to handle:
            if len(the_feedback) > 1:
                results_lists.ungraded.append(dest_dir)
                return

            fp_feedback_to_upload = the_feedback[0]
            result = sub.upload_comment(fp_feedback_to_upload)
            if result[0] == True: # upload succeeded
                results_lists.graded.append(fp_feedback_to_upload)
            else:
                results_lists.new_student_work_since_grading.append(fp_feedback_to_upload)

        if dest_dir is  None:
            dest_dir = config.getKey(f"courses/{course}/assignments/{hw_name}/dest_dir")

        # Confirm that the program hasn't hung for verbose and concise mode:
        print(f"\nAttempting to upload feedback for assignment \"{hw_name}\" for \"{course}\"")
        if only_student_to_upload is not None:
            print(f"\n\tOnly uploading {only_student_to_upload.replace(dest_dir + os.path.sep, '')}")

        # Data fields have weird names because we're reusing the data structure from another use case :)
        results_lists = grade_list_collector()
        results_lists.verbose = verbose

        quarter = None
        do_fnx_per_matching_submission(course, quarter, hw_name, dest_dir, results_lists, upload_feedback, \
                                       "Uploading student feedbacks to Canvas")

        if verbose:
            print("\n\n" + "=" * 20 + "\n")

        print_list(dest_dir, sorted(list(set(results_lists.no_submission)), key=str.casefold), \
               Fore.RED, "The following students did not have feedback to upload", \
               verbose=verbose)

        print_list(dest_dir, sorted(list(set(results_lists.ungraded)), key=str.casefold), \
               Fore.CYAN,"The following students have more than 1 feedback file - please figure out which one(s) to upload", \
               verbose=verbose)

        print_list(dest_dir, sorted(list(set(results_lists.graded)), key=str.casefold), \
               Fore.GREEN,"Successfully uploaded feedback for the following students", \
               verbose=verbose)

        print_list(dest_dir, sorted(list(set(results_lists.new_student_work_since_grading)), key=str.casefold), \
               Fore.CYAN,"The following students' feedback files caused an error", \
               verbose=verbose)

    print(f"Uploaded feedback from:\t{dest_dir}")


def course_key_name(course):
    return course.name

def course_has_start_at_date(course):
    return ( (hasattr(course, 'start_at') and course.start_at) \
            or \
            (hasattr(course, 'term') and course.term['start_at']))

def course_start_date(course):
    if hasattr(course, 'start_at') and course.start_at:
        course_date = course.start_at
    if hasattr(course, 'term') and course.term['start_at']:
        course_date = course.term['start_at']
    return course_date;

def course_key_timestamp(course):
    dt = datetime.datetime.fromisoformat(course_start_date(course).replace("Z", ""))
    return dt.timestamp()

   # Two scenarios that lead to duplicate courses matching:
    #  1. Teaching multiple sections in this quarter
    #  2. Teaching the same course next quarter (or last quarter) and this quarter
    #current_courses = d = {pattern: list() for pattern in courses_to_look_for}

def is_current_course(course_maybe):
    if (not hasattr(course_maybe, 'concluded') or not course_maybe['concluded']) \
            and hasattr(course_maybe, 'name')  \
            and course_has_start_at_date(course_maybe):

        starting_date = datetime.datetime.fromisoformat(course_start_date(course_maybe).replace("Z", ""))
        now = datetime.datetime.fromisoformat(datetime.datetime.now().isoformat())
        if starting_date < now:
            return True
        else:
            # print("Found a course, but it hasn't started yet: " + course_maybe['name'])
            return False

    return False

########################################################################################################################
####  Everything below here used to be in the 'Canvas_API_Helper.py' file ##############################################
########################################################################################################################

# The files were merged to avoid a circular dependency problem (and PyInstaller had problems with importlib.loadmodule)

def name_to_last_first( shortname: str):
    parts = shortname.split()

    # Turns out, students can change this to be a single word
    if len(parts) == 1:
        return parts[0]

    # # Otherwise, assume there's two names and reverse them
    # # TODO: What if the student has a different number of names? (More than 2?)
    # return parts[1].lower() + parts[0].lower()
    capped = string.capwords(shortname)
    firstname = capped.split()[0].strip()
    lastname = capped.split()[-1].strip()
    return lastname + "_" + firstname


# The concurrent, multithreaded download code was copied from:
# https://rednafi.github.io/digressions/python/2020/04/21/python-concurrent-futures.html#download--save-files-from-urls-with-multi-threading
# Code was then tweaked
def download_one(info, verbose):
    # ""
    # Downloads the specified URL and saves it to disk
    # ""
    url, fp_dest, version_num = info
    req = urllib.request.urlopen(url)
    # fullpath = Path(url)
    # fname = fullpath.name
    # ext = fullpath.suffix

    # if not ext:
    #     raise RuntimeError("URL does not contain an extension")

    with open(fp_dest, "wb") as handle:
        while True:
            chunk = req.read(1024)
            if not chunk:
                break
            handle.write(chunk)

    msg = f"\t\tVer #{version_num}\t{os.path.basename(fp_dest)}"
    if verbose:
        print_threadsafe( msg )
    return msg


def download_all(urls, verbose):
    # ""
    # Create a thread pool and download specified urls
    # ""

    futures_list = []
    results = []

    with ThreadPoolExecutor(max_workers=50) as executor:
        for url in urls:
            futures = executor.submit(download_one, url, verbose)
            futures_list.append(futures)

        for x in as_completed(futures_list):
#            print(x.result())
            results.append(x)

        # for future in futures_list:
        #     try:
        #         result = future.result(timeout=60)
        #         print( "download all: " + result )
        #         results.append(result)
        #     except Exception:
        #         results.append(None)
    return results
#End of copied code


# The goal of this had been to specify something like "BIT 115" and then
# figure out which of the many matches were for the current quarter's class.
# As of 2023 Fall it looks like Canvas isn't reporting the start/end dates for the class anymore :(
# So the user must specify a matching RegEx in the gradingTool.json file
# and this will return the one match for the course
def get_canvas_course(course_name: str, verbose, sz_re_quarter: str = ".*"):
    config = get_app_config()
    api_url, api_key, sz_re_course = config.verify_keys([
        "canvas/api/url",
        "canvas/api/key",
        f"courses/{course_name}/canvas_api/sz_re_course"
    ])

    # Initialize a new Canvas object
    canvas = canvasapi.Canvas(api_url, api_key)
    try:
        curuser = canvasapi.current_user.CurrentUser(canvas._Canvas__requester)
    except:
        printError("Unable to connect to the Canvas server - are we offline?")
        sys.exit(-1)

    matching_course = None
    persistent_app_cache = get_app_cache(verbose)

    if sz_re_course in persistent_app_cache:
        course_id= persistent_app_cache.get(sz_re_course)
        course = canvas.get_course(course_id, include=['term', 'syllabus_body'])

        # Verify that we actually have the correct course
        # (i.e., we're not in a new term with a re-used course name)
        if hasattr(course, 'name') \
            and re.search(sz_re_course, course.name) \
            and re.search(sz_re_quarter, course.name):

            matching_course = course
            if verbose:
                print(f"= Found cached Canvas ID for course {course_id} (aka \"{course.name}\")")

    # If we didn't find a cached, valid match then go (re)find the Canvas ID for this course:
    if matching_course is None:
        if verbose:
            print(f"= Getting information from Canvas:")
            print("\tSearching for target course in the list of all courses")

        # Get CanvasAPI.PaginatedList, which will lazy-load individual courses:
        courses = curuser.get_courses(enrollment_type='teacher',
                                           state=['unpublished', 'available'],
                                           include=['term', 'syllabus_body'])  # 'include': ['term', 'concluded']

        for course in courses:
            if hasattr(course, 'name') \
                    and re.search(sz_re_course, course.name) \
                    and re.search(sz_re_quarter, course.name):
                if verbose:
                    print("\tFound \"" + course.name + "\", whose named matched the pattern " + sz_re_course)
                matching_course = course
                break

        if matching_course is None:
            printError("No matching course names for the pattern\n\t" + sz_re_course)
            print("REMINDER: Remember to escape your parentheses with a backslash in the JSON config file, like so: \\\\(")
            print("SUGGESTION: Try an online Python RegEx tester to make sure that your pattern matches!")
        else:
            persistent_app_cache.set(sz_re_course, matching_course.id, expire=APP_CACHE_EXPIRATION)

    return matching_course, canvas

foundMatchingAssignment = False

def do_fnx_per_matching_submission(course_name, sz_re_quarter, hw_name, dest_dir_from_cmd_line:str,
                                   results_lists: grade_list_collector,
                                   fnx: Callable[[Submission, User, Assignment, str, grade_list_collector],None],
                                   msg_to_display = "Downloading student submissions from Canvas"):

    if sz_re_quarter is None:
        sz_re_quarter = ".*"

    dir_required = dest_dir_from_cmd_line != "NO_DIR_NEEDED"

    config = get_app_config()

    course, canvas = get_canvas_course(course_name, results_lists.verbose, sz_re_quarter)
    if course is None:
        return

    if results_lists.verbose:
        print(f"\tGetting Users for \"{course.name}\"")

    users_lookup = dict()
    users = course.get_users(enrollment_type=['student'])
    for user in users:
        users_lookup[user.id] = user

    assignment_name = config.getKey(f"courses/{course_name}/assignments/{hw_name}/canvas_api/canvas_name")

    if results_lists.verbose:
        print(f"\tGetting Assignments for \"{course.name}\"")

    # Get all assignments:
    assignments = course.get_assignments()
    assign_lookup = dict()

    for assign in assignments:
        assign_lookup[assign.id] = assign

        if assign.name != assignment_name:
            continue

        global foundMatchingAssignment
        foundMatchingAssignment = True  # We've found it, although there may be zero submissions/uploads to download

        # This used to work, but now Canvas sometimes reports a false negative :(
        # if not assign.has_submitted_submissions:
        #     # Error message printed elsewhere
        #     return

        if results_lists.verbose:
            print(f"\tGetting Submissions for \"{assign.name}\"")
        else: # don't indent, and show more info (pretty much the only info we'll show here in concise mode)
            print(f"Getting Submissions for \"{assign.name}\" in \"{course.name}\"")
        dest_dir = None
        if dir_required:
            if hw_name != 'all' and dest_dir_from_cmd_line is not None:
                dest_dir = dest_dir_from_cmd_line
            else:
                dest_dir = config.getKey(f"courses/{course_name}/assignments/{hw_name}/dest_dir")

        if assign.group_category_id is None:
            if results_lists.verbose:
                print("\tThis is NOT a group assignment")
        else:
            try:
                group_category = canvas.get_group_category(assign.group_category_id)
                if results_lists.verbose:
                    print(f"\tThis assignment is a group assignment, using group \"{group_category.name}\"")

                for group in group_category.get_groups():
                    # print(f"\tGroup: {group.name}")

                    # Reset the 'Group Members' file
                    safe_name = format_filename(group.name)
                    group_dest_dir = os.path.join(dest_dir, safe_name)
                    os.makedirs(group_dest_dir, exist_ok=True)
                    with open(os.path.join(group_dest_dir, "GROUP_MEMBERS.txt"), "w", encoding="utf-8") as myfile:
                        pass

                    for user in group.get_users():
                        obj_user = users_lookup[user.id]
                        # print(f"\t\t{obj_user.name}")
                        users_lookup[user.id].attributes["group"] = group
            except canvasapi.exceptions.ResourceDoesNotExist as e:
                printError(f"*** This assignment is a group assignment, but the group-set that was used can't be found (was it deleted after students handed in work?)***")

        # https://canvasapi.readthedocs.io/en/latest/assignment-ref.html#canvasapi.assignment.Assignment.get_submissions
        submissions = assign.get_submissions(include=["submission_history"])

        stop_early = 2

        global foundSubmissions
        foundSubmissions = False

        for sub in submissions:
            # print("\nNEXT SUBMISSION: ==================================================")
            if foundSubmissions == False:
                if results_lists.verbose:
                    print(f"\n= {msg_to_display}:")
                    print(" ")  # blank, spacer line

            foundSubmissions = True

            if sub.user_id not in users_lookup:

                # Concise mode: only print info when it looks like there was something submitted
                if results_lists.verbose or \
                        (not results_lists.verbose and (not sub.missing or \
                        sub.workflow_state != "unsubmitted" \
                        or sub.submitted_at is not None)):
                    print(f"\tUnknown user id ({sub.user_id}) - skipping submission ".ljust(60, "-"))
                    if obj_user is not None:
                        print(f"\t\tobj_user.name: \"{obj_user.name}\"")
                    print(f"\t\tworkflow_state: \"{sub.workflow_state}\" | Missing? {sub.missing} | submitted_at: {sub.submitted_at}")

                # Regardless, we don't have user info, so go on to the next student
                continue

            obj_user = users_lookup[sub.user_id]
            capped = string.capwords(obj_user.name)
            firstname = capped.split()[0].strip()
            lastname = capped.split()[-1].strip()

            # Students are allowed to put in nicknames, which show up at the end of the string:
            # "Smith, Robert (Bob)"
            if len(lastname) > 2 and lastname[0] == '(' and lastname[-1] == ')':
                lastname = capped.split()[-2].strip()

            # Repair the user object so that anything else looking for first & last names
            # will get the correct strings:
            obj_user.name = obj_user.short_name = firstname + ' ' + lastname
            obj_user.sortable_name = lastname + ', ' + firstname

            group = None
            if hasattr(obj_user, 'attributes') and 'group' in obj_user.attributes and obj_user.attributes["group"] is not None:
                group = obj_user.attributes['group']

            if results_lists.verbose:
                if group is None:
                    print(f"\t{lastname}, {firstname} ".ljust(60, "-") )
                else:
                    print(f"\t{group.name} == ({lastname}, {firstname}) ".ljust(60, "-"))

            # Is Canvas telling us about an empty "submission" (i.e., student didn't hand in any work)?
            if sub.missing or sub.submitted_at is None:
                # len(sub.submission_history) == 1 and "submitted_at" not in sub.submission_history[0]:
                if results_lists.verbose:
                    print("\t\tNo work uploaded")

                results_lists.no_submission.append(f"{lastname}, {firstname}")
                continue

            if sub.assignment_id not in assign_lookup:
                print(f"\t\tUnknown assignment id encountered - skipping submission! ID = {sub.assignment_id}")
                continue

            obj_assign = assign_lookup[sub.assignment_id]

            # If student is part of a group then put in group folder
            if group is not None:
                safe_name = format_filename(group.name)
                sub_dest_dir = os.path.join(dest_dir, safe_name)
                with open(os.path.join(sub_dest_dir,"GROUP_MEMBERS.txt"), "a", encoding="utf-8") as myfile:
                    myfile.write(obj_user.name + "\n")

            # Otherwise, put it into a folder for this particular student
            else:
                # Now add the student's name onto the end
                # Format like the organized .ZIP downloads:
                sub_dest_dir = os.path.join(dest_dir, name_to_last_first(obj_user.name) + '_' + str(obj_user.id) + '_FROM_CANVAS')


            fnx(sub, obj_user, obj_assign, sub_dest_dir, results_lists)

            # break # uncomment to stop after a downloading a single student
            #
            # # uncomment to stop after stop_early students
            # if stop_early  <= 1: break
            # stop_early = stop_early - 1

def fn_canvas_download_homework(args):

    hw_info = lookupHWInfoFromAlias(args.COURSE)
    if hw_info is not None:
        course = hw_info.course
        hw_name = hw_info.hw
        dest_dir = hw_info.fp_dest_dir
    else:
        course = args.COURSE  # formerly COURSE
        hw_name = args.HOMEWORK_NAME
        dest_dir = args.DEST

    quarter = args.QUARTER
    verbose = args.VERBOSE

    global foundMatchingAssignment
    foundMatchingAssignment = False # reset

    global foundSubmissions # False if assign exists, but no student subs yet
    foundSubmissions = False # reset

    new_student_projects = list()
    updated_student_projects = list()
    unchanged_student_projects = list()

    def download_homework(sub: Submission, user: User, assign: Assignment,
                          dest_dir:str, results_lists: grade_list_collector, canvas = None):

        sz_re_feedback_file = config.verify_keys([
            "canvas/InstructorFeedbackFileNameRegex"])
        re_FEEDBACK = re.compile(sz_re_feedback_file, re.IGNORECASE)

        attached_file_info = namedtuple('attached_file_info', 'attempt_num sub fp_dest modified_at')

        fp_versions_file = os.path.join(dest_dir, "CANVAS_FILE_VERSIONS.csv")

        # If there's a dir for the homework already AND it contains
        # a versions.csv file then read through it for version info
        files_original = dict()
        if os.path.isfile(fp_versions_file):
            with open(fp_versions_file, mode='r', encoding="utf-8") as inp:
                reader = csv.reader(inp)
                files_original = {rows[1]: attached_file_info(int(rows[0]), None, rows[2], rows[3]) for rows in reader}

        files = dict()
        for prev_sub in sub.submission_history:

            # Multiple submission for a single assignment:
            if "attachments" in prev_sub \
                    and prev_sub['attachments'] is not None:

                for attach in prev_sub['attachments']:
                    real_name = urllib.parse.unquote_plus(attach["filename"])
                    # if real_name in files:
                    #     print(f"\t\tREPLACING Ver #{str((files[real_name]).attempt_num)} with ver #{str(prev_sub['attempt'])} for {real_name.ljust(30)}")

                    if re_FEEDBACK.search(attach['display_name']):
                        # To recreate the instructor feedback filename gibberish that Canvas normally puts into it's .zip downloads, use:
                        # this will allow us to identify and re-upload these files back to Canvas
                        fp_dest = name_to_last_first(user.name) + '_' + str(user.id) + '_' + str(attach['id']) + '_' + attach['display_name']
                        fp_dest = os.path.join(dest_dir, fp_dest)
                    else:
                        # use nice filenames for everything except the instructor feedback:
                        # we won't be uploading them, but we will want to read the names ourselves
                        fp_dest = os.path.join(dest_dir, real_name)

                    attach_info = attached_file_info(prev_sub['attempt'], attach, fp_dest, attach['modified_at'])
                    files[real_name] = attach_info
            elif "submission_type" in prev_sub \
                    and prev_sub['submission_type'] == 'online_quiz' \
                    and "submission_data" in prev_sub \
                    and prev_sub['submission_data'] is not None:

                if canvas is None:
                    raise GradingToolError("Can't download ")

                for answer in prev_sub['submission_data']:
                    if "attachment_ids" in answer \
                        and answer['attachment_ids'] is not None:
                        for attachment in answer['attachment_ids']:
                            print("attachment ID: " + attachment)

                            # Retrieve the file object
                            file = canvas.get_file(attachment_id)

                            # Specify the local path to save the file
                            file_path = "downloaded_file_name.extension"

                            # Download the file
                            file.download(file_path)

        unchanged_files = dict(filter(lambda file: file[0] in files_original \
                                               and file[1].attempt_num <= files_original[file[0]].attempt_num,
                                  files.items()))

        # Take out the files that haven't changed, leaving only those files we'll need to download new copies of
        files = dict( filter( lambda file: file[0] not in unchanged_files, files.items()))

        if len(files) > 0:
            if verbose:
                print("\t\tDownloading new and/or changed files:")

            os.makedirs(dest_dir, exist_ok=True)

            with open(fp_versions_file, 'w', newline='', encoding="utf-8") as file:
                writer = csv.writer(file)

                if len(unchanged_files) > 0:
                    for file_name, file_info in unchanged_files.items():
                        writer.writerow([str(file_info.attempt_num), file_name, file_info.fp_dest, file_info.modified_at])

                # Set up list of stuff to download in parallel:
                download_info = []

                for file_name, file_info in files.items():
                    # we don't want to overwrite INSTRUCTORFEEDBACK files when updating
                    # a folder of graded work
                    if is_file_locked(file_info.fp_dest):
                        if verbose:
                            print("\t\tFile was already locked for grading; NOT downloading despite finding newer version in Canvas:\n\t\t\t" + os.path.basename(file_info.fp_dest))
                        if file_name in files_original:
                            orig_file_info = files_original[file_name]
                        else:
                            # If we lost the file info then use the most current as a placeholder, I guess
                            orig_file_info = files[file_name]
                        writer.writerow(
                            [str(orig_file_info.attempt_num), file_name, orig_file_info.fp_dest, orig_file_info.modified_at])
                        unchanged_files[file_name] = orig_file_info
                    else:
                        # print(f"\t\tVer #{str(file_info.attempt_num).ljust(4)}{file_name}")
                        writer.writerow([str(file_info.attempt_num), file_name, file_info.fp_dest, file_info[1]['modified_at']])
                        download_info.append( (file_info.sub['url'], file_info.fp_dest, file_info.attempt_num))

                results = download_all(download_info, results_lists.verbose)
                # for result in results:
                #     print(f"\t{result.result()}")

            if len(unchanged_files) > 0 and verbose:
                print("\t\tThe following files were previously downloaded (or locked), and are unchanged:")
                print('\t\t\t' + '\n\t\t\t'.join(f"\"{f}\"" for f in sorted(unchanged_files)))

        # dest_dir looks like "/StudentName", so let's remove the leading /
        dest_dir_to_display = os.path.basename(dest_dir)
        if not files_original:
            # add the download into the list of newly downloaded
            new_student_projects.append(dest_dir_to_display)
        else:

            # since we always accumulate files from all submisisons
            # if the # has increased it's because we found new files:
            if len(files) > 0:
                sz_changed_files = ', '.join(f"\"{f}\"" for f in sorted(files))
                updated_student_projects.append(dest_dir_to_display + " " + sz_changed_files)
            else:
                # Append list of changed files?
                unchanged_student_projects.append(dest_dir_to_display)

    config = get_app_config()

    if dest_dir is  None:
        dest_dir = config.getKey(f"courses/{course}/assignments/{hw_name}/dest_dir")

    dest_dir = config.ensureDestDirHasSuffix(course, dest_dir)

    # If we don't download anything at least the dir will exist
    # (which hints at the problem - no downloadable files)
    os.makedirs(dest_dir, exist_ok=True)

    # Confirm that the program hasn't hung for verbose and concise mode:
    if hw_name == 'all':
        print(f"\nAttempting to download all homework assignments for \"{course}\"")
    else:
        print(f"\nAttempting to download homework assignment \"{hw_name}\" for \"{course}\"")
    # if verbose:
    #     print('\n\n') # blank line

    results_lists = grade_list_collector()
    results_lists.verbose = verbose

    do_fnx_per_matching_submission(course, quarter, hw_name, dest_dir, results_lists, download_homework)

    if hw_name == 'all':
        dest_dir = '' # force output to list complete paths

    if foundMatchingAssignment == False:
        assignment_name = config.getKey(f"courses/{course}/assignments/{hw_name}/canvas_api/canvas_name")
        printError(f"No assignments were found with the name \"{assignment_name}\"")
        return

    if foundSubmissions == False:
        printError(f"There are no submissions in Canvas for {hw_name}")
        return;

    if verbose:
        print("\n" + "=" * 20 + "\n")

    if verbose:
        print_list(dest_dir, sorted(list(set(unchanged_student_projects)), key=str.casefold), \
               Fore.CYAN,"The following Canvas submissions already exist and have NOT been updated by the student since our last download",
               "There were no unchanged student submissions", \
               verbose=verbose)

        print_list(dest_dir, sorted(list(set(results_lists.no_submission)), key=str.casefold), \
               Fore.RED, "The following students did not submit anything", \
               verbose=verbose)

    print_list(dest_dir, sorted(list(set(updated_student_projects)), key=str.casefold), \
               Fore.YELLOW,"The following Canvas submissions already existed but 1+ files have been updated since last downloaded",
               "There were no updated student submissions", \
               verbose=verbose)

    print_list(dest_dir, sorted(list(set(new_student_projects)), key=str.casefold), \
               Fore.GREEN, "The following student submissions are newly downloaded:", \
               "There were no brand new (to us) student submissions", \
               verbose=verbose)

    if hw_name != 'all':
        if len(dest_dir) > 1 \
            and dest_dir[-1:] != os.sep \
            and dest_dir[-1:] != os.altsep:
            dest_dir = dest_dir + os.sep

        print(f"Downloads can be found in:\t{dest_dir}")


def fn_canvas_list_homeworks(args):
    course_name = args.COURSE  # formerly COURSE

    config = get_app_config()

    table = Table(box=box.SIMPLE_HEAVY, collapse_padding=True, show_header=False)

    table.add_column("Course", justify="right")
    table.add_column("Assignment", justify="right")
    table.add_column("CanvasAPI?", justify="center", style="grey35")
    table.add_column("GitHub?", justify="center", style="grey35")

    if course_name == None:
        courses = config.getKey(f"courses")
    else:
        the_course = config.getKey(f"courses/{course_name}")
        courses = { course_name: the_course}


    # / {course} / assignments / {hw_name}
    for course, course_info in courses.items():
        if "assignments" not in course_info: # this must be the 'alias' hive, etc
            continue

        table.add_row(course, "", "", "", style="black on white")

        for assign, assign_info in course_info["assignments"].items():
            szfCanvas = ""
            if "canvas_api" in assign_info and "canvas_name" in assign_info["canvas_api"]:
                szfCanvas = "Canvas"

            szfGitHub = ""
            if "github" in assign_info and "sz_re_repo" in assign_info["github"]:
                szfGitHub = "GitHub"

            table.add_row("", assign, szfCanvas, szfGitHub)

    console = Console()
    console.print(table)


@dataclass(frozen=True)
class AssignmentForDisplay:
    due_at: str
    title: str
    unlock_at: str = None
    lock_at: str = None

    def print(self):
        str_to_print =f"\tDue at: {self.due_at}\t{self.title}"
        if self.unlock_at is not None:
            str_to_print += f"\tUnlock at: {self.unlock_at}"
        if self.lock_at is not None:
            str_to_print += f"\tLock at: {self.lock_at}"

        print(str_to_print)


def cmp_AssignmentForDisplay(a, b):
    # Put missing due dates at the end:
    if a.due_at is None \
       and b.due_at is None :
        return cmp_AssignmentForDisplay_by_name(a,b)
    if a.due_at is None:
        return +1
    if b.due_at is None:
        return -1

    if a.due_at < b.due_at:
        return -1
    elif a.due_at > b.due_at:
        return 1
    else:
        return cmp_AssignmentForDisplay_by_name(a,b)

def cmp_AssignmentForDisplay_by_name(a,b):
    if a.title == b.title:
        return 0
    else:
        return -1 if a.title < b.title else +1


def confirm_choice(szPrompt: str, szTypeThis:str, szMsgProceeding: str, szMsgCancel:str):
    szTypeThis = szTypeThis.strip()

    print("\n"+szPrompt)
    print("\tIf so, please type in")
    print(Style.BRIGHT + Fore.RED + Back.BLACK \
            + szTypeThis \
            + Style.RESET_ALL )
    print("(this is case sensitive), followed by Enter/Return")
    print("Type anything else (or leave it blank) and press Enter/Return to cancel")

    confirm = input("").strip()

    if confirm != szTypeThis:
        print(szMsgCancel)
        return False

    print(Style.BRIGHT + Fore.RED + "\n\n" + szMsgProceeding + "\n" + Style.RESET_ALL)
    return True

## TODO
#
# Add events for non-instructional days (but only if they're not already in the schedule)
#
# Handle times for due dates (right now it's just dates)
#
NO_DUE_DATE_MARKER_STRING = "gradingTool.json specified 'NO_DUE_DATE' for this item"
def fn_canvas_calculate_all_due_dates(args):
    course_name = args.COURSE
    hw_name = args.HOMEWORK_NAME
    verbose = args.VERBOSE
    noop = args.NOOP

    print(f"Calculating due dates for {course_name}")
    if noop:
        print(f"\tNo-op mode: this will NOT make any changes in Canvas (but will still print out the calculated dates)")

    config = get_app_config()

    is_json_course_found = config.getKey(f"courses/{course_name}", "")
    if is_json_course_found == "":
        printError(f"Could not find course info in JSON config file for \"{course_name}\"")
        print(f"\tIs \"{course_name}\"  an alias (like 2a4, or 3i11, etc)?")
        return

    general_due_date_info = get_general_due_date_info_defaults()
    if general_due_date_info == None:
        return

    if args.FIRST_DAY_OF_QUARTER == '':
        if 'date_of_first_day_of_the_quarter' in general_due_date_info \
                and general_due_date_info['date_of_first_day_of_the_quarter'] is not None:
            # this is already a datetime in UTC
            start_of_quarter = general_due_date_info['date_of_first_day_of_the_quarter']
        else:
            printError("First day of class not found in json file, and not specified on the command line")
            return
    else:
        # first day of the quarter was specified as a string on the CLI - convert it here
        try:
            start_of_quarter = datetime.datetime.strptime(args.FIRST_DAY_OF_QUARTER, "%Y-%m-%d")
            start_of_quarter = date_time_from_local_to_utc(start_of_quarter, general_due_date_info['time_zone'])
        except ValueError as ve:
            printError(f'FIRST_DAY_OF_QUARTER parameter needs to be a date in YYYY-MM-DD format.  This is not in that format: {args.FIRST_DAY_OF_QUARTER}')
            return

    # at this point start_of_quarter is a datetime, in UTC

    if 'date_of_last_day_of_the_quarter' in general_due_date_info \
            and general_due_date_info['date_of_last_day_of_the_quarter'] is not None:
        # this is already a datetime in UTC
        end_of_quarter = general_due_date_info['date_of_last_day_of_the_quarter']
    else:
        printError("Last day of class not found in json file")
        return

    due_date_info_for_course = config.getKey(f"courses/{course_name}/due_date_info", "")
    if due_date_info_for_course == "":
        printError(f"Could not find course-wide due date info for {course_name}")
        return
    due_date_info_for_course = set_course_due_date_info_defaults(due_date_info_for_course)

    valid_day_abbrevs = list(calendar.day_abbr)

    due_date_not_found = False
    for due_date in due_date_info_for_course["days_of_week"]:
        if due_date not in valid_day_abbrevs:
            printError(f"Did not find {due_date} in list of valid day abbreviations")
            due_date_not_found = True

    if due_date_not_found:
        print(f"Found this info in gradingTool.json/courses/{course_name}/due_date_info/days_of_week")
        print("Valid day abberviations are: " + str(valid_day_abbrevs))
        sys.exit(-1)

    course_info = config.getKey(f"courses/{course_name}", "")
    if course_info == "":
        printError(f"Could not find {course_name}")
        return

    if hw_name != "":
        hw_info = config.getKey(f"courses/{course_name}/assignments/{hw_name}", "")
        if hw_info == "":
            printError(f"Could not find the assignment {hw_name} within the course {course_name}")
            return
        course_info["assignments"] = {
            hw_name : hw_info
        }

    # For the entries in the JSON file:
    # Normalize spaces for Canvas names (no leading or trailing spaces, exactly 1 space between tokens)
    for assign_name, assign_info in course_info["assignments"].items():
        tokens = assign_info['canvas_api']['canvas_name'].split()
        assign_info['canvas_api']['canvas_name'] = " ".join(tokens)

    # dict: Canvas name -> assignment info from JSON file
    json_assignments_lookup = dict()
    for assign_name, assign_info in course_info["assignments"].items():
        if assign_info['canvas_api']['canvas_name'] in json_assignments_lookup:
            printError(f"\t\tERROR: {json_assignments_lookup} is already in the json_assignments_lookup table.  Make sure that every item has a unique CanvasAPI name!")
        else:
            json_assignments_lookup[assign_info['canvas_api']['canvas_name']] = assign_info

    # Go through all the assignments in Canvas, via the CanvasAPI:
    print("Getting the assignment from Canvas")
    course, canvas = get_canvas_course(course_name, verbose)
    if course is None:
        return

    # if verbose:
    print(f"\tQuarter start date: {start_of_quarter.strftime('%a, %B %d, %Y')}")
    print(f"\tQuarter end date:   {general_due_date_info['date_of_last_day_of_the_quarter'].strftime('%a, %B %d, %Y')}")
    print(f"Getting Assignments for \"{Style.BRIGHT + Fore.RED + course.name+ Style.RESET_ALL}\"")

    if not noop:
        if not confirm_choice("Do you want to change the due dates for this course?", course.name, \
                       "Updating due dates now", \
                       "Operation canceled - NO CHANGES MADE"):
            return

    # Get all assignments:
    capi_assignments = course.get_assignments()

    # For the assignments in Canvas:
    # Normalize spaces for Canvas names (no leading or trailing spaces, exactly 1 space between tokens)
    for assign in capi_assignments:
        assign.name_original = assign.name # save the original name for when we update Canvasj
        tokens = assign.name.split()
        assign.name = assign.name_normalized =" ".join(tokens)


    all_capi_assignments = []
    for assign in capi_assignments:
        if not hasattr(assign, 'due_at_date'):
            due_date_str = "None"
        else:
            due_date_str = assign.due_at_date.astimezone(general_due_date_info['time_zone']).strftime("%Y-%m-%d %H:%M:%S")
        all_capi_assignments.append(AssignmentForDisplay(due_date_str, \
                                                         assign.name, assign.unlock_at, assign.lock_at))

    all_capi_assignments.sort(key=functools.cmp_to_key(cmp_AssignmentForDisplay ))

    if not noop:
        # first, go through and print all the current due dates (in case we mess up and need to manually reset things)
        print("Before we change anything, here are the due dates in Canvas: ".ljust(120, "="))
        for assign in all_capi_assignments:
            assign.print()

    all_capi_assignments_dict = {i.title : i  for i in all_capi_assignments}
    updated_capi_assignments_dict = {}

    # We're going to list the assignments with lock/unlock info
    # so we can tell the user that we changed the lock/unlock
    # date to be the same as the due date
    canvas_assignments_with_lock_or_unlock_set = {}

    # Any assignments set after the end of the quarter
    # should be emphasized in the output, so it's clear that
    # these need to be handled manually:
    canvas_assignments_after_quarter_end_dict = {}

    # Next, actually go through and adjust the due dates:
    if not noop:
        print("\nChanging the due dates in Canvas: ".ljust(120, "="))
    else:
        print("\nCalculating due dates (but NOT changing anything in Canvas): ".ljust(120, "="))

    for assign in capi_assignments:
        if assign.name in json_assignments_lookup and 'due_date' in json_assignments_lookup[assign.name]:

            the_assignment = json_assignments_lookup[assign.name] # this switches from looking up by Canvas name to JSON ID/key/name
            due_date = calculateDueDate(the_assignment, start_of_quarter, due_date_info_for_course, general_due_date_info, course_info["assignments"])

            if isinstance(due_date, datetime.datetime) \
                    or (isinstance(due_date, str) \
                        and due_date.endswith(NO_DUE_DATE_MARKER_STRING)):

                if isinstance(due_date, datetime.datetime):
                    # we have a valid datetime:
                    due_date_str = due_date.astimezone(general_due_date_info['time_zone']).strftime(
                        "%A, %b %d, %Y at %I:%M %p")
                    print(f"\tDue on: {due_date_str.ljust(35)} : {assign.name.ljust(40)}", end='')

                # Don't flag assignments as error when due date is intentionally not present:
                # (But do update it, so that we can remove lock_at dates, etc
                if isinstance(due_date, str) \
                        and due_date.endswith(NO_DUE_DATE_MARKER_STRING):
                    print(f"\tDue on: NO_DUE_DATE     (from json file)    : {assign.name.ljust(40)}", end='')
                    due_date = '' # Remove due date

                try:
                    # If there's a lock/unlock date then move them, relative to the due date
                    lock_at = ''
                    if hasattr(assign, 'lock_at_date') \
                            and assign.is_quiz_assignment:
                        # Where is lock, relative to the (original) due date?
                        lock_delta = assign.lock_at_date - assign.due_at_date
                        # Move lock to due date:
                        lock_at = assign.lock_at_date.replace(year=due_date.year, month=due_date.month, day=due_date.day)
                        # Then move lock relative to the new due date:
                        lock_at = due_date + lock_delta

                        canvas_assignments_with_lock_or_unlock_set[assign.name] = all_capi_assignments_dict[assign.name]

                    unlock_at = ''
                    if hasattr(assign, 'unlock_at_date') \
                            and assign.is_quiz_assignment:
                        unlock_delta =  assign.unlock_at_date - assign.due_at_date
                        unlock_at = assign.unlock_at_date.replace(year=due_date.year, month=due_date.month, day=due_date.day)
                        unlock_at = due_date + unlock_delta

                        # due_date should now be between unlock and lock dates

                        canvas_assignments_with_lock_or_unlock_set[assign.name] = all_capi_assignments_dict[assign.name]

                    # restore the name that Canvas is expecting:
                    assign.name = assign.name_original

                    if not noop:
                        updated_assignment = assign.edit(
                            assignment={
                                'due_at': due_date,
                                'lock_at': lock_at,
                                'unlock_at':unlock_at
                            }
                        )
                        print(" : Updated!")
                    else:
                        print() # each result is printed out on it's own line

                    # Copy the assignment into the 'updated assignments' map:
                    updated_capi_assignments_dict[assign.name_normalized] = all_capi_assignments_dict[assign.name_normalized]

                    if isinstance(due_date, datetime.datetime) \
                        and due_date > end_of_quarter:
                        canvas_assignments_after_quarter_end_dict[assign.name_normalized] = all_capi_assignments_dict[assign.name_normalized]

                except Exception as e:
                    printError("Error: " + str(type( e )) + " : " + str(e))
                finally:
                    # Guarantee that we restore the name without any goofy whitespacing:
                    assign.name = assign.name_normalized
            else:
                #  due_date is an error message (str)
                due_date_str = due_date
                print(f"\t--- Due date error for {assign.name}: {due_date_str.ljust(35)}")

    capi_assignments_NOT_updated_keyset = all_capi_assignments_dict.keys() - updated_capi_assignments_dict.keys()

    capi_assignments_NOT_updated_list = [ all_capi_assignments_dict[i] for i in capi_assignments_NOT_updated_keyset ]
    capi_assignments_NOT_updated_list.sort(key=functools.cmp_to_key(cmp_AssignmentForDisplay))

    all_json_assignments_dict = {}

    # Any unused entries in the JSON file?
    for assign_name, assign_info in course_info["assignments"].items():

        if 'resolved_due_date' not in assign_info:
            # This will ensure that we've calculated the due date
            # Anything we saw in the CAPI part should already have a due date
            # Anything we didn't see in the CAPI part should lack a due date until we call this:
            date_obj = calculateDueDate(assign_info, start_of_quarter, due_date_info_for_course, \
                             general_due_date_info, course_info["assignments"])
        else:
            date_obj = assign_info['resolved_due_date']

        date_str = ""
        if  isinstance(date_obj, datetime.datetime):
            date_str = date_obj.replace(microsecond=0).astimezone(general_due_date_info['time_zone']).isoformat()
        else:
            date_str = date_obj

        canvas_name = assign_info['canvas_api']['canvas_name']
        all_json_assignments_dict[canvas_name] = AssignmentForDisplay( date_str, canvas_name )

    json_but_not_capi_keyset = all_json_assignments_dict.keys() - all_capi_assignments_dict.keys()
    json_but_not_capi_list = [ all_json_assignments_dict[i] for i in json_but_not_capi_keyset ]
    json_but_not_capi_list.sort(key=functools.cmp_to_key(cmp_AssignmentForDisplay))

    if len(json_but_not_capi_list) > 0:
        print("\nAssignments that were found in JSON that were NOT found in Canvas: ".ljust(120,"="))
        for assign in json_but_not_capi_list:
            assign.print()

    if len(capi_assignments_NOT_updated_list) > 0:
        print("\nAssignments that were found in Canvas but were NOT updated: ".ljust(120,"=") + "\n\t\t(Are these missing from the JSON file?)")
        for assign in capi_assignments_NOT_updated_list:
            assign.print()

    # Build up the list of assignments where we changed the lock/unlock date:
    lock_or_unlock_list = [ canvas_assignments_with_lock_or_unlock_set[i] for i in canvas_assignments_with_lock_or_unlock_set ]
    lock_or_unlock_list.sort(key=functools.cmp_to_key(cmp_AssignmentForDisplay))

    if len(lock_or_unlock_list) > 0:
        print("\nPLEASE DOUBLE CHECK THE FOLLOWING ASSIGNMENTS! ".ljust(120,"="))
        print("These assignments have an 'Available After' / 'Available Until' date" )
        print("The Available After' / 'Available Until' dates were maintained (relative to the new date) but the times have been mangled")
        for assign in lock_or_unlock_list:
            assign.print()

    after_quarter_end_keyset = canvas_assignments_after_quarter_end_dict.keys()
    after_quarter_end_list = [ all_json_assignments_dict[i] for i in after_quarter_end_keyset ]
    after_quarter_end_list.sort(key=functools.cmp_to_key(cmp_AssignmentForDisplay))

    if len(after_quarter_end_list) > 0:
        # Always list when we're making changes
        # In no-op mode if the list is short then it's probably legit, so list it anyways
        if not noop or len(after_quarter_end_list) < 10:
            print(
                Style.BRIGHT + Fore.RED + "\nAssignments that have due dates AFTER the end of the quarter: ".ljust(120,                                                                                                        "=") + Style.RESET_ALL)
            for assign in after_quarter_end_list:
                assign.print()
        else:
            print(f"\nAssignments that have due dates AFTER the end of the quarter: ")
            print(f"\tIgnoring these {len(after_quarter_end_list)} items under the assumption that the end of quarter date wasn't changed for a no-op run")

    noninst_days_list = list(due_date_info_for_course['noninstructional_days_that_prevented_classes_dict'])
    noninst_days_list.sort(key=functools.cmp_to_key(cmp_AssignmentForDisplay))
    if len(noninst_days_list) > 0:
        print("\nRemember to create Canvas events for the following Non-Instructional Days: ".ljust(120,"="))
        for noninst_day in noninst_days_list:
            noninst_day.print()

    if noop:
        print()
        print(Style.BRIGHT + Fore.RED + "Don't forget to update holidays, etc!!"+ Style.RESET_ALL)

    print() # spacer line, so it's easier to see where output ends & prompt begins :)

# Returns:
#   One of the following:
#       1) a DateTime for the due date
#       2) a string containing an error message, describing why we can't calculate a DateTime
def calculateDueDate(assign, start_of_quarter, due_date_info_for_course, general_due_date_info, assignments_from_json):
    # Once we start this method we'll look up all the assignments using their JSON ID/name field
    # Instead of their CanvasAPI names

    # If we previously memoized it, return that value:
    if 'resolved_due_date' in assign:
        # print(f"Returning previously calculated answer for {assign['name']}")
        return assign['resolved_due_date']

    due_date_info = assign['due_date']
    if 'relative_to' not in due_date_info:
        return f"Assignment {assign['name']} doesn't have a 'relative_to' field in the 'due_date' object"
    if 'type' not in due_date_info['relative_to']:
        return f"Assignment {assign['name']} doesn't have a 'type' field in the 'due_date/relative_to' object"
    if 'offsets' not in due_date_info:
        return f"Assignment {assign['name']} doesn't have a 'offsets' field in the 'due_date' object"

    relative_to = due_date_info['relative_to']['type']
    offsets = due_date_info['offsets']

    # This will be replaced (or else it will be true :)  )
    due_date = f"Internal error when trying to calculate {assign['name']}"

    if relative_to == "START_OF_QUARTER":
        due_date = start_of_quarter
    elif relative_to == "FIRST_CLASS_OF_QUARTER":
        due_date = start_of_quarter
        offsets.insert(0, "-1 CALENDAR_DAY")
        offsets.insert(1, "+1 CLASS_DAY")
    elif relative_to == "NO_DUE_DATE":
        due_date = NO_DUE_DATE_MARKER_STRING
    elif relative_to == "ASSIGNMENT":
        if 'assignment_name' not in due_date_info['relative_to']:
            return f"Assignment {assign['name']} doesn't have a 'assignment_name' field in the 'due_date/relative_to' object"
        base_due_date_assign_name = due_date_info['relative_to']['assignment_name']
        # TODO: Recursively calculate (and cache) relative due date here

        if base_due_date_assign_name not in assignments_from_json:
            due_date = f"Couldn't determine due date of {assign['name']} because we could not find \"{base_due_date_assign_name}\" in gradingTool.json"
        else:
            due_date = calculateDueDate(assignments_from_json[base_due_date_assign_name], start_of_quarter, due_date_info_for_course, general_due_date_info, assignments_from_json)
            if isinstance(due_date, str):
                due_date = f"Couldn't determine due date of {assign['name']} because of a problem with {base_due_date_assign_name}:\n" + due_date
    else:
        due_date += f": Did not recognize relative_to['type'] of {relative_to}"

    if  isinstance(due_date, datetime.datetime):
        # First set the time to the default so we can optionally replace it using an offset
        due_date = set_due_date_time(due_date, general_due_date_info)

        due_date = apply_offsets_to_due_date(due_date, offsets, due_date_info_for_course, general_due_date_info)


    # Memoize it, so we don't have to repeat all this work
    assign['resolved_due_date'] = due_date

    return due_date

# Returns
#   A DateTime
def apply_offsets_to_due_date(due_date:datetime.datetime, offsets, due_date_info_for_course, general_due_date_info):

    for szOffset in offsets:
        parts = szOffset.split(' ')
        op = parts[len(parts) - 1] # operation is the last item

        if op == "ABS_TIME":
            sz_time = parts[0]
            try:
                due_time = datetime.datetime.strptime(sz_time, FMT_TIME_WITHOUT_DATE).time()
            except ValueError as ve:
                printError(f"Could not parse {sz_time} as time using format string of {FMT_TIME_WITHOUT_DATE} - IGNORING THIS OFFSET")
            due_date = due_date.combine(due_date, due_time, tzinfo=due_date.tzinfo)

        elif op == "CALENDAR_DAY":
            how_many = int(parts[0])
            # print(f"Moving forwards {how_many} calendar days")
            if how_many > 0:
                move_by = 1
            else:
                move_by = -1

            while how_many != 0:
                due_date = due_date + datetime.timedelta(days=move_by)
                how_many = how_many - move_by

        elif op == "CLASS_DAY":
            how_many = int(parts[0])
            # print(f"Moving forwards {how_many} class days")
            if how_many > 0:
                move_by = 1
            else:
                move_by = -1

            while how_many != 0:
                idx_cur_day = None
                idx_next_class = None
                moved_off_starting_day = False

                try:
                    idx_cur_day = idx_starting_day = due_date_info_for_course["days_of_week"].index(due_date.astimezone(general_due_date_info['time_zone']).strftime("%a"))
                    # If we're at the last day of class this week then wrap around to next week's first day:
                    idx_next_class = (idx_starting_day + 1) % len(due_date_info_for_course["days_of_week"])
                except ValueError as ve:
                    # We're here because we couldn't find due_date's day-of-week in the list of class days for the course
                    pass
                    # print(str(ve))

                while moved_off_starting_day == False \
                        or idx_cur_day is None \
                        or idx_cur_day != idx_next_class:
                    # Move due date by 1 day and see if we're on the next class day:
                    due_date = due_date + datetime.timedelta(days = move_by)

                    moved_off_starting_day = True

                    try:
                        idx_cur_day = due_date_info_for_course["days_of_week"].index(due_date.astimezone(general_due_date_info['time_zone']).strftime("%a"))

                        if idx_next_class is None:
                            # must have started between class days, so the first one we find is the 'next' one
                            # this will cause the loop to stop
                            idx_next_class = idx_cur_day

                        # If the current due_date is a non-instructional day,
                        # AND we're avoiding due dates on non-instructional days,
                        # then skip this date

                        if not due_date_info_for_course['class_on_noninstructional_days']:
                            result = list(filter(lambda noninst_day: noninst_day['date'].date() == due_date.astimezone(general_due_date_info['time_zone']).date(), \
                                                     general_due_date_info['noninstructional_days']))
                            is_noninst_day = len(result) > 0

                            if is_noninst_day:
                                # This day isn't usable, so keep looking for the next class day
                                idx_next_class = (idx_next_class + 1) % len(due_date_info_for_course["days_of_week"])

                                noninst_date_str = result[0]['date'].strftime("%Y-%m-%d")
                                noninst = AssignmentForDisplay(noninst_date_str, result[0]['title'])
                                due_date_info_for_course['noninstructional_days_that_prevented_classes_dict'].add(noninst)

                    except ValueError as ve:
                        # print(str(ve))
                        idx_cur_day = None # This will cause us to skip any non-class days

                how_many = how_many - move_by

        elif op == "NEAREST_CALENDAR_DAY":
            which_day = parts[0].casefold() # 'Mon', 'Sun', etc

            day_ahead = due_date # We will move this forward from the starting day to check for the day we're looking for
            day_behind = due_date # Ditto, but backwards (earlier) in time
            while day_ahead.strftime("%a").casefold() != which_day \
                    and day_behind.strftime("%a").casefold() != which_day:

                # Move candidates by 1 day and see if we're on the next class day:
                day_ahead = day_ahead + datetime.timedelta(days = 1)
                day_behind = day_behind + datetime.timedelta(days = -1)

            # which day matched the target?
            if day_ahead.strftime("%a").casefold() == which_day:
                due_date = day_ahead
            elif day_behind.strftime("%a").casefold() == which_day:
                due_date = day_behind
            else:
                printError("Did not find a day for " + which_day + " - IGNORING THIS OFFSET")

    return due_date

def day_to_daynum(day:str):
    days = ["Blank space so that 'Sun' is 1", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    try:
        day_idx = days.index(day)
        return day_idx
    except ValueError:
        printError(f"day_to_daynum was given {day} but that isn't one of the legal day abbreciations: {str(days)}")
        sys.exit(-2)


def set_course_due_date_info_defaults(course_due_dates):
    if 'class_on_noninstructional_days' not in course_due_dates:
        course_due_dates['class_on_noninstructional_days'] = False

    if 'days_of_week' not in course_due_dates:
        printError("Missing 'days_of_week' from course due date info - please check gradingTool.json")

    course_due_dates['days_of_week'].sort(key=day_to_daynum)

    # This will be filled with AssignmentForDisplay objects
    # User will be reminded to create events for these dates
    course_due_dates['noninstructional_days_that_prevented_classes_dict'] = set()

    return course_due_dates

FMT_DATE_WITHOUT_TIME = "%Y-%m-%d" # 2024-03-25
FMT_TIME_WITHOUT_DATE = "%H:%M" # 23:59

def is_valid_date(str, format):
    try:
        datetime.datetime.strptime(str, format)
        return True
    except Exception:
        return False

def is_valid_noninstructional_day(noninst_day):
    if 'title' not in noninst_day:
        printError("Missing title for noninstructional day:")
        dir(noninst_day)
        return False

    if 'date' not in noninst_day:
        printError("Missing date for noninstructional day:")
        dir(noninst_day)
        return False

    if not  is_valid_date(noninst_day['date'], FMT_DATE_WITHOUT_TIME):
        printError(f"Invalid date for noninstructional day:\n\t(Used format string {FMT_DATE_WITHOUT_TIME})\n")
        dir(noninst_day)
        return False

    return  'title' in noninst_day and \
            'date' in noninst_day and \
            is_valid_date(noninst_day['date'], FMT_DATE_WITHOUT_TIME)

def noninstructional_day_json_to_python(noninst_day):
    noninst_day['date'] = datetime.datetime.strptime(noninst_day['date'], FMT_DATE_WITHOUT_TIME)

    return noninst_day

def get_general_due_date_info_defaults():
    config = get_app_config()
    general_due_dates = config.getKey(f"due_date_info", "")
    if general_due_dates == "":
        printError(f"Could not find general due date info in gradingTool.json")
        return None

    zoneName = config.getKey(f"app-wide_config/preferred_time_zone", "")
    if zoneName == "":
        printError(f"Could not find app-wide_config/preferred_time_zone in gradingTool.json")
        return None

    general_due_dates['time_zone'] = pytz.timezone(zoneName)
    if 'date_of_first_day_of_the_quarter' in general_due_dates:
        general_due_dates['date_of_first_day_of_the_quarter'] = datetime.datetime.strptime(general_due_dates['date_of_first_day_of_the_quarter'], FMT_DATE_WITHOUT_TIME)
        general_due_dates['date_of_first_day_of_the_quarter'] = date_time_from_local_to_utc(general_due_dates['date_of_first_day_of_the_quarter'], \
                                                                                            general_due_dates['time_zone'])
    else:
        general_due_dates['date_of_first_day_of_the_quarter'] = None

    if 'date_of_last_day_of_the_quarter' in general_due_dates:
        general_due_dates['date_of_last_day_of_the_quarter'] = datetime.datetime.strptime(general_due_dates['date_of_last_day_of_the_quarter'], FMT_DATE_WITHOUT_TIME)
        general_due_dates['date_of_last_day_of_the_quarter'] = date_time_from_local_to_utc(general_due_dates['date_of_last_day_of_the_quarter'], \
                                                                                            general_due_dates['time_zone'])
    else:
        general_due_dates['date_of_last_day_of_the_quarter'] = None

    if 'assignment_default_due_time' in general_due_dates:
        # We assume that the naive time is specified for the default time zone
        # We'll set the time for due dates later on
        default_due_time = datetime.datetime.strptime(general_due_dates['assignment_default_due_time'], FMT_TIME_WITHOUT_DATE).time()
        general_due_dates['assignment_default_due_time'] = default_due_time
    else:
        general_due_dates['assignment_default_due_time'] = None

    if 'noninstructional_days' not in general_due_dates:
        general_due_dates['noninstructional_days'] = []
    else:
        general_due_dates['noninstructional_days'] = [noninstructional_day_json_to_python(noninst_day) for noninst_day in general_due_dates['noninstructional_days'] if is_valid_noninstructional_day(noninst_day)]

    return general_due_dates

def set_due_date_time(due_date:datetime.datetime, general_due_date_info):
    default_due_time = general_due_date_info["assignment_default_due_time"]
    default_time_zone = general_due_date_info['time_zone']
    due_date_in_utc = default_time_zone.localize(due_date.combine(due_date, default_due_time))
    return due_date_in_utc


def date_time_from_local_to_utc(dt_naive, tz_local):
    local_dt = tz_local.localize(dt_naive, is_dst=None)
    utc_dt = local_dt.astimezone(pytz.utc)
    return utc_dt