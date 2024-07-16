'''
Created on May 28, 2012

Grading Tool (gt)

# Publishing using poetry:
# https://www.freecodecamp.org/news/how-to-build-and-publish-python-packages-with-poetry/

# To build and install using pipx:
# In the MikesGradingTool root dir:

cd "C:\\MIkesStuff\\Pers\\Dropbox\\Work\\Courses\\MikesGradingTool"

poetry build -f wheel
pipx uninstall mikesgradingtool
pipx install  --verbose dist/mikesgradingtool-0.1.0-py3-none-any.whl
#   Watch for the file name changing!

All in one line:
poetry build -f wheel ; pipx uninstall mikesgradingtool ; pipx install  --verbose dist/mikesgradingtool-0.1.1-py3-none-any.whl ; mikesgradingtool.exe


Python + Word automation: http://win32com.goermezer.de/content/view/173/190/

I

@author: MikePanitz
'''

# For constants like __app_name__ and __version:
import mikesgradingtool
import argparse
import os
import sys

from mikesgradingtool.utils.config_json import get_app_config
from mikesgradingtool.utils.diskcache_utils import close_app_cache
from mikesgradingtool.utils.my_logging import get_logger
from mikesgradingtool.utils.print_utils import GradingToolError, printError

import mikesgradingtool.Canvas.CanvasHelper as CanvasHelper
import mikesgradingtool.MiscFiles.MiscFilesHelper as MiscFilesHelper
from mikesgradingtool.HomeworkHelpers.CopyRevisionFeedback \
    import CopyRevisionFeedback
from mikesgradingtool.HomeworkHelpers.CopyTemplateToStudents \
    import CopyTemplateToStudents

from colorama import init
init()

logger = get_logger(__name__)


#
# import stackprinter
# stackprinter.set_excepthook(style='darkbg2')

def fnPrepCopyRevisionFeedback(args):
    print('\nREVISE MODE: Copying feedback files (and renaming them to match new revision name)')
    if args.DEST is None:
        printError(
            "Second parameter is required! (only given " + args.SRC + ")")
        return
    print('\tSRC:\t' + args.SRC + "\n\tDEST:\t" + args.DEST + "\n")
    if not os.path.exists(args.SRC):
        printError('Unable to find ' + args.SRC)
        return
    if not os.path.isdir(args.SRC):
        printError("'SRC' argument must be a directory but isn't")
        print(f"\tSRC: {args.SRC}\n")
        sys.exit()

    if not os.path.exists(args.DEST):
        printError('Unable to find ' + args.DEST)
        return
    if not os.path.isdir(args.DEST):
        printError("'DEST' argument must be a directory but isn't")
        print(f"\tDEST: {args.DEST}\n")
        sys.exit()

    CopyRevisionFeedback(args.SRC, args.DEST)


def fnPrepCopyTemplate(args):
    print('\nTEMPLATE MODE: Copying template file to student dirs (and renaming them)')
    if args.DEST is None:
        print("Second parameter is required! (only given " + args.SRC + ")")
        return

    print('\tSRC:\t' + args.SRC + "\n\tDEST:\t" +
          args.DEST + "\n\tprefix:" + args.prefix + "\n")

    if not os.path.isfile(args.SRC):
        print("'SRC' argument must be a file but isn't")
        print(f"\tSRC: {args.SRC}\n")
        print(
            "(Perhaps you meant to use the -r option, to copy revision feedback?)\n")
        sys.exit()

    if not os.path.isdir(args.DEST):
        print("'DEST' argument must be a directory but isn't")
        print(f"\tDEST: {args.DEST}\n")
        sys.exit()

    CopyTemplateToStudents(args.SRC, args.DEST, args.prefix)

class ArgParserHelpOnError(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)

# The 'CLI' function is used by the overall GradingTool program (it's needed to package stuff using PyZip)
def CLI():

