

import os
import os.path
import platform
import string
# cd command that works as a context manager:
# from https://stackoverflow.com/a/24176022/250610
# Ex:
#   with cd('/tmp'):
from contextlib import contextmanager
from pathlib import Path

from mikesgradingtool.utils.config_json import get_app_config

@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


# from https://gist.github.com/seanh/93666
def format_filename(s):
#     ""Take a string and return a valid filename constructed from the string.
# Uses a whitelist approach: any characters not present in valid_chars are
# removed. Also spaces are replaced with underscores.
#
# Note: this method may produce invalid filenames such as ``, `.` or `..`
# When I use this method I prepend a date string like '2009_01_15_19_46_32_'
# and append a file extension like '.txt', so I avoid the potential of using
# an invalid filename.
#
# ""
    valid_chars = "-_() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in s if c in valid_chars)
    filename = filename.replace(' ', '_')  # I don't like spaces in filenames.
    return filename

# append _1, _2, etc, onto the filename
# if startWithSuffix is True then use a prefix the first time (otherwise start with filenameOrig)
def UniqueFileName(fileNameOrig, startWithSuffix=False):
    ctr = 0
    fileExtList = os.path.splitext(fileNameOrig)
    if startWithSuffix:
        filename = fileExtList[0] + "_" + str(ctr) + fileExtList[1]
    else:
        filename = fileNameOrig
    while os.path.exists(filename):
        ctr = ctr + 1
        filename = fileExtList[0] + "_" + str(ctr) + fileExtList[1]
        if ctr > 20:
            raise Exception("This script can only unique-ify a name 20 time: " + filename)
    return filename

def get_lock_filename(fp_file):
    config = get_app_config()
    alreadyCopiedSuffix = config.verify_keys([
        "misc_files/FileAlreadyProcessedMarker",
    ])

    file = os.path.basename(fp_file)
    fnAlreadyProcessed = format_filename(file + alreadyCopiedSuffix) + ".txt"
    fpProcessed = os.path.join(os.path.dirname(fp_file), fnAlreadyProcessed)

    # Windows filename length limit is 260 chars, unless you prefix it with \\?\
    if platform.system() == "Windows":
        fpProcessed = "\\\\?\\" + fpProcessed

    return fpProcessed

def is_file_a_lock_file(fp_file: str):
    config = get_app_config()
    alreadyCopiedSuffix = config.verify_keys([
        "misc_files/FileAlreadyProcessedMarker",
    ])
    alreadyCopiedSuffix= config.getKey("misc_files/FileAlreadyProcessedMarker")

    file = os.path.basename(fp_file)
    return fp_file.endswith(alreadyCopiedSuffix+".txt")

def is_file_locked(fp_file):
    config = get_app_config()
    alreadyCopiedSuffix = config.verify_keys([
        "misc_files/FileAlreadyProcessedMarker",
    ])

    fpProcessed = get_lock_filename(fp_file)

    return os.path.exists(fpProcessed)

def lock_file(fp_file):
    config = get_app_config()
    alreadyCopiedSuffix = config.verify_keys([
        "misc_files/FileAlreadyProcessedMarker",
    ])

    fpProcessed = get_lock_filename(fp_file)

    os.makedirs(os.path.dirname(fp_file), exist_ok=True)
    Path(fpProcessed).touch()

    return fpProcessed


def rmtree_remove_readonly_files(func, path, exc_info):
    # ""
    # Error handler for ``shutil.rmtree``.
    #
    # If the error is due to an access error (read only file)
    # it attempts to add write permission and then retries.
    #
    # If the error is for another reason it re-raises the error.
    #
    # Usage : ``shutil.rmtree(path, onerror=rmtree_remove_readonly_files)``
    #
    # This code was copied from
    # http://stackoverflow.com/questions/2656322/shutil-rmtree-fails-on-windows-with-access-is-denied
    # ""
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


from threading import Lock

mylock = Lock()
p = print

def print_threadsafe(*a, **b):
	with mylock:
		p(*a, **b)


class grade_list_collector(object):
    # ""A class to collect up the 'what needs to be graded' info
    # for the instructor""

    def __init__(self):
        #""Set up the empty lists""
        self.no_submission = list()  # for CanvasAPI - students who didn't submit anything
        self.ungraded = list()
        self.new_student_work_since_grading = list()
        self.graded = list()
        self.verbose = True # print everything by default

    def generate_grading_list_collector(self, tag):
        def grading_list_collector():

            branches = get_remote_branches_list()

            sha_tag, dt_tag = extract_sha_and_datetime(tag, mode=Mode.Tag)
            if sha_tag is None:
                logger.debug("This assignment hasn't been graded yet")
                self.ungraded.append(os.getcwd() + get_multiple_branches_suffix(branches))
                return True

            sha_head, dt_head = extract_sha_and_datetime("head", mode=Mode.Commit)

            if sha_head == sha_tag:
                logger.debug("SHA's for commits matched GRADED MOST RECENT SUBMISSION: " + os.getcwd())
                self.graded.append(os.getcwd() + get_multiple_branches_suffix(branches))
            elif dt_tag < dt_head:
                logger.debug("Instructor feedback was tagged then more work was submitted: " + os.getcwd())
                self.new_student_work_since_grading.append(os.getcwd()  + get_multiple_branches_suffix(branches))
            else:
                self.new_student_work_since_grading.append(
                    os.getcwd() + get_multiple_branches_suffix(branches) + " <== Had that odd 'tag' timestamp is >= 'head' timestamp BUT tag is not the current head issue")

                # We don't want this for the 'grading list' output:
                if self.verbose:
                    print("Tag that we looked for: " + tag)
                    print("sha_head: " + str(sha_head) if sha_head else "None")
                    print("dt_head: " + str(dt_head) if dt_head else "None")

                    print("sha_tag: " + str(sha_tag) if sha_tag else "None")
                    print("dt_tag: " + str(dt_tag) if dt_tag else "None")

                    printError("This directory has graded feedback, " \
                               "but the most recent commit is prior to the instructor's" \
                               " feedback commit & tag.  This might indicate a problem" \
                               " with a timezone on the server\n\t" + \
                               os.getcwd())
            return True

        return grading_list_collector

