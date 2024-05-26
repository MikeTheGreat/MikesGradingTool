import functools
import os

import diskcache as dc

the_persistent_cache = None

@functools.lru_cache(1)
def get_app_cache(verbose: bool = False):
    global the_persistent_cache

    fp_cache_dir = os.path.normcase(os.path.expanduser("~/.gradingtool/caches"))
    os.makedirs(fp_cache_dir, exist_ok=True)

    if not os.access(fp_cache_dir, os.W_OK):
        raise PermissionError(f"Directory {fp_cache_dir} is not writable.")

    the_persistent_cache = dc.Cache(fp_cache_dir)

    if verbose:
        print(f"diskcache location: {the_persistent_cache.directory} - delete this folder to clear the cache")
        print(f"\tKeys: {sorted(list(the_persistent_cache.iterkeys()))}")

    return the_persistent_cache

# Flush cache to disk if we used it (no-op if we didn't use it)
def close_app_cache():
    global the_persistent_cache

    if the_persistent_cache is not None:
        the_persistent_cache.close()
        the_persistent_cache = None


# keys = list(cache.iterkeys())
# print("Before: " )
# print(keys)
#
# # Setting a value with a 3-month expiration (approx 90 days)
# cache.set('key_10', 'value', expire=10)  # 3 minutes in seconds
#
# keys = list(cache.iterkeys())
# print("After: ")
# print(keys)
# # Getting a value
# value = cache.get('key')
# print(value)