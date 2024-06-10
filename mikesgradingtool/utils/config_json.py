from collections import namedtuple
import copy
import functools
import json
import json.decoder
import os.path
import re
import sys
import typing


import jk_commentjson
from mikesgradingtool.utils.print_utils import printError, GradingToolError
from requests.structures import CaseInsensitiveDict
from jsmin import jsmin


@functools.lru_cache(1)
def get_app_config():
    gtc = GradingToolConfig()
    return gtc

SZ_DEST_DIR_SUFFIX_KEY = 'dest_dir_suffix'
SZ_ASSIGNMENTS_KEY = 'assignments'

# This is used for reading the app-wide JSON config file
# TODO use https://docs.python.org/3/library/functools.html#functools.cached_property to memoize the config settings
class GradingToolConfig:

    def __init__(self,fpConfig: str = None):
        if fpConfig is not None:
            self.fpgtConfig = fpConfig
        else:
            self.gradingToolConfigDir = os.path.expanduser("~/.gradingtool")
            self.fpgtConfig = os.path.abspath(os.path.join(self.gradingToolConfigDir, 'gradingtool.json'))

        # case insensitive dictionary:
        # from https://stackoverflow.com/a/16817943/250610
        self.hive = CaseInsensitiveDict()
        self.LoadConfig()


    def GetConfigFileDirPath(self):
        return self.gradingToolConfigDir


    def LoadConfig(self):
        try:
            with open(self.fpgtConfig, encoding="utf8") as open_file:
                minified = jsmin(open_file.read(), quote_chars="'\"`")
                self.hive = json.loads(minified)
                self.hive = CaseInsensitiveDict_Recursive(self.hive)

                if "courses" not in self.hive:
                    printError("Loading config: did not find a top-level 'courses' object!!!!")
                else:
                    mergeInheritedCourses(self.hive["courses"])

            # import pprint
            # pp = pprint.PrettyPrinter(indent=2, width=200)
            # print(f"config")
            # pp.pprint(self.hive)
        except json.decoder.JSONDecodeError as e:
            # The exception info isn't super-useful because jsmin squashed it into a single line

            # printError("2: " +e.doc)
            # printError("3: " +str(e.lineno))
            # printError("4: " +str(e.pos))
            # printError("5: " +str(e.args))
            # printError("6: " +str(e.colno))
            raise GradingToolError(
                "There was a problem somewhere in the .JSON config file:\n\t" + e.msg
                + "\n\tfile: " + self.fpgtConfig
                + "\n\tLocation:" + minified[e.colno:e.colno+40])

        except FileNotFoundError as fnfe:
            raise GradingToolError("Unable to find the config file.  I tried this file:\n\t"+self.fpgtConfig
                                   +"\nOn Windows it may be useful to use mklink to set up a symlink to your real HOME dir")

    # make the config file a context manager, so we can use it with 'with(...)' constructs
    def __enter__(self):
        self.LoadConfig()
        return self

    def getKeyParts(self, key):
        if key[-1:] == os.sep or key[-1:] == os.altsep:
            key = key[:-1]
        keyparts:typing.List[str] = key.split('/')
        return key, keyparts

    # If there's a 'course' above the key and that course
    # contains 'course_dir_suffix' then concatenate that
    # onto the end of the key
    # Useful for a second section that works by mostly inheriting from
    # a base course, but this way the second section downloads homeworks
    # into a unique directory

    # UNUSED: Get a dest_dir and fix it up if there's a 'course' with a suffix above it
    def getDestDir(self, key:str):
        key, keyparts = self.getKeyParts(key)
        sz_course = ""
        course = None

        dest_dir = self.getKey(key)

        for idx, part in enumerate(keyparts):
            sz_course = sz_course + "/" + part
            if part == 'courses':
                sz_course = sz_course + "/" + keyparts[idx+1]
                course = self.getKey(sz_course[1:], "") # remove leading /
                break

        if course is None or course == "":
            # Couldn't find 'courses' in the path; this is ok - just return the dest_dir
            return dest_dir

        if  SZ_DEST_DIR_SUFFIX_KEY not in course[SZ_ASSIGNMENTS_KEY]:
            return dest_dir

        suffix = course[SZ_DEST_DIR_SUFFIX_KEY]

        dest_dir += suffix

        return dest_dir

    # If course has an 'assignments' with 'dest_dir_suffix' in it then append that to dest_dir
    # This is idempotent: nothing is changed if the suffix is already at the end of dest_dir
    # Regardless, always return dest_dir
    def ensureDestDirHasSuffix(self, course, dest_dir:str):

        # Lookup course if it's not an object already:
        if isinstance(course, str):
            course = self.getKey(f"courses/{course}", "")
            if course == "":
                return dest_dir

        if SZ_DEST_DIR_SUFFIX_KEY in course[SZ_ASSIGNMENTS_KEY]:
            suffix = course[SZ_DEST_DIR_SUFFIX_KEY]

            if not dest_dir.endswith(suffix):
                dest_dir += suffix

        return dest_dir


    # If the key/keypath doesn't exist:
    #   If 'default' is set to something OTHER THAN None then this will be returned
    #   Else an exception will the thrown
    def getKey(self, key: str, default:typing.Any = None):
        key, keyparts = self.getKeyParts(key)

        previous_value = ""
        theDictionary = self.hive  # will move down into sub-dictionaries
        goodSoFar:str = ""

        for part in keyparts:
            if part not in theDictionary:
                if default is not None:
                    return default
                else:
                    printError(f"Couldn't find {part} in config{goodSoFar}")
                    sys.exit(-1)

            goodSoFar = goodSoFar + f"['{part}']"
            previous_value = theDictionary[part]
            theDictionary = theDictionary[part]

        # May as well return the value, given that we did all this work to walk here?
        return previous_value

    ### Will throw an exception if the key/keypath doesn't exist
    # return the string/value is there's only 1 thing in the 'keys' list
    # otherwise return a tuple (for multi-assignment)
    def verify_keys(self, keys: typing.List[str], base:str = None):
        values = list()
        for key in keys:
            if base is not None:
                # make sure that base DOES end in /
                if base[-1:] != '/':
                    base = base + '/'
                # make sure that key does NOT start with /
                if key[0] == '/':
                    key = key[1:]
                # then glue base to key, properly separated
                key = base + key
            values.append(self.getKey(key))
        if len(values) != 1: # empty (0) or more than 1
            return tuple(values)
        else:
            return values[0] # return this, exactly


def CaseInsensitiveDict_Recursive(dictionary: dict):
    cid = CaseInsensitiveDict()
    for k, d in dictionary.items():
        if isinstance(d, dict):
            d = CaseInsensitiveDict_Recursive(d)
        cid[k] = d
    return cid

HWInfo = namedtuple('HWInfo', 'course hw fp_dest_dir fp_template prior_version next_version')
def lookupHWInfoFromAlias(possible_alias):
    try:
        config = get_app_config()
        aliases = config.verify_keys([f"courses/aliases"] )
    except:
        return None

    course = hw = None

    for alias in aliases:
        match = re.search(alias['overall_pattern'], possible_alias)
        if match:
            course = re.sub(alias['course_match_pattern'], alias['course_replacement_pattern'], possible_alias)
            hw = re.sub(alias['hw_match_pattern'], alias['hw_replacement_pattern'], possible_alias)
            break

    if course is None:
        # printError(f"Couldn't find course matching {course}")
        return None

    # It's ok if any of the following are missing:
    fp_hw_template= config.getKey( f"courses/{course}/assignments/{hw}/grading_template", '')
#        if fp_hw_template == '':
#            printError(f"Found the alias \"{alias}\", but the underlying \"{hw}\" in \"{course}\" does NOT have a 'grading_template' value")

    fp_hw_dest_dir = config.getKey( f"courses/{course}/assignments/{hw}/dest_dir", '')
    if fp_hw_dest_dir != '':
        fp_hw_dest_dir = config.ensureDestDirHasSuffix(course, fp_hw_dest_dir)
#        if fp_hw_dest_dir == '':
#            printError(
#            f"Found the alias \"{alias}\", but the underlying \"{hw}\" in \"{course}\" does NOT have a 'dest_dir' value")
    prior_version = config.getKey(f"courses/{course}/assignments/{hw}/prior_version", "")
    if prior_version == "":
        prior_version = None

    next_version = config.getKey(f"courses/{course}/assignments/{hw}/next_version", "")
    if next_version == "":
        next_version = None

    return HWInfo(course, hw, fp_hw_dest_dir, fp_hw_template, prior_version, next_version)


SZ_COURSE_TO_INHERIT_FROM = "inherits_from"
def mergeInheritedCourses(json_config_courses):
    for course_name in json_config_courses:
        course = json_config_courses[course_name]

        if SZ_COURSE_TO_INHERIT_FROM in course:

            base_course_name = course[SZ_COURSE_TO_INHERIT_FROM]

            if base_course_name not in json_config_courses:
                printError(f"In JSON config file, course '{course_name}' has 'inherits_from' key but {base_course_name} not found in 'courses'")
                continue

            base_course = json_config_courses[base_course_name]
            json_config_courses[course_name] = mergeBaseCourseIntoNewCourse(json_config_courses, base_course, course)

def merge_CaseInsensitiveDicts(src, dest):
    "merges src into dest, recursively merging dictionary elements and overwriting non-dictionary keys in dest with the corresponding value in src"
    # based on https://stackoverflow.com/a/7205107/250610
    for key in src:
        if key in dest:
            if isinstance(dest[key], CaseInsensitiveDict) and isinstance(src[key], CaseInsensitiveDict):
                merge_CaseInsensitiveDicts(src[key], dest[key])
            elif dest[key] == src[key]:
                pass  # same leaf value
            else:
                # replace key with src value (for non-dictionary elements)
                dest[key] = copy.deepcopy(src[key])
                # Uncomment this to throw an exception, instead of replacing:
                # raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            dest[key] = copy.deepcopy(src[key])
    return dest

def mergeBaseCourseIntoNewCourse(json_config_courses, base_course, course):
    if SZ_COURSE_TO_INHERIT_FROM in base_course:
        base_course = mergeBaseCourseIntoNewCourse(json_config_courses, \
                                                   json_config_courses[base_course[SZ_COURSE_TO_INHERIT_FROM]], \
                                                   base_course)
    else:
        base_course = copy.deepcopy(base_course)

    course = merge_CaseInsensitiveDicts(course, base_course)

    return course


########################################################################################################################
########################################################################################################################
########################################################################################################################
########################################################################################################################

# this is used for managing the per-assignment JSON config files
# that the autograded assignments use
# Do NOT use this for gradingTool.json config file!
SZ_NEXT_CONFIG_FILE_KEY = "next_config_file"
SZ_CONFIG_FILE_LIST_KEY = "loaded_config_files"

def fixupPaths(currentFile, configFileBaseDir):
    # "" fix up things that appear to be paths, in order to ensure that they're absolute
    # a path is either an absolute path,
    # or a relative path to an existing file/directory
    # relative paths are changed into absolute paths
    #
    # currentFile is a dictionary of keys, some of which may be paths
    # configFileBaseDir is the dir to use a a base for attempting to resolve relative paths
    # ""
    for key in currentFile:

        if type(currentFile[key]) is dict:
            fixupPaths(currentFile[key], configFileBaseDir)
            continue
        if type(currentFile[key]) is not str:
            continue
        if os.path.isabs(currentFile[key]):
            continue

        # Let's see if this string value actually points to
        # an existing file/dir:
        possiblePath = os.path.normpath(
            os.path.join(configFileBaseDir, currentFile[key]))
        if os.path.exists(possiblePath) or \
                key == "output_dir":
            currentFile[key] = possiblePath
            # continue # not needed

def merge(dest, src, path=None):
    "merges src into dest, recursively merging dictionary elements and overwriting non-dictionary keys in dest with the corresponding value in src"
    # from https://stackoverflow.com/a/7205107/250610
    if path is None:
        path = []
    for key in src:
        if key in dest:
            if isinstance(dest[key], dict) and isinstance(src[key], dict):
                merge(dest[key], src[key], path + [str(key)])
            elif dest[key] == src[key]:
                pass  # same leaf value
            else:
                # replace key with src value (for non-dictionary elements)
                dest[key] = src[key]
                # Uncomment this to throw an exception, instead of replacing:
                # raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            dest[key] = src[key]
    return dest

def LoadConfigFile(fpConfigFile):
    # ""
    #     fpConfigFile: a full path to the JSON file to load
    #
    #     returns: a dictionary of all the key/values in that file
    #              or 'None' if the file can't be loaded
    #
    #     If the JSON file contains a key named "next_config_file" then we will recursively
    #         load that file, then update the recursive file with the keys from the current file.
    #         This will ensure that the current file takes precedence over files loaded later
    #         This will enable us to use 'next_config_file' as a 'base class' of configs which
    #             can be overridden / replaced in this file
    #
    # ""
    if not os.path.isfile(fpConfigFile):
        raise GradingToolError(f"Could not load config file {fpConfigFile}")

    #    configFileBaseDir:
    #        The dir containing this config file is used as the 'base dir'
    #        for any relative paths.
    #           (this is os.path.dirname(fpConfigFile) is used)
    configFileBaseDir = os.path.dirname(fpConfigFile)

    with open(fpConfigFile, "r") as fileADesc:
        try:
            currentFile = jk_commentjson.commentjson.load(fileADesc)
        except jk_commentjson.commentjson.JSONLibraryException as jde:
            printError("Underlying json library had a problem with the Assign.config.json file (see details below:)")
            print(str(jde))
            printError("Underlying json library had a problem with the Assign.config.json file (see details above)")
            print("\tWatch out for c:\\\\Top\\next when you really wanted C:\\\\Top\\\\next\n\n")
            sys.exit(1)

        # next, fixup anything that we want to adjust
        # by doing this here, we'll do this exactly once per file that we load
        fixupPaths(currentFile, configFileBaseDir)

    if SZ_NEXT_CONFIG_FILE_KEY in currentFile:
        recursiveFile = LoadConfigFile(
            currentFile[SZ_NEXT_CONFIG_FILE_KEY])
        # replace stuff in recursiveFile with any overriding values in currentFile:
        merge(recursiveFile, currentFile)
        currentFile = recursiveFile
    else:
        assert SZ_CONFIG_FILE_LIST_KEY not in currentFile
        currentFile[SZ_CONFIG_FILE_LIST_KEY] = list()

    currentFile[SZ_CONFIG_FILE_LIST_KEY].insert(0, fpConfigFile)

    return currentFile