#region Set up argparse
    root_parser = ArgParserHelpOnError(
        description = mikesgradingtool.__app_name__ + ': Automate repetitive grading tasks (Version ' + mikesgradingtool.__version__ + ')')

    subparsers = root_parser.add_subparsers(dest='command', help='sub-command help')

    parser_verbose = argparse.ArgumentParser(add_help=False)
    parser_verbose.add_argument('-v', '--verbose', action='store_true',
                                help='For additional, more detailed output')

    parser_src = argparse.ArgumentParser(add_help=False)
    parser_src.add_argument('SRC', help='the source directory')

    parser_src_dest = argparse.ArgumentParser(add_help=False, parents=[parser_src])
    parser_src_dest.add_argument('DEST', help='the destination directory')  # , nargs='?')


    szSummary: str
    szHelp: str

    ################################# MISC. FILE MANIPULATORS ################################################
    def setup_misc_file_parsers(subparsers):
        szSummary = 'Misc. file subcommands'
        szHelp = 'Commands for working with files (regardless of where they came from)'
        misc_files = subparsers.add_parser('files',
                                            aliases=['f'],
                                            help=szSummary,
                                            description=szHelp)
        misc_files_subparsers = misc_files.add_subparsers(dest='subcommand', help="Help for the misc. files parser")

        parser_files_template_copy_to_subdir = misc_files_subparsers.add_parser('copyToSubdir',
                                                         aliases=['c'],
                                                         help='Copy the given file to all the subdirs in DEST')
        parser_files_template_copy_to_subdir.add_argument('template_file', help='The file.  Will be renamed to include the subdir\'s name')
        parser_files_template_copy_to_subdir.add_argument('SRC', help='The directory that contains the subdirs.  File will be copied to ALL subdirs')
        parser_files_template_copy_to_subdir.set_defaults(func=MiscFilesHelper.fn_misc_files_copy_to_subdir)

        parser_files_template_copier = misc_files_subparsers.add_parser('template',
                                                         aliases=['t'],
                                                         help='Copy all the files given by TEMPLATE into any feedback files in SRC')
        parser_files_template_copier.add_argument('template_file', help='The template file')
        parser_files_template_copier.add_argument('SRC', help='The directory that contains the files to copy the template into')
        parser_files_template_copier.set_defaults(func=MiscFilesHelper.fn_misc_files_copy_template)

        parser_files_feedback_copier = misc_files_subparsers.add_parser('move_feedback',
                                                         aliases=['m'],
                                                         help='Move all the instructor feedback files in SRC to the matching student dir in DEST')
        parser_files_feedback_copier.add_argument('SRC', help='The directory that contains the instructor\'s feedback files (file names contain/are similar to student dest dir)')
        parser_files_feedback_copier.add_argument('DEST', help='The directory that contains the student dirs (the dir names must be similar to the instuctor\'s feedback file names)')
        parser_files_feedback_copier.add_argument('-c', "--confirm", action="store_true",
                                                  help='Ask before moving each file (default is to move to whatever the "best" match is, which can be random for files without student names in them)')

        parser_files_feedback_copier.set_defaults(func=MiscFilesHelper.fn_misc_files_move_feedback_to_student_dirs)

    setup_misc_file_parsers(subparsers)

    ################################# LIST COURSES, ASSIGNMENTS AND GITHUB/CANVASAPI ACCESS ##################
    def setup_list_info_parsers(subparsers):
        szSummary = 'List info'
        szHelp = f'List all the homework assignments in gradingtool.json'
        list_info = subparsers.add_parser('list',
                                            aliases=['l'],
                                            help=szSummary,
                                            description=szHelp)
        list_info.add_argument('-c', '--COURSE',
                                help='Name of the course (e.g., 142), leave out for all courses')

        list_info.set_defaults(func=CanvasHelper.fn_canvas_list_homeworks)

    setup_list_info_parsers(subparsers)

    ################################# Canvas ################################################
    def setup_canvas_parsers(subparsers):
        config = get_app_config()
        dir_for_new_feedbacks, zip_file_name = config.verify_keys([
            "canvas/NewDirForMissingFeedbackFiles",
            "canvas/ZipFileToUploadToCanvas"
        ])

        szSummary = 'Canvas subcommands'
        szHelp = 'Commands for working with the CanvasAPI (download), and with files bulk-downloaded from Canvas'
        parser_canvas = subparsers.add_parser('canvas',
                                                        aliases=['c'],
                                                        help=szSummary,
                                                        description=szHelp)

        canvas_subparsers = parser_canvas.add_subparsers(dest='subcommand', help="Help for the canvas parser")

        parser_canvas_new_announcement = canvas_subparsers.add_parser('new_announcement',
                                                                aliases=['a'],
                                                                help=f'Post a new announcement for a particular course')
        parser_canvas_new_announcement.add_argument('ALIAS_OR_COURSE',
                                               help='Alias for course + assignment, or the name of the course (e.g., 142)')
        parser_canvas_new_announcement.add_argument('TEMPLATE', nargs='?', default='',
                                               help='The name of the announcement template to use (Optional)')
        parser_canvas_new_announcement.add_argument('-d', '--DATE', help='Date (if the template needs it) in YYYY-MM-DD-HH-MM or YYYY-MM-DD (11:50pm assumed) format')
        parser_canvas_new_announcement.add_argument('-v', '--VERBOSE', action='store_true', help='Show extra info (verbose)')
        parser_canvas_new_announcement.set_defaults(func=CanvasHelper.fn_canvas_new_announcement)

        parser_canvas_set_assignment_due_date = canvas_subparsers.add_parser('set_assignment_due_date',
                                                                aliases=['dud'],
                                                                help=f'Set the due date for an assignment (c.f. calculate_all_due_dates)')
        parser_canvas_set_assignment_due_date.add_argument('ALIAS_OR_COURSE',
                                               help='Alias for course + assignment, or the name of the course (e.g., 142)')
        parser_canvas_set_assignment_due_date.add_argument('DUE_DATE',
                                                   help='Due date in YYYY-MM-DD-HH-MM or YYYY-MM-DD (11:50pm assumed) format, or the letter x to remove (delete) the due date')
        parser_canvas_set_assignment_due_date.add_argument('HOMEWORK_NAME', nargs='?', default='',
                                               help='The name of the homework assignment (Optional - for when alias isn\'t used)')
        parser_canvas_set_assignment_due_date.add_argument('-v', '--VERBOSE', action='store_true', help='Show extra info (verbose)')
        parser_canvas_set_assignment_due_date.set_defaults(func=CanvasHelper.fn_canvas_set_assignment_due_date)

        parser_download_homeworks = canvas_subparsers.add_parser('download',
                                                                     aliases=['d'],
                                                                     help=f'Download new student homework submissions and update existing subs (using the CanvasAPI)')
        parser_download_homeworks.add_argument('COURSE',
                                               help='Name of the course (e.g., 142), or \'all\' for all sections OR ELSE the alias in gradingtool.json that lists the course and homework (in which case you don\'t need the second argument)')
        parser_download_homeworks.add_argument('HOMEWORK_NAME', nargs='?', default='',
                                               help='The name of the homework assignment (or "all", to download all assignments for this class)')
        parser_download_homeworks.add_argument('-d', '--DEST',
                                               help='Directory to download homework into and/or update existing repos')
        parser_download_homeworks.add_argument('-q', '--QUARTER',
                                               help='Quarter code to look for (e.g., "S20" for Spring 2020)')
        parser_download_homeworks.add_argument('-v', '--VERBOSE', action='store_true', help='Show extra info (verbose)')
        parser_download_homeworks.set_defaults(func=CanvasHelper.fn_canvas_download_homework)

        parser_canvas_lock_assignment = canvas_subparsers.add_parser('lock_assignment',
                                                                aliases=['l'],
                                                                help=f'Lock (or unlock) an assignment to prevent (allow) homework uploads.  Does not prevent students from attaching files to Canvas comments on their submission, sadly')
        parser_canvas_lock_assignment.add_argument('ALIAS_OR_COURSE',
                                               help='Alias for course + assignment, or the name of the course (e.g., 142)')
        parser_canvas_lock_assignment.add_argument('HOMEWORK_NAME', nargs='?', default='',
                                               help='The name of the homework assignment (Optional - for when alias isn\'t used)')
        parser_canvas_lock_assignment.add_argument('-u', '--UNLOCK', action='store_false', help='Unlock the assignment (when missing, this defaults to "yes, lock the assignment")')
        parser_canvas_lock_assignment.add_argument('-v', '--VERBOSE', action='store_true', help='Show extra info (verbose)')
        parser_canvas_lock_assignment.set_defaults(func=CanvasHelper.fn_canvas_lock_assignment)

        parser_canvas_set_due_dates = canvas_subparsers.add_parser('calculate_all_due_dates',
                                                                   aliases=['h'],
                                                                   help=f'Set the due dates for all homeworks in a particular course')
        parser_canvas_set_due_dates.add_argument('COURSE',
                                                 help='Name of the course (e.g., 142)')
        parser_canvas_set_due_dates.add_argument('HOMEWORK_NAME', nargs='?', default='',
                                                 help='The name of the homework assignment (to update only that assignment)')
        parser_canvas_set_due_dates.add_argument('-f', '--FIRST_DAY_OF_QUARTER', nargs='?', default='',
                                                 help='The first day of the quarter, in YYYY-MM-DD format (so Sept 27th, 2023 would be 2023-09-27)')
        parser_canvas_set_due_dates.add_argument('-n', '--NOOP', action='store_true', help='No-op: Calculate due dates but don\'t change anything')
        parser_canvas_set_due_dates.add_argument('-v', '--VERBOSE', action='store_true', help='Show extra info (verbose)')

        parser_canvas_set_due_dates.set_defaults(func=CanvasHelper.fn_canvas_calculate_all_due_dates)

        parser_canvas_package_ = canvas_subparsers.add_parser('package',
                                                                aliases=['pu'],
                                                                help=f'Package all feedback files to upload to Canvas.  All files from Canvas are put into a .ZIP (named {dir_for_new_feedbacks}), new feedback files are put into a new directory (named {zip_file_name})')
        parser_canvas_package_.add_argument('SRC',
                                            help='The directory that contains the feedback files to upload')
        parser_canvas_package_.set_defaults(func=CanvasHelper.fn_canvas_package_feedback_for_upload)

        # Doesn't work, so I'm removing it from the UI.  Temporarily, hopefully
        # parser_canvas_post_assignment_grades = canvas_subparsers.add_parser('post_assignment_grade',
        #                                                         aliases=['p'],
        #                                                         help=f'Lock (or unlock) an assignment to prevent (allow) homework uploads.  Does not prevent students from attaching files to Canvas comments on their submission, sadly')
        # parser_canvas_post_assignment_grades.add_argument('ALIAS_OR_COURSE',
        #                                        help='Alias for course + assignment, or the name of the course (e.g., 142)')
        # parser_canvas_post_assignment_grades.add_argument('HOMEWORK_NAME', nargs='?', default='',
        #                                        help='The name of the homework assignment (Optional - for when alias isn\'t used)')
        # parser_canvas_post_assignment_grades.add_argument('-i', '--HIDE', action='store_true', help='Hide the assignment\'s grades (when missing, this defaults to "show the assignment\'s grades to the students")')
        # parser_canvas_post_assignment_grades.add_argument('-v', '--VERBOSE', action='store_true', help='Show extra info (verbose)')
        # parser_canvas_post_assignment_grades.set_defaults(func=CanvasHelper.fn_canvas_post_assignment_grades)

        parser_canvas_org = canvas_subparsers.add_parser('revisions',
                                                 aliases=['r'],
                                                 help='Copy original feedbacks into new, revised student submissions')
        parser_canvas_org.add_argument('SRC', help='The directory that contains the original feedback files OR ELSE the alias in gradingtool.json that lists the course and homework (in which case you don\'t need the second argument)')
        parser_canvas_org.add_argument('DEST', nargs='?', default='', help='The directory that contains the new homeworks to upload')
        parser_canvas_org.set_defaults(func=CanvasHelper.fn_canvas_copy_feedback_to_revision)

        parser_canvas_template_copier = canvas_subparsers.add_parser('template',
                                                                        aliases=['t'],
                                                                        help='Copy all the files given by TEMPLATE into any feedback files in SRC, then create a _NEW folder with templates for students who didn\'t include the feedback file')

        parser_canvas_template_copier.add_argument('template_file', help='The template file OR ELSE the alias in gradingtool.json that lists the course and homework (in which case you don\'t need the second argument)')
        parser_canvas_template_copier.add_argument('SRC', nargs='?', default='',
                                                  help='The directory that contains the files to copy the template into (the "_NEW" dir will be created in here')
        parser_canvas_template_copier.set_defaults(func=CanvasHelper.fn_canvas_copy_template)

        parser_canvas_upload_feedback = canvas_subparsers.add_parser('upload_feedback',
                                                                aliases=['u'],
                                                                help=f'Upload feedback file(s) to Canvas.')
        parser_canvas_upload_feedback.add_argument('ALIAS',
                                            help='The alias (listed in gradingtool.json) that refers to the course and assignment')
        parser_canvas_upload_feedback.add_argument('DEST', nargs='?', default=None,
                                               help='(Optional) The name of a single homework directory (to upload only that assignment)')
        parser_canvas_upload_feedback.add_argument('-v', '--VERBOSE', action='store_true', help='Show verbose output')
        parser_canvas_upload_feedback.set_defaults(func=CanvasHelper.fn_canvas_upload_feedback_via_CAPI)

        parser_canvas_d_r_l = canvas_subparsers.add_parser('downloadRevisionTemplate',
                                                                aliases=['z'],
                                                                help=f'Using an alias, download the assignment, copy feedback from the prior revision (if it exists), then copy the grading template into the assignments')
        parser_canvas_d_r_l.add_argument('alias',
                                            help='The alias (listed in gradingtool.json) that refers to the course and assignment')
        parser_canvas_d_r_l.add_argument('-v', '--VERBOSE', action='store_true', help='Show status of all repos (default is to show only those that have changed/need grading)')
        parser_canvas_d_r_l.set_defaults(func=CanvasHelper.fn_canvas_download_revision_template)

    setup_canvas_parsers(subparsers)
#endregion


    if len(sys.argv) == 1:
        root_parser.print_help()
        sys.exit(0)

    args = root_parser.parse_args()

    # set up defaults for common command line args
    setattr(args, 'SRC', getattr(args, 'SRC', None))
    setattr(args, 'DEST', getattr(args, 'DEST', None))
    setattr(args, 'prefix', getattr(args, 'prefix', None))
    setattr(args, 'verbose', getattr(args, 'verbose', False))

    # Only pre-process first positional arg if we know that we'll need file paths:
    if not hasattr(args, 'func'):
        root_parser.print_help()
        printError("Missing 'func' - did you pick an actual, existing, option?")
        sys.exit(-1)

    if args.SRC is not None:
        args.SRC = os.path.abspath(args.SRC)

    if hasattr(args, 'DEST') \
            and args.DEST is not None:
        args.DEST = os.path.abspath(args.DEST)

    # give optional args default values as needed:
    if hasattr(args, 'prefix') \
            and args.prefix is None:
        args.prefix = ""

    # Would like to allow for multiple levels of verbosity, if needed
    # for right now the command-line flag is just T/F, so
    # we'll translate into an int here:
    if hasattr(args, 'verbose') \
            and args.verbose is True:
        args.verbose = 1
    else:
        args.verbose = 0

    try:
        # call / dispatch out to the function that handles the menu item
        args.func(args)
    except GradingToolError as ex:
        printError(str(ex))
        sys.exit(-1)
    finally:
        close_app_cache()

    #
    # # Is it the same python interpreter?
    # import sys
    # print(sys.executable)
    #
    # # Is it the same working directory?
    # import os
    # print(os.getcwd())
    #
    # # Are there any discrepancies in sys.path?
    # # this is the list python searches, sequentially, for import locations
    # # some environment variables can fcuk with this list
    # print("sys.path entries:")
    # for p in sys.path:
    #     print(f"\t{p}")


if __name__ == "__main__":
    CLI()