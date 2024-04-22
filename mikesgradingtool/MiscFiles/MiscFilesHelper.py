#
#
import datetime
import difflib
import functools
import os
import re
import shutil
import sys
import typing
from pathlib import Path

import keyboard

from mikesgradingtool.SubmissionHelpers.StudentSubmission import StudentSubmission
from mikesgradingtool.SubmissionHelpers.StudentSubmissionListCollection import StudentSubmissionListCollection
from mikesgradingtool.utils.config_json import LoadConfigFile, SZ_CONFIG_FILE_LIST_KEY
from mikesgradingtool.utils.config_json import get_app_config
from mikesgradingtool.utils.misc_utils import cd, UniqueFileName, is_file_locked, lock_file
from mikesgradingtool.utils.my_logging import get_logger
from mikesgradingtool.utils.print_utils import GradingToolError

logger = get_logger(__name__)


def fn_misc_files_copy_to_subdir(args):
    fp_CopyTemplateToHere: str = args.SRC
    fpTemplate = args.template_file
    template_file_ext = os.path.splitext(fpTemplate)[1]
    config = get_app_config()
    sz_new_dir_for_feedbacks, sz_feedback_file_slug = config.verify_keys([
        "canvas/NewDirForMissingFeedbackFiles",
        "canvas/InstructorFeedbackSlug"
    ])
    print("Template file:\n\t" + fpTemplate)
    print("\nCopying template file into all subidrs of\n\t" + fp_CopyTemplateToHere)

    # c_copied = copy_file_to_subdirs(fp_CopyTemplateToHere, fpTemplate)
    # print(f"\nCopied the template into {c_copied} subdirs")
    fileExt = '.docx'
    file_name_template = os.path.basename(fpTemplate)

    # Given C:\foo\bar\student1 and fpTemplate of c:\baz\whatever\Assign1.docx
    # Assemble the filepath: C:\foo\bar\student1\Assign1-student1.docx
    sub_dirs = [os.path.join(f.path, os.path.splitext(file_name_template)[0] + "-" + os.path.basename(f.path) + os.path.splitext(file_name_template)[1]) for f in os.scandir(fp_CopyTemplateToHere) if f.is_dir()]
    #sub_dirs = [os.path.basename(f.path)  for f in os.scandir(fp_CopyTemplateToHere) if
    #            f.is_dir()]

    c_student_included, c_copied_included = 0, 0
    if len(sub_dirs) > 0:
        c_student_included, c_copied_included = copy_template_to_path_list(fpTemplate, sub_dirs)
    else:
        print(Fore.YELLOW + "Couldn't find any subdirs to copy the template into" + Style.RESET_ALL)

    print()

    print(f"\nCopied the template into {c_copied_included} subdirs (out of {c_student_included} total students)")

'C:\\MikesStuff\\Work\\Student_Work\\BIT_142_New\\ICE01\\cmdgladious\\In Class Exercises - Lecture 01-cmdgladious..docx'


def fn_misc_files_copy_template(args):
    fp_CopyTemplateToHere: str = args.SRC
    fpTemplate = args.template_file
    config = get_app_config()
    sz_re_feedback_file = config.verify_keys([
        "canvas/InstructorFeedbackFileNameRegex"])
    print("Template file:\n\t" + fpTemplate)
    print("\nCopying template for:")
    c_students, c_copied = copy_template_to_regex_matches(fp_CopyTemplateToHere, fpTemplate, sz_re_feedback_file)
    print(f"\nFound a total of {c_students} feedback files\n\tCopied the template into {c_copied} of those files")


def ignore_this_file(fp_file):
    config = get_app_config()
    fnBackups, alreadyCopiedSuffix = config.verify_keys([
        "misc_files/BackupDirName",
        "misc_files/FileAlreadyProcessedMarker",
    ])

    if fnBackups in fp_file \
        or alreadyCopiedSuffix in fp_file:
        return True
    else:
        return False


def copy_template_to_path_list(fpTemplate, rg_fp_target_files: typing.List[str]):
    # ""
    #
    # Note: the files listed in the target list may or may not already exist
    # ""

    config = get_app_config()
    fnBackups = config.verify_keys([
        "misc_files/BackupDirName"
    ])

    fpTemplate = os.path.abspath(fpTemplate)
    if not os.path.exists(fpTemplate):
        raise GradingToolError("Template file to copy doesn't exist:\n\t"+fpTemplate)

    if not os.path.isfile(fpTemplate):
        raise GradingToolError("Template 'file' to copy is not actually a file:\n\t" + fpTemplate)

    c_copied = 0
    c_students = 0

    # files now contains exactly and only the files we want to process:
    for destFile in rg_fp_target_files:

        # The philosophy here is that
        # it's worse to change the file and NOT create the lock file
        # instead of
        # creating the lock file and then being unable to change the file and unable to remove the lock file

        c_students = c_students + 1
        if is_file_locked(destFile):
            print("Already copied: " + os.path.basename(destFile))
            continue
        else:
            # Create the 'lock' file:
            fp_lock_file = lock_file(destFile)

            try:
                file = os.path.basename(destFile)

                # Put this in when I was worried about overwriting a graded assignment.
                # Keeping it in case I ever want it back
                # if os.path.exists(destFile):
                #     # Create the backup copy:
                #     fpBackups = os.path.join(os.path.dirname(destFile), fnBackups)
                #     Path(fpBackups).mkdir(parents=True, exist_ok=True)
                #     fpBackupFile = os.path.join(fpBackups, file)
                #     fpBackupFile = UniqueFileName(fpBackupFile, startWithSuffix=True)
                #     shutil.copy2(destFile, fpBackupFile)

                # replace the feedback file  with the grading rubric/template:
                print(("                {0:<20}".format(file)))
                shutil.copy2(fpTemplate, destFile)

                c_copied = c_copied + 1
            except BaseException as e:
                # If anything went wrong then remove the 'lock' file, so we'll try again later
                os.remove(fp_lock_file)
                print(e.args)

    return (c_students, c_copied)


def copy_template_to_regex_matches(fp_CopyTemplateToHere, fpTemplate, sz_re_files_to_replace):

    config = get_app_config()
    fnBackups, alreadyCopiedSuffix = config.verify_keys([
        "misc_files/BackupDirName",
        "misc_files/FileAlreadyProcessedMarker",
    ])

    re_files_to_replace = re.compile(sz_re_files_to_replace, re.IGNORECASE)

    fpTemplate = os.path.abspath(fpTemplate)
    print("Template file:\n\t" + fpTemplate)
    if not os.path.exists(fpTemplate):
        raise GradingToolError("Template file to copy does not exist:\n\t"+fpTemplate)

    if not os.path.exists(fp_CopyTemplateToHere):
        raise GradingToolError("Directory of student work does not exist:\n\t" + fp_CopyTemplateToHere)

    with cd(fp_CopyTemplateToHere):
        print("Directory to copy the templates to:\n\t" + fp_CopyTemplateToHere)

        print("\nCopying template for:")
        c_copied = 0
        c_students = 0

        for root, dirs, raw_file_list in os.walk(fp_CopyTemplateToHere):
            # Don't traverse our own backup dirs :)
            if fnBackups in dirs:
                dirs.remove(fnBackups)

            # Only process the files that contain INSTRUCTORFEEDBACK,
            # But don't process our lock files
            files = [file for file in raw_file_list if re_files_to_replace.search(file)
                                                       and alreadyCopiedSuffix not in file]

            # files now contains exactly and only the files we want to process:
            for file in files:
                destFile = os.path.join(root, file)

                # The philosophy here is that
                # it's worse to change the file and NOT create the lock file
                # instead of
                # creating the lock file and then being unable to change the file and unable to remove the lock file

                c_students = c_students + 1
                if is_file_locked(destFile):
                    print("Already copied: " + file)
                    continue
                else:
                    # Create the 'lock' file:
                    fp_lock_file = lock_file(destFile)

                    try:
                        # Create the backup copy:
                        fpBackups = os.path.join(root, fnBackups)
                        Path(fpBackups).mkdir(parents=True, exist_ok=True)
                        fpBackupFile = os.path.join(fpBackups, file)
                        fpBackupFile = UniqueFileName(fpBackupFile, startWithSuffix=True)
                        shutil.copy2(destFile, fpBackupFile)

                        # replace the feedback file  with the grading rubric/template:
                        print(("                {0:<20}".format(file)))
                        shutil.copy2(fpTemplate, destFile)

                        c_copied = c_copied + 1
                    except BaseException as e:
                        # If anything went wrong then remove the 'lock' file, so we'll try again later
                        os.remove(fp_lock_file)
                        print(e.args)

    # wordapp.Visible = wasVisible
    return (c_students, c_copied)


def autograder_common_actions(args, sz_glob_student_submission_dir, fn_organize_submissions, fn_convert_dir_to_student_sub):
    fp_grade_these: str = args.SRC
    fp_output: str = args.DEST
    print(
        f'\nAUTOGRADER MODE:\n\tSRC:\t{fp_grade_these}\n\nTidying up SRC in preparation for grading, then auto-grading it\n')

    config = get_app_config()
    student_submission_dir_suffix = config.verify_keys([
        "canvas/StudentSubFolderMarker"])

    if not os.path.isdir(fp_grade_these):
        print("'SRC' argument must be a directory but isn't")
        print(f"\tSRC: {fp_grade_these}\n")
        sys.exit()

    if fn_organize_submissions is not None:
        # consolidate & organize the submissions:
        fn_organize_submissions(args)
        print("\n=== Submissions Consolidated ===\n")
    else:
        print("\nNot organizing submissions ===\n")

    config = get_app_config()
    fn_autograder_config = config.verify_keys([
        "autograder/default_config_file_name",
    ])

    start = datetime.datetime.now()

    fpADesc = os.path.join(fp_grade_these, fn_autograder_config)
    assign_desc = LoadConfigFile(fpADesc)

    #  allow command line to override config file for where to put output
    if fp_output is not None:
        assign_desc['output_dir'] = fp_output

    print("Loaded the following config files:")
    for fpConfigFile in assign_desc[SZ_CONFIG_FILE_LIST_KEY]:
        print(f"\t{fpConfigFile}")
    print("")

    if "assignment_type" not in assign_desc:
        raise GradingToolError(
            "Could not find the 'assignment_type' key in the config files!")

    if assign_desc["assignment_type"] == "BIT_116_Assignment":
        raise GradingToolError("BIT 116 assignments not supported")

    # if args.GenerateGradesheet and \
    #         (assign_desc["assignment_type"] == "BIT_142_Assignment" or \
    #          assign_desc["assignment_type"] == "BIT_143_PCE"):
    #     raise GradingToolError("BIT 142 / 143 autograders don't (yet) support the 'generate blank gradesheet' option")

    all_sub_dirs = sorted(Path(fp_grade_these).glob(sz_glob_student_submission_dir))
    all_subs = StudentSubmissionListCollection(None)  # 'None' means 'Don't walk a dir to find student subs'

    now = datetime.datetime.now().strftime(StudentSubmission.DATE_TIME_FORMAT)
    for dir in all_sub_dirs:

        if os.path.isdir(dir):
            # don't autograde the output directory (if it exists) :)
            if os.path.isdir(assign_desc['output_dir']) \
                and os.path.samefile(dir, assign_desc['output_dir']):
                continue;

            next_student = fn_convert_dir_to_student_sub(assign_desc, dir, now)
            all_subs.Add(next_student)

    DoAutoGrading(all_subs, assign_desc)

    end = datetime.datetime.now()
    elapsedTime = end - start
    TotalDuration = str(elapsedTime).split('.', 2)[0]
    print("Just autograding (not consolidating) took " +
          TotalDuration + "\n")


# From https://www.geeksforgeeks.org/print-longest-common-substring/
def LCSubStr(X: str, Y: str):
    return getLCSSubStr(X, Y, len(X), len(Y))

def getLCSSubStr(X: str, Y: str,
                   m: int, n: int):
    # Create a table to store lengths of
    # longest common suffixes of substrings.
    # Note that LCSuff[i][j] contains length
    # of longest common suffix of X[0..i-1] and
    # Y[0..j-1]. The first row and first
    # column entries have no logical meaning,
    # they are used only for simplicity of program
    LCSuff = [[0 for i in range(n + 1)]
              for j in range(m + 1)]

    # To store length of the
    # longest common substring
    length = 0

    # To store the index of the cell
    # which contains the maximum value.
    # This cell's index helps in building
    # up the longest common substring
    # from right to left.
    row, col = 0, 0

    # Following steps build LCSuff[m+1][n+1]
    # in bottom up fashion.
    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0 or j == 0:
                LCSuff[i][j] = 0
            elif X[i - 1] == Y[j - 1]:
                LCSuff[i][j] = LCSuff[i - 1][j - 1] + 1
                if length < LCSuff[i][j]:
                    length = LCSuff[i][j]
                    row = i
                    col = j
            else:
                LCSuff[i][j] = 0

    # if true, then no common substring exists
    if length == 0:
        print("No Common Substring")
        return

    # allocate space for the longest
    # common substring
    resultStr = ['0'] * length

    # traverse up diagonally form the
    # (row, col) cell until LCSuff[row][col] != 0
    while LCSuff[row][col] != 0:
        length -= 1
        resultStr[length] = X[row - 1]  # or Y[col-1]

        # move diagonally up to previous cell
        row -= 1
        col -= 1

    # required longest common substring
    return ''.join(resultStr)


# end of function lcs
def fn_misc_files_move_feedback_to_student_dirs(args):
    fp_from: str = args.SRC
    fp_to = args.DEST
    move_with_confirmation = args.confirm

    config = get_app_config()
    # sz_re_feedback_file = config.verify_keys([
    #     "canvas/InstructorFeedbackFileNameRegex"])
    print(f"Moving instructor feedback from: {fp_from}")
    print(f"Moving to student dirs in:    {fp_to}")

    if not os.path.exists(fp_from):
        raise GradingToolError(F"Dir of instructor feedback files doesn't exist ({fp_from})")
    if not os.path.isdir(fp_from):
        raise GradingToolError(F"SRC argument is not a dir ({fp_from})")

    if not os.path.exists(fp_to):
        raise GradingToolError(F"Dir of student dirs doesn't exist ({fp_to})")
    if not os.path.isdir(fp_to):
        raise GradingToolError(F"DEST argument is not a dir ({fp_to})")

    _, _, rg_fn_feedback = next(os.walk(fp_from))
    _, student_dirs, _ = next(os.walk(fp_to))

    d_feedback = dict()

    print() # blank line
    if not move_with_confirmation:
        dest_col = "<Dest>".ljust(20)
        print(f"\t{dest_col}<File To Move>")

    for fn_feedback in rg_fn_feedback:
#        print("Matching: " + fn_feedback)
        # returns a 2-tuple: (student_dir_best_match, levenshtein_distance from fn_feedback)
        def min_diff(min, next):
            # print(f"min is: {str(min).ljust(50)}next is: {next}")

            if isinstance(min, str):
            #     seq = difflib.SequenceMatcher(None, min.lower(), fn_feedback.lower())
            #     min = (min, seq.ratio())
                subst = LCSubStr(min.lower(), fn_feedback.lower())
                min = (min, len(subst))

            # seq = difflib.SequenceMatcher(None, next.lower(), fn_feedback.lower())
            # next = (next, seq.ratio())
            subst = LCSubStr(next.lower(), fn_feedback.lower())
            next = (next, len(subst))

            if min[1] > next[1]:
                return min
            else:
                return next

        best_match = functools.reduce(min_diff, student_dirs)
 #       print("Best match: " + str(best_match))

        fn_feedbackd_quoted = '"' + fn_feedback + '"'

        if not move_with_confirmation:
            print(f"\t{best_match[0].ljust(20)}{fn_feedbackd_quoted}")
            shutil.move(os.path.join(fp_from, fn_feedback), \
                        os.path.join(fp_to, best_match[0]))
        else:
            print( f"Should I move: {fn_feedbackd_quoted} to: {best_match[0]}? (y/n)" )

            e: keyboard.KeyboardEvent = keyboard.read_event()
            while( e.event_type != 'down'):
                e = keyboard.read_event()

            # print(e.name)
            if e.name.lower() == 'y':
                shutil.move(os.path.join(fp_from, fn_feedback), \
                            os.path.join(fp_to, best_match[0]))