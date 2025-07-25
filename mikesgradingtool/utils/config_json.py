from collections import namedtuple
from collections.abc import MutableMapping
import functools
import json
import json.decoder
import os.path
import re
import typing

from jsmin import jsmin

from mikesgradingtool.utils.print_utils import printError, GradingToolError

@functools.lru_cache(1)
def get_app_config():
    gtc = GradingToolConfig()
    return gtc

SZ_DEST_DIR_SUFFIX_KEY = 'dest_dir_suffix'
SZ_ASSIGNMENTS_KEY = 'assignments'


KEY_INHERIT_FROM = "inherits_from"
KEY_STRING_REPLACEMENTS = "string_replacements"
KEY_STRINGS_TO_REPLACE = "strings_to_replace"
KEY_CONDITIONS = "conditions"
TOP_LEVEL_COURSES_KEY = "courses"
MEMO_REPLACEMENTS = "_cached_replacements"

class LazyCaseInsensitiveWrapper(MutableMapping):
    def __init__(self, source):
        if not isinstance(source, dict):
            raise TypeError("LazyCaseInsensitiveWrapper expects a dict as source")
        self._source = source
        self._lower_key_map = None
        self._wrapped_cache = {}

    def _build_key_map(self):
        self._lower_key_map = {
            k.lower(): k for k in self._source if isinstance(k, str)
        }

    def __getitem__(self, key):
        if not isinstance(key, str):
            return self._source[key]

        if self._lower_key_map is None:
            self._build_key_map()

        real_key = self._lower_key_map.get(key.lower())
        if real_key is None:
            raise KeyError(key)

        if real_key in self._wrapped_cache:
            return self._wrapped_cache[real_key]

        value = self._source[real_key]
        wrapped = self._wrap(value)
        self._wrapped_cache[real_key] = wrapped
        return wrapped

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            self._source[key] = value
            return

        if self._lower_key_map is None:
            self._build_key_map()

        key_lc = key.lower()
        real_key = self._lower_key_map.get(key_lc, key)

        self._source[real_key] = value
        self._lower_key_map[key_lc] = real_key
        self._wrapped_cache.pop(real_key, None)

    def __delitem__(self, key):
        if not isinstance(key, str):
            del self._source[key]
            return

        if self._lower_key_map is None:
            self._build_key_map()

        key_lc = key.lower()
        real_key = self._lower_key_map.pop(key_lc, None)
        if real_key is None:
            raise KeyError(key)

        del self._source[real_key]
        self._wrapped_cache.pop(real_key, None)

    def __iter__(self):
        if self._lower_key_map is None:
            self._build_key_map()
        return iter(self._lower_key_map.keys())

    def __len__(self):
        return len(self._source)

    def _wrap(self, value):
        if isinstance(value, dict):
            return LazyCaseInsensitiveWrapper(value)
        elif isinstance(value, list):
            return [self._wrap(v) for v in value]
        return value

    def __contains__(self, key):
        if not isinstance(key, str):
            return key in self._source

        if self._lower_key_map is None:
            self._build_key_map()

        return key.lower() in self._lower_key_map

    def __repr__(self):
        return f"<LazyCIWrapper {repr(self._source)}>"

    # -------- get_path and string expansion logic --------

    def get_path(self, path, delimiter="/"):
        parts = path.split(delimiter)
        current = self
        inherit_info_path = None
        path_so_far = []

        for i, part in enumerate(parts):
            if isinstance(current, LazyCaseInsensitiveWrapper):
                if KEY_INHERIT_FROM in current:
                    inherit_info_path = path_so_far[:-1] + [current[KEY_INHERIT_FROM]]
                try:
                    current = current[part]
                except KeyError:
                    current = None
            else:
                current = None

            path_so_far.append(part)

            if current is None:
                break

        if current is not None:
            return (self._maybe_expand_value(path, current), None)

        possible_prior_errors = ""

        if inherit_info_path:
            new_parts = inherit_info_path + parts[len(inherit_info_path):]
            results = self.get_path(delimiter.join(new_parts), delimiter)
            if results[1] is None:
                return results
            else:
                possible_prior_errors = "\n" + results[1]

        return (None, f"Config file lookup error: Couldn't find {path_so_far[-1:]} in {"/".join(path_so_far[:-1])}"
                        + possible_prior_errors)

    def _maybe_expand_value(self, path, value):
        if not isinstance(value, str):
            return value

        parts = path.split("/")
        if len(parts) < 2 or parts[0].lower() != TOP_LEVEL_COURSES_KEY:
            return value

        course_id = parts[1]
        courses = self[TOP_LEVEL_COURSES_KEY]
        course_obj = courses.get(course_id)
        if course_obj is None:
            return value

        replacements = self._get_string_replacements_for_course(course_obj)

        prev = None
        current = value
        while current != prev:
            prev = current
            try:
                current = current.format(**replacements)
            except KeyError:
                break  # fail gracefully if placeholders are missing

        return current

    def _get_string_replacements_for_course(self, course_obj):
        if MEMO_REPLACEMENTS in course_obj._source:
            return course_obj._source[MEMO_REPLACEMENTS]

        acc = {}
        visited = set()
        current = course_obj

        while isinstance(current, LazyCaseInsensitiveWrapper):
            obj_id = id(current._source)
            if obj_id in visited:
                break
            visited.add(obj_id)

            repl = current.get(KEY_STRING_REPLACEMENTS)
            if isinstance(repl, LazyCaseInsensitiveWrapper):
                conditions = repl.get(KEY_CONDITIONS, [])
                if self._conditions_met(conditions):
                    for k, v in repl.get(KEY_STRINGS_TO_REPLACE, {}).items():
                        if k not in acc:
                            acc[k] = v

            if KEY_INHERIT_FROM in current:
                courses = self.get(TOP_LEVEL_COURSES_KEY)
                current = courses.get(current[KEY_INHERIT_FROM])
            else:
                break

        course_obj._source[MEMO_REPLACEMENTS] = acc
        return acc

    def _conditions_met(self, conditions):
        for cond in conditions:
            if cond.get("condition") == "dir_exists":
                if not os.path.isdir(cond.get("dir", "")):
                    return False
        return True



# This is used for reading the app-wide JSON config file
# TODO use https://docs.python.org/3/library/functools.html#functools.cached_property to memoize the config settings
class GradingToolConfig:

    def __init__(self,fpConfig: str = None):
        if fpConfig is not None:
            self.fpgtConfig = fpConfig
        else:
            home = os.getenv('HOME')
            if home:
                self.gradingToolConfigDir = os.path.join(home, ".config", "mikesgradingtool")
            else:
                self.gradingToolConfigDir = os.path.join(os.path.expanduser("~"), ".config", "mikesgradingtool")

            self.fpgtConfig = os.path.abspath(os.path.join(self.gradingToolConfigDir, 'config.json'))

        self.LoadConfig()

    def LoadConfig(self):
        try:
            with open(self.fpgtConfig, encoding="utf8") as open_file:
                minified = jsmin(open_file.read(), quote_chars="'\"`")
                self.hive = LazyCaseInsensitiveWrapper(json.loads(minified))

                if "courses" not in self.hive:
                    printError("Loading config: did not find a top-level 'courses' object!!!!")

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


    # If there's a 'course' above the key and that course
    # contains 'course_dir_suffix' then concatenate that
    # onto the end of the key
    # Useful for a second section that works by mostly inheriting from
    # a base course, but this way the second section downloads homeworks
    # into a unique directory


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
        (val, err) = self.hive.get_path(key)
        if err:
            if default is not None:
                return default
            else:
                printError(err)
                raise Exception(err)
        else:
            return val

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
