# from dataclasses import dataclass
# import datetime
# import glob
# import json
# import os
# import pytz
# import re
# import shutil
# import subprocess
# import tempfile
# import time
# from tzlocal import get_localzone
# from collections import namedtuple
# from enum import Enum
# from pathlib import Path
# from typing import Callable, Optional
#
# import github
# from GradingTool.GitHubClassroom.GitHubClassroomHelper import call_shell, go_through_all_git_repos
# from GradingTool.utils.config_json import get_app_config, HWInfo, lookupHWInfoFromAlias
# from GradingTool.utils.misc_utils import cd, rmtree_remove_readonly_files
# from GradingTool.utils.my_logging import get_logger
# from GradingTool.utils.print_utils import printError, GradingToolError, print_list, print_color
# from colorama import Fore, Style, Back
# # docs: https://pygithub.readthedocs.io/en/latest/introduction.html
# from github import Github, GithubException
#
# logger = get_logger(__name__)
#
# SZ_COMMIT_PUSH_LOG_FILENAME = "GitCommitsAndGitHubPushes.txt"
#
# def test_PyGitHub(g):
#     # for org in g.get_user().get_orgs():
#     #     print(org.url)
#
#     print("Getting events: ")
#     for event in g.get_events():
#         print( f"Event\n\ttype=\"{event.type}\"\n\tid=\"{event.id}\"\n\tcreated_at=\"{event.created_at}\"\n\tevent.repo.name=\"{event.repo.name}\"\n\tevent.repo.html_url=\"{event.repo.html_url}\n\tevent.actor.login=\"{event.actor.login}\"\"")
#     print("done printing events")
#
# StudentLocalRepo = namedtuple('StudentLocalRepo', 'name dest_dir timestamp branches')
#
#
# def get_matching_orgs_from_current_user(g, re_org_name: re.Pattern):
#     orgs = [org for org in g.get_user().get_orgs() if re_org_name.search(org.url)]
#     return orgs
#     # for org in g.get_user().get_orgs():
#     #     if not re_org_name.search(org.url):
#     #         print("\tOrganization does NOT match - skipping all repos in it")
#     #         continue
#
#
# def get_matching_repos_from_org(org, re_repo: re.Pattern):
#     # This will NOT print out dirs that exist but don't match the regex
#     # Do we want to print non-matches?  It might make it easier to debug problems
#     # repos = list(org.get_repos(type='member', sort='full_name', direction='asc'))
#     # all_repos = list(org.get_repos(type='member', sort='full_name', direction='asc'))
#     # for repo in all_repos:
#     #     print(repo)
#
#     repos = [repo for repo \
#              in org.get_repos(type='member', sort='full_name', direction='asc') \
#              if re_repo.search(repo.name)]
#     return repos
#
#
# def do_fnx_per_github_repo(g: github.Github, course: str, hw_name: str, dest_dir_from_cmd_line: str,
#                            fnx_per_assign: Callable[[dict], bool],
#                            fnx_per_repo: Callable[[dict, github.Repository.Repository, str, Optional[bool]], bool],
#                            search_for_existing_repos: bool = False):
#     # "" Call fnx once per repo, for a given course and homework assignment (or "all", for all assignments)
#     #
#     # :param course: internal name for a course.  used to look up the relevant hive in gradingtool.json,
#     #                 under courses/{course}
#     # :param hw_name: EITHER:
#     #                 key used to find hw-specific info in courses/{course}/assignments
#     #                 OR:
#     #                 the word 'all', to indicate that all assignments within the course should be processed
#     # :param dest_dir_from_cmd_line: optional (None); if not none then it's a absolute path to a directory in the file system.  This
#     #                 will be passed to fnx.  Ex: Used by 'download homeworks' to specify an alternate place to put
#     #                 the homeworks
#     #                 NOTE: Ignored if hw_name is 'all'
#     #                 NOTE: If this is "NO_DIR_NEEDED" then this function won't require a dest dir
#     # :param fnx_per_assign:  Called with the hive for an individual assignment.  Return True to process it, False to skip
#     #                 Can be None (in which case all assignments will be processed)
#     #                 Intended for filtering malformed assignments when hw_name is 'all'
#     # :param fnx_per_repo:
#     #                 Return True if processing should continue, return False to stop processing for this assignment
#     #                 param= dict = the hive for the assignment
#     #                 param= PyGitHub Repository object
#     #                 param= StudentLocalRepo
#     #                     destination dir for this particular student for this particular homework assignment, may be None
#     #
#     # :return: None
#     # ""
#
#     dir_required = dest_dir_from_cmd_line != "NO_DIR_NEEDED"
#
#     config = get_app_config()
#     assignments, sz_re_org_name = config.verify_keys(
#         [
#             f"assignments",
#             f"github/org_name",
#         ],
#         base=f"courses/{course}/")
#
#     re_org_name = re.compile(sz_re_org_name)
#
#     # After this, one of three things is true:
#     #   1) hw_to_download is a list of all the homework project
#     #   2) hw_to_download is a list of exactly one homework project
#     #   3) EnvOptions.HOMEWORK_NAME didn't match anything and we exit
#
#     def add_name_into_hw(name, hw):
#         hw['name'] = name
#         return hw
#
#     hw_name = hw_name.lower()
#     if hw_name == 'all':
#         # we're going to make a new list with all the projects
#         hw_name = 'all'
#         hw_to_download = [add_name_into_hw(hw_nom, hw) for hw_nom, hw in assignments.items()]
#     else:
#         # we're going to make a new list that should match just one
#         # homework assignment
#         hw_to_download = [add_name_into_hw(hw_nom, hw) for hw_nom, hw in assignments.items() if
#                           hw_nom.lower() == hw_name]
#
#     if not hw_to_download:  # if list is empty
#         raise GradingToolError(f"{hw_name} doesn't match any of the have any assignments in {course}")
#
#     # speed up searches:
#     for hw in hw_to_download:
#         if "github" not in hw:
#             raise GradingToolError(
#                 "Couldn't find GitHub config info for this assignment.  Is this a GitHub assignment?")
#         if "sz_re_repo" not in hw["github"]:
#             raise GradingToolError(
#                 "Couldn't find sz_re_repo for GitHub for this assignment - make sure that gradingTool.config is set up correctly!")
#
#         hw["re_repo"] = re.compile(hw["github"]["sz_re_repo"])
#
#     orgs = get_matching_orgs_from_current_user(g, re_org_name)
#
#     for hw in hw_to_download:
#         result = True
#
#         dest_dir = None  # reset for each assignment
#         if dir_required:
#             if hw_name != 'all' and dest_dir_from_cmd_line is not None:
#                 dest_dir = dest_dir_from_cmd_line
#             else:
#                 dest_dir = config.getKey(f"courses/{course}/assignments/{hw['name']}/dest_dir")
#
#             global dest_dir_HACK
#             # this is a hack to pass the root dir back when we're downloading based on the config json
#             if dest_dir is not None:
#                 dest_dir_HACK = dest_dir
#
#         #  f"Must have a destination dir (either in the gradingtool.json config file or as a command-line parameter"
#
#         sz_re_hw_repos = config.getKey(f"courses/{course}/assignments/{hw['name']}/github/sz_re_repo", "")
#         if sz_re_hw_repos == "":
#             print(
#                 f"Homework assignment {hw['name']} does not have a RegEx to match repos to! (missing github/sz_re_repo)")
#             continue
#
#         # if fnx_per_assign is not None and not fnx_per_assign(hw):
#         #     continue # go on to next assignment
#
#         for org in orgs:
#             print(f"\nDownloading the repo list for {hw['name']}")
#             re_hw_repos = re.compile(sz_re_hw_repos)
#             repos = get_matching_repos_from_org(org, re_hw_repos)
#
#             # repo_count = 0
#             for repo in repos:
#                 # if repo_count >= 3:
#                 #     break
#                 # repo_count = repo_count + 1
#
#                 student_name = re_hw_repos.sub(' ', repo.name).strip()
#
#                 print(f"\n{'-' * 5} {(student_name + ' ').ljust(20, '-')}{(' ' + repo.name).rjust(40, '-')} {'-' * 10}")
#
#                 if dest_dir != None:
#                     student_dest_dir = os.path.join(dest_dir, student_name)
#                 else:
#                     student_dest_dir = None
#
#                 branches = []
#
#                 # if we want to find & update existing repos
#                 # (which may have been moved to a subdir of dest_dir)
#                 # then we'll search here
#                 # & replace student_dest_dir with the existing dir
#                 #       (in case it's been moved under a canvas directory, for example)
#                 if search_for_existing_repos:
#                     search_for = os.path.join(dest_dir, "**", student_name) + os.sep
#                     existing_repos = glob.glob(search_for, recursive=True)
#                     if len(existing_repos) > 0:
#                         if len(existing_repos) > 1:
#                             printError(
#                                 f"Found multiple existing repos for {student_name} - ignoring them all and downloading a new copy")
#                         else:
#                             student_dest_dir = existing_repos[0]
#                             print(f"\tFound existing repo: {student_dest_dir}")
#
#                             with(cd(student_dest_dir)):
#                                 branches = get_remote_branches_list()
#
#                 student_info = StudentLocalRepo(student_name, student_dest_dir, datetime.datetime.now(), branches)
#
#                 # figure out if the main branch has changed since this was last tagged as 'graded'
#                 #
#                 #    On GitHub, look for the most recent 'graded by instructor' tag
#                 #    and compare the datetime to the HEAD.
#                 #       Only call the function if HEAD is more recent than the tag
#                 #           (i.e., if the student pushed something since this was last graded)
#                 #       OR call the function if there is no tag
#                 #           (i.e., the repo has never been graded)
#                 repo_new_or_changed_since_most_recent_grading = True
#                 tags = list(filter( lambda t: "GradedByInstructor" in t.name, repo.get_tags()))
#
#                 if len(tags) != 0:
#                     tags.sort(reverse=True, key = lambda t: t.last_modified)
#                     most_recently_graded = tags[0]
#                     # Again, PyGitHub didn't consistently return the last_modified time:
#                     # dt_most_recently_graded = datetime.datetime.strptime(most_recently_graded.commit.last_modified, "%a, %d %b %Y %H:%M:%S %Z" )
#                     dt_most_recently_graded = datetime.datetime.strptime(most_recently_graded.name,
#                                                                          "GradedByInstructor-%Y-%m-%d-%H-%M-%S")
#
#                     branches = repo.get_branches()
#                     for branch in branches:
#                         # force retrieval of the commit info
#                         # c.f. https://github.com/PyGithub/PyGithub/issues/1967
#                         HEAD = repo.get_commit( str(branch.commit.sha))
#
#                         if branch.name == repo.default_branch: # branch.name == "master" or branch.name == "main":
#                             dt_most_recent_commit = datetime.datetime.strptime(HEAD.commit.last_modified, "%a, %d %b %Y %H:%M:%S %Z" )
#
#                             if dt_most_recently_graded > dt_most_recent_commit:
#                                 repo_new_or_changed_since_most_recent_grading = False
#
#                 result = fnx_per_repo(hw, repo, student_info, repo_new_or_changed_since_most_recent_grading)
#                 if result == False: break
#             if result == False: break
#         if result == False: break  # this will get us to the next homework assignment
#
#
# def fn_github_delete_student_repos(args):
#     course: str = args.COURSE
#
#     config = get_app_config()
#     sz_re_org_name, do_not_delete, sz_re_student_repos = config.verify_keys(
#         [
#             "org_name",
#             "do_not_delete",
#             "sz_re_student_repos"
#         ],
#         base=f"courses/{course}/github")
#
#     git_api_key = config.verify_keys(["github/api_key"])
#     g = Github(git_api_key)
#
#     re_org_name = re.compile(sz_re_org_name)
#
#     # this is a safety feature so you don't accidentallyk delete your repos when
#     # cleaning out student repos after the term ends
#     re_do_not_delete = [re.compile(pattern) for pattern in do_not_delete]
#
#     re_student_repos = re.compile(sz_re_student_repos)
#
#     orgs = get_matching_orgs_from_current_user(g, re_org_name)
#     if len(orgs) != 1:
#         raise GradingToolError(
#             f"Found more than 1 matching course (GitHub organization) when searching with {sz_re_org_name}")
#     org = orgs[0]
#
#     def delete_users(print_without_deleting=True):
#         print(org.url)
#         repos = get_matching_repos_from_org(org, re_student_repos)
#         for repo in repos:
#             for safety_check in re_do_not_delete:
#                 if safety_check.search(repo.name):
#                     print(
#                         f"\t{repo.name}  {'*' * 5}  THIS REPO IS IN THE SAFETY LIST. => NOT <= DELETING IT  {'*' * 5}")
#                     break
#             else:
#                 # we only get here if the safety_check loop finishes normally
#                 # meaning that we did NOT break out of the loop because
#                 # we found a matching check pattern
#
#                 if print_without_deleting:
#                     print(f"\t{repo.name.ljust(40)}  STUDENT REPO - will be deleted, after confirmation")
#                 else:
#                     print(f"\t{repo.name.ljust(40)} - DELETING NOW")
#                     try:
#                         repo.delete()
#                     except GithubException as ghe:
#                         print(f"had a problem with {repo.html_url}")
#                         print(repr(ghe))
#                         # raise # rethrow
#
#     print("\nFirst, let's see the repos that will be deleted (or not):\n")
#
#     delete_users(print_without_deleting=True)
#
#     print(
#         "\nIf you want to delete all the repos please type in " + Style.BRIGHT + Fore.RED + Back.BLACK + "\nDelete\n" + Style.RESET_ALL + "(this is case sensitive), followed by Enter/Return"
#     )
#     print("Type anything else (or leave it blank) and press Enter/Return to cancel")
#
#     confirm = input("")
#
#     if confirm == "Delete":
#         print(Style.BRIGHT + Fore.RED + "\n\nDELETING REPOS NOW:\n" + Style.RESET_ALL)
#         delete_users(print_without_deleting=False)
#     else:
#         print("Operation canceled - NO CHANGES MADE")
#
#     #    #     print(dir(repo))
#
#
# dest_dir_HACK = ""
#
#
# @dataclass(repr=False, order=True)
# class GitEvent:
#     when: datetime.datetime # dataclass will sort by this field first
#     type: str
#     id: str
#     author: str
#     other_details: [str]
#
#     def __repr__(self):
#         other_deets = "None"
#         if self.other_details is not None:
#             other_deets = ""
#             for deet in self.other_details:
#                 other_deets += "\n\t\t" + deet
#         return f"Event\n\ttype=\"{self.type}\"\n\tid=\"{self.id}\"\n\tdate/time (local)=\"{self.when.astimezone()}\"\n\tby whom?=\"{self.author}\"\n\tother details:{other_deets}"
#
# def utc_to_local_string(dtUTC):
#
#     config = get_app_config()
#     tz_to_use = config.getKey("app-wide_config/preferred_time_zone", "") # if not found then return ""
#     if tz_to_use != "":
#         tz_local = pytz.timezone(tz_to_use)
#     else: # datetime.datetime.now(datetime.timezone.utc).astimezone()
#         tz_local = get_localzone()
#
#     local_time = dtUTC.astimezone(tz_local)
#     sz_dt = local_time.strftime("%a, %b %d %Y %H:%M:%S %Z")
#     return sz_dt
#
# def log_repo_events(repo, dest_dir):
#     events = []
#
#     for event in repo.get_events():
#
#         other_details = None
#         if event.type == "PushEvent":
#             other_details = {'commits_only_the_first_20': event.payload['commits'] }
#
#         nextEvent = GitEvent(event.created_at.replace(tzinfo=datetime.timezone.utc), event.type, event.id, event.actor.login, other_details)
#         events.append( nextEvent )
#
#     repos =repo.get_commits()
#     for commit in repos:
#         # There seems to be a (maybe?) race condition
#         # If we go through the raw_data first then the date ends up being correct
#         # If we wait & just ask for commit.last_modified without this then
#         # all the commits will use the datetime for the most recent commit
#         # This is all a guess, but seems to work (???????????????????????)
#         json.dumps(commit.raw_data, indent=4)
#
#         # datetime is actually a string (in UTC)
#         when = datetime.datetime.strptime(commit.last_modified, "%a, %d %b %Y %H:%M:%S %Z")
#         when = when.replace(tzinfo=datetime.timezone.utc)
#
#         name = commit.commit.author.name
#         if commit.author is not None and commit.author.login != commit.commit.author.name:
#             name += " ( " + commit.author.login + " )"
#
#         nextEvent = GitEvent(when, \
#                              "Commit", \
#                              commit.commit.sha, \
#                              name, \
#                              ["Commit message: " + commit.commit.message, \
#                               commit.commit.html_url, \
#                               "Parents: " + str(commit.parents)])
#         events.append( nextEvent )
#
#     events.sort()
#
#     # print(f"Events and commits for repo\n\trepo.name=\"{repo.name}\"\n\trepo.html_url=\"{repo.html_url} ")
#     # for event in events:
#     #     print(event)
#
#     def jsonify(field, value):
#         if field == "when":
#             return utc_to_local_string(value)
#         else:
#             return value
#
#     fpEvents = os.path.join(dest_dir, SZ_COMMIT_PUSH_LOG_FILENAME)
#     with open(fpEvents, "w", encoding="utf-8") as file:
#         events_jsonable = [ {k: jsonify(k,v) for (k, v) in e.__dict__.items() } for e in events]
# #         print(json.dumps(events_jsonable, indent=4))
#         json.dump(events_jsonable, file, indent=4)
#
#     pass # left here to put a breakpoint on it :)
#
#
# def fn_github_download_homework(args):
#     global dest_dir_HACK
#
#     hw_info = lookupHWInfoFromAlias(args.COURSE)
#     if hw_info is not None:
#         course = hw_info.course
#         hw_name = hw_info.hw
#         dest_dir = hw_info.fp_dest_dir
#     else:
#         course = args.COURSE  # formerly COURSE
#         hw_name = args.HOMEWORK_NAME
#         dest_dir = args.DEST
#
#     student_name = args.STUDENT_NAME
#     new_only = args.NEWONLY
#     verbose = args.VERBOSE
#
#     new_student_projects = list()
#     updated_student_projects = list()
#     unchanged_student_projects = list()
#
#     def download_homework(hw, \
#                           repo, \
#                           student_info: StudentLocalRepo, \
#                           repo_new_or_changed_since_most_recent_grading: bool = True):
#
#         # If we have a name to filter for, but this repo isn't the target
#         # then skip it
#         if student_name != "" and student_name != student_info.name:
#             # Don't add it to any lists, since we didn't actually process it
#             print(f"\tLooking for \"{student_name}\" but \"{student_info.name}\" did not match - ignoring and continuing on")
#             return;
#
#         if new_only and repo_new_or_changed_since_most_recent_grading == False:
#             print("\tRepo is UNchanged since the last time we tagged it as graded (skipping the pull)")
#             unchanged_student_projects.append(student_info)
#             return
#         try:
#             if os.path.isdir(student_info.dest_dir):
#                 # if there's already a .git repo there then refresh (pull) it
#                 # instead of cloning it
#
#                 repo_exists = False
#                 for root, dirs, files in os.walk(student_info.dest_dir):
#                     for dir in dirs:
#                         if dir == '.git':
#                             git_dir = os.path.join(root, dir)
#                             logger.debug("Found an existing repo at " + git_dir)
#
#                             with cd(root):
#                                 # Note that update_branches will update the current branch AND any others too
#                                 (repo_changed, branches) = git_update_branches(student_info.branches)
#                                 if repo_changed:
#                                     print("\tRepo HAS changed since the last time we updated (pulled) it")
#                                     student_info = StudentLocalRepo(student_info.name, \
#                                                                     student_info.dest_dir, \
#                                                                     student_info.timestamp, \
#                                                                     branches) # update list
#                                     updated_student_projects.append(student_info)
#                                 else:
#                                     print("\tRepo is UNchanged since the last time we updated (pulled) it")
#                                     unchanged_student_projects.append(student_info)
#
#                             log_repo_events(repo, student_info.dest_dir)
#
#                             # we've updated it, so we're done - stop looking for repos to update
#                             return
#             else:
#                     # If we need to clone (download) any projects we'll put them
#                     # in the temp_dir, then move the dir containing .git (and
#                     # all subdirs) to the place where we want them to end up
#                     logger.debug("local copy doesn't exist (yet), so clone it")
#                     with tempfile.TemporaryDirectory() as temp_dir_root:
#                         # clone the repo into the project
#                         # The ssh connection string should look like:
#                         #   git@ubuntu:root/bit142_assign_1.git
#                         temp_dir = os.path.join(temp_dir_root, "TEMP")
#                         os.makedirs(temp_dir)
#
#                         with cd(temp_dir):  # this will pushd to the temp dir
#                             # --config core.filemode=false will make sure that all the repos we clone
#                             # don't care about the permission bits
#                             # (Otherwise we'll get merge conflicts b/c of file mode changes)(???)
#                             call_shell(f"git clone --config core.filemode=false {repo.clone_url}", print_output_on_error=True)
#
#                             # next, go find the .git dir:
#                             found_git_dir = False
#                             for root, dirs, files in os.walk(temp_dir):
#                                 for dir in dirs:
#                                     if dir == '.git':
#                                         new_git_dir = root
#                                         logger.debug("Found the git dir inside " + new_git_dir)
#                                         found_git_dir = True
#                                     if found_git_dir: break
#                                 if found_git_dir: break
#
#                             if not found_git_dir:
#                                 raise GradingToolError("Despite cloning new repo, couldn't find git dir!")
#
#                             shutil.copytree(new_git_dir, student_info.dest_dir)
#
#                             # add the repo into the list of updated projects
#                             new_student_projects.append(student_info)
#
#                             log_repo_events(repo, student_info.dest_dir)
#
#         except Exception as e:
#             printError(f"Something went wrong trying to update or clone the repo of {student_info.name}\nError:\n{str(e)}")
#
#
#     config = get_app_config()
#
#     if hw_name == 'all':
#         print(f"\nAttempting to download all homework assignments for {course}")
#     else:
#         print(f"\nAttempting to download homework assignment \"{hw_name}\" for {course}")
#
#     try:
#         git_api_key = config.verify_keys(["github/api_key"])
#     except KeyError as ke:
#         printError("Couldn't find API Key for GitHub - make sure that gradingTool.config is set up correctly!")
#     g = Github(git_api_key)
#
#     #test_PyGitHub(g)
#     #return
#
#     dest_dir_HACK = ""
#     do_fnx_per_github_repo(g, course, hw_name, dest_dir, None, download_homework, \
#                            search_for_existing_repos=True)
#
#     if hw_name == 'all':
#         dest_dir = ''  # force output to list complete paths
#     else:
#         dest_dir = dest_dir_HACK
#
#         if dest_dir[-1:] != os.sep and dest_dir[-1:] != os.altsep:
#             dest_dir = dest_dir + os.sep
#
#     print("\n" + "=" * 20 + "\n")
#
#     # sortStudentInfoByName = lambda s: s.name.lower()
#
#     # Note: s.dest_dir includes student name as the last part of the path
#     sortStudentInfoByAssign = lambda s: s.dest_dir.lower()
#
#     sz_unchanged = "The following student repos existed previously, and have not changed: "
#     if new_only:
#         sz_unchanged += " (unchanged repos weren't pulled, and may not be present locally)"
#
#     # [:-1] will leave off the trailing '/'
#     dir_list = [local_repo.dest_dir[:-1] + get_multiple_branches_suffix(local_repo.branches) for local_repo in sorted(unchanged_student_projects, \
#                                                              key=sortStudentInfoByAssign)]
#     print_list(dest_dir, dir_list, \
#                Fore.GREEN, sz_unchanged)
#
#     dir_list = [local_repo.dest_dir[:-1] + get_multiple_branches_suffix(local_repo.branches) for local_repo in sorted(new_student_projects, \
#                                                              key=sortStudentInfoByAssign)]
#     print_list(dest_dir, dir_list, \
#                Fore.RED, "The following student repos are newly downloaded:", \
#                "No new student repos have been downloaded")
#
#     dir_list = [local_repo.dest_dir[:-1] + get_multiple_branches_suffix(local_repo.branches) for local_repo in sorted(updated_student_projects, \
#                                                              key=sortStudentInfoByAssign)]
#     print_list(dest_dir, dir_list, \
#                Fore.YELLOW, "Updated the following student repos:", \
#                "None of the existing student repos have been updated")
#
#     if hw_name != 'all':
#         print(f"Repos can be found in:\n\t{dest_dir}")
#
# def get_multiple_branches_suffix( branches: [str]):
#     if len(branches) <= 1:
#         return ""
#     else:
#         return "MULTIPLE BRANCHES: ".rjust(30) + str(branches)
#
# # PRECONDITION: Already called fetch for this branch
# #
# # Returns true if the branch changes when we pull it
# # Also returns true if something goes wrong
# #       (in the hopes that it gets added to the 'needs more attention' list)
# def git_merge_current_branch(branch):
#     # in order to know if the pull actually
#     # changes anything we'll need to compare
#     # the SHA ID's of the HEAD commit before & after
#     sz_std_out, sz_std_err, ret_code = call_shell(
#         "git show-ref --head --heads HEAD", False, exit_on_fail=False)
#     if sz_std_out == "":
#         printError("Error with repo - couldn't find HEAD commit")
#         return True
#     if ret_code != 0 and ret_code != 1:
#         return True
#
#     sha_pre_pull = sz_std_out.strip().split()[0].strip()
#
#     # Update the repo
#     # Don't need to pull since we'll do just one fetch prior to all the merges
#     # sz_std_out, sz_std_err, ret_code = call_shell("git pull --tags --rebase --autostash -Xtheirs",
#     #                                               print_output_on_error=True, exit_on_fail=False)
#
#     # Update the repo by rebasing previously fetched changes
#     sz_std_out, sz_std_err, ret_code = call_shell(f"git rebase --autostash -Xtheirs {branch}",
#                                                     print_output_on_error=True, exit_on_fail=False)
#     if ret_code != 0 and ret_code != 1:
#         return True
#
#     sz_std_out, sz_std_err, ret_code = call_shell(
#         "git show-ref --head --heads HEAD", False, exit_on_fail=False)
#     if ret_code != 0 and ret_code != 1:
#         return True
#
#     sha_post_pull = sz_std_out.strip().split()[0].strip()
#
#     return sha_pre_pull != sha_post_pull
#
# def get_remote_branches_list():
#     cmd_list_branches = "git for-each-ref refs/remotes/origin --format=%(refname:short)" # --no-merged
#
#     # Get list of branches that are not the same as HEAD
#     sz_std_out, sz_std_err, ret_code = call_shell(cmd_list_branches, False, exit_on_fail=False)
#     if ret_code != 0 and ret_code != 1:
#         raise GradingToolError(f"Error with repo - couldn't use for-each-ref to get list of branches (post-fetch)")
#
#     branches = sz_std_out.splitlines()
#
#     # Remove the bogus 'origin/HEAD' entry:
#     branches = [item for item in branches if "HEAD" not in item]
#
#     return sorted(branches)
#
# # Returns a tuple:
# # Slot 0 is a boolean:
# #       true if the number of branches has changed
# #       false if the number of branches has NOT changed
# # Slot 1 is the number of branches
#
# # Note that update_branches will update the current branch AND any others too
# def git_update_branches(branches_original):
#     branches_changed = False
#
#     # Remember which branch we're on
#     # (so we can switch back to it after getting all other branches, if any)
#     sz_std_out, sz_std_err, ret_code = call_shell(
#         "git rev-parse --abbrev-ref HEAD", False, exit_on_fail=False)
#     if sz_std_out == "" or ret_code != 0 and ret_code != 1:
#         raise GradingToolError(f"Error with repo - couldn't find HEAD commit")
#
#     original_branch = sz_std_out
#
#     # Run git fetch to make sure that we're up to date with GitHub
#     # This will fetch ALL branches (on all repos - there should be only 'origin' which points to GitHub)
#     sz_std_out, sz_std_err, ret_code = call_shell(
#         "git fetch --all --tags", False, exit_on_fail=False)
#     # std_out should be empty on success
#     if ret_code != 0 and ret_code != 1:
#         raise GradingToolError(f"Error with repo - couldn't run git fetch")
#
#     # Get list of branches that are not the same as HEAD
#     branches = get_remote_branches_list()
#
#     # if the list of branches has changed, then remember that:
#     if branches_original != branches:
#         branches_changed = True
#
#     regex = re.compile("fatal: a branch named '(.*)' already exists", flags=re.IGNORECASE)
#
#     # Download each of the branches:
#     for branch_with_remote in branches:
#         cmd = "git switch --track " + branch_with_remote
#         sz_std_out, sz_std_err, ret_code = call_shell( cmd, False, exit_on_fail=False)
#
#         match = re.search(regex, sz_std_err)
#         if match:
#             branch_without_remote = match.group(1)
#             # branch already exists, so update it; has it changed since last pull?
#             sz_std_out, sz_std_err, ret_code = call_shell(f"git switch {branch_without_remote}", True, exit_on_fail=False)
#             if ret_code != 0 and ret_code != 1:
#                 raise GradingToolError(
#                     f"Couldn't change to branch {branch_with_remote} in order to do the update")
#             if git_merge_current_branch(branch_with_remote) == True:
#                 branches_changed = True
#         elif sz_std_out == "" or ret_code != 0 and ret_code != 1:
#             raise GradingToolError(f"Error with repo - couldn't switch to branch: " + branch_with_remote)
#         else: # then we must have created the branch brand-new, which changes the repo
#             branches_changed = True
#
#     # Finally, switch back to the original branch:
#     sz_std_out, sz_std_err, ret_code = call_shell("git switch " + original_branch, False, exit_on_fail=False)
#     if sz_std_out == "" or ret_code != 0 and ret_code != 1:
#         raise GradingToolError(f"Error with repo - couldn't switch back to original branch: {original_branch}")
#
#     return (branches_changed, branches)
#
#
# def github_grading_list(config, verbose, course, hw_name, dest_dir=None):
#     hw_hive_base = f"courses/{course}/assignments/{hw_name}"
#     hw, assign_dir = config.verify_keys([
#         hw_hive_base,
#         f"{hw_hive_base}/dest_dir"])
#
#     # if full_name isn't defined then use the course's/hw's key
#     course_full_name = config.getKey(f"courses/{course}/full_name", course)
#     hw_full_name = config.getKey(f"courses/{course}/assignments/{hw_name}/full_name", hw_name)
#
#     tag = config.getKey("github/grading_list/tag")
#
#     # Note: verify_keys will throw an exception if the dest_dir key is missing
#     # regardless of whether we provide this parameter or not
#     if dest_dir is not None:
#         assign_dir = dest_dir
#
#     if not os.path.exists(assign_dir):
#         printError(f"Grading list for {hw_name}: No folder found at {assign_dir}")
#         return
#
#     print(f" ===== {course_full_name} - {hw_full_name} " + "=" * 20)
#
#     grading_list = grade_list_collector()
#     grading_list_collector = grading_list.generate_grading_list_collector(tag)
#     grading_list.verbose = verbose
#
#     go_through_all_git_repos(assign_dir, grading_list_collector, print_student_name=False)
#
#     if verbose:
#         print_list(assign_dir + os.sep, grading_list.graded, \
#                Fore.LIGHTCYAN_EX,
#                "\tThe following items have been graded (and haven't been updated since they were graded):",
#                    verbose=verbose,
#                    indent="\t\t")
#
#     print_list(assign_dir + os.sep, grading_list.new_student_work_since_grading, \
#                Fore.LIGHTYELLOW_EX, "\tThe following items have been " \
#                                     "re-submitted by students since grading:", verbose=verbose,
#                                     indent="\t\t")
#
#     print_list(assign_dir + os.sep, grading_list.ungraded, \
#                Fore.RED, "\tThe following items haven't " \
#                          "been graded yet:", verbose=verbose,
#                          indent="\t\t")
#
#     num_printed = len(grading_list.new_student_work_since_grading) + len(grading_list.ungraded)
#     if verbose:
#         num_printed += len(grading_list.graded)
#     return num_printed
#
#
# def fn_github_grading_list(args):
#
#     hw_info = lookupHWInfoFromAlias(args.COURSE)
#     if hw_info is not None:
#         course = hw_info.course
#         hw_name = hw_info.hw
#         dest_dir = hw_info.fp_dest_dir
#     else:
#         course = args.COURSE  # formerly COURSE
#         hw_name = args.HOMEWORK_NAME
#         dest_dir = args.DEST
#
#     verbose = args.VERBOSE
#
#     config = get_app_config()
#
#     if hw_name != 'all':
#         github_grading_list(config, verbose, course, hw_name, dest_dir)
#     else:
#         print(f"\nGenerating grade reports for all homework assignments in {course}")
#
#         hw_hive = config.verify_keys([f"courses/{course}/assignments/"])
#         for hw_name, hw in hw_hive.items():
#             num_printed = github_grading_list(config, verbose, course, hw_name, dest_dir)
#             # if not verbose and num_printed > 0:
#             #     print()  # blank line to separate from next assignment
#
# def fn_github_rate_limit_info(args):
#     config = get_app_config()
#     git_api_key = config.verify_keys(["github/api_key"])
#     g = Github(git_api_key)
#     limits = g.get_rate_limit()
#
#     # Reset timestamp appears to be in UTC timezone, but it's a 'naive' object without a tzinfo object
#     reset_aware = pytz.utc.localize(limits.core.reset).astimezone()
#     reset_time = reset_aware.strftime("%I:%M:%S %p (on %A, %b %d, %Y)")
#     print(f"Rate limit info\n\tRate Limit: {limits.core.limit}\n\tRequests Remaining: {limits.core.remaining}\n\tReset at: {reset_time}")
#
# class Mode(Enum):
#     Commit = "Commit"
#     Tag = "Tag"
#
#
# def extract_sha_and_datetime(tagOrCommit, mode: Mode):
#     # ""Given a Git stdout message for a tag or commit, extract
#     # the SHA-1 ID for the commit and the date of the underlying commit""
#
#     # this was copied from an older project, which is why it's different than anything else
#
#     # ~0 asks for the 0th last commit (i.e., this one)
#     #   for tags it'll get past the tag and talk about the commit itself
#     #   for 'head' it'll no-op
#     if mode == Mode.Commit:
#         rgCmdLine = f'git show -s --format="%H-%cd" {tagOrCommit}~0'.split()
#     elif mode == Mode.Tag:
#         # to get the most recent tag, no matter what the timestamp is after it:
#         # The * in front of objectname is very important because it 'dereferences' the tag, and gets the objectname (SHA hash)
#         # for the underlying (real) commit, instead of for the tag itself
#         rgCmdLine = f"git for-each-ref --count=1 --sort=-creatordate --format='%(*objectname)-%(creatordate)' refs/tags/*{tagOrCommit}*".split()
#         # Adding %(refname) to format will be useful for debugging purposes, but can be left out otherwise
#     else:
#         raise GradingToolError(f"extract_sha_and_datetime was given a mode that isn't recognized: {mode}")
#
#     # if things go ok then there will be no output on stderr, and any
#     # readline()'s would block.
#     # instead, check the first line for the word 'fatal' to detect error
#     p = subprocess.Popen(rgCmdLine, \
#                          stderr=subprocess.STDOUT, \
#                          stdout=subprocess.PIPE)
#     try:
#         # Did git report a fatal error?
#         output = p.stdout.readline().strip().decode("utf-8", errors='replace').strip(' \t\n\'')
#         timestampStart = output.lower().find("fatal")
#         if timestampStart != -1 or len(output) == 0:
#             logger.error("Fatal error - found 'fatal' in tag/commit message")
#             logger.debug("tag/commit message:\n" + output)
#             return None, None
#
#         if p.returncode and p.returncode != 0 and p.returncode != 1:
#             logger.error(
#                 "extract_sha_and_datetime: Unable to find tag.  Instead got returncode " + p.returncode if p.returncode else "None!")
#             return None, None
#
#         # otherwise we're expecting <SHA-1> <date>
#         timestampStart = output.find("-")
#         currentYear = datetime.datetime.now().year # 4 digits
#         timestampEnd = output.rfind(str(currentYear))
#
#         if mode == Mode.Commit:
#             SHA_commit = output[1:timestampStart]  # trim off the " at the start
#         elif mode == Mode.Tag:
#             SHA_commit = output[0:timestampStart]
#         logger.debug('Found commit, SHA-1=' + SHA_commit)
#
#         #print('Raw date for commit:' + output + " loc: " + str(timestampStart) )
#
#
#         # Fri Mar 27 22:33:35 2020 -0700
#         # The remainder is the time, minus the '-0700'/'+0800' at the end:
#         date_str = output[timestampStart + 1:timestampEnd+4].strip()
#
#         #print('\tStripped date for commit>>' + date_str + "<<")
#
#         # Fri Mar 27 22:33:35 2020
#         dt = datetime.datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
#
#         logger.debug('Resulting date object::' + str(dt))
#
#         return SHA_commit, dt
#     finally:
#         p.terminate()
#
#
#
# def renumber_current_tag(target_tag):
#     sz_stdout, sz_stderr, ret = run_command_capture_output( \
#         "git for-each-ref refs/tags/" + target_tag)
#
#     if sz_stdout:
#         logger.debug("Existing tag already found for " + target_tag \
#                      + " in " + os.getcwd())
#
#         # Get the SHA of the current tag (the one without the numbers)
#         # Remember that this is the SHA of the tag itself,
#         # NOT the commit that it's attached to
#         tags = sz_stdout.strip().split("\n")
#         if len(tags) > 1:
#             logger.error("Found more than 1 matching tag: " + sz_stdout)
#
#         current_tag = tags[0]
#         loc = current_tag.find(" ")
#         sha_tag = current_tag[:loc]
#
#         # already filtered list for the desired tag
#         # in the 'git for-each-ref' step
#         sz_stdout, sz_stderr, ret = run_command_capture_output( \
#             "git for-each-ref refs/tags/" + target_tag + "*")
#
#         # get the highest number prior tag
#         # by going through all of them
#         tags = sz_stdout.strip().split("\n")
#         highest_suffix = 0
#         for next_tag in tags:
#             loc = next_tag.find(target_tag)
#             sz_last_tag = next_tag[loc:]  # get the whole tag, whatever it is
#             suffix = next_tag[loc + len(target_tag):]  # grab the number
#
#             if suffix and int(suffix) > highest_suffix:
#                 highest_suffix = int(suffix)
#
#         new_prior_tag = target_tag + str(highest_suffix + 1)
#
#         sha_actual_commit, dt_tag = extract_commit_datetime(sha_tag)
#
#         # rename the current commit to be the tag with the number
#         # after it:
#         git_cmd = "git tag -a -m INSTRUCTOR_FEEDBACK " + \
#                   new_prior_tag + " " + sha_actual_commit
#         print
#         git_cmd
#
#         sz_stdout, sz_stderr, ret = run_command_capture_output(git_cmd)
#
#         # remove existing tag:
#         git_cmd = "git tag -d " + target_tag
#         sz_stdout, sz_stderr, ret = run_command_capture_output(git_cmd)
#
#         # now ready to tag the current commit
#     else:
#         logger.info("Called renumber_current_tag, but no current tag")
#
#
# # This may be useful in case
# class commit_feedback_collector:
#     def __init__(self):
#         self.no_feedback_ever = list()
#         self.new_feedback = list()
#         self.current_feedback_not_changed = list()
#         self.current_feedback_updated = list()
#
#     def generate_commit_feedback(self, pattern, tag, assign_dir):
#         # "" returns a closure that enables us to commit
#         # instructor feedback ""
#
#         def commit_feedback():
#             # "" Go through all the directories and if we find
#             # a file that matches the pattern try to commit it and
#             # tag it. ""
#
#             # The expectation is that there's a single file that
#             # matches and either it's already been committed & tagged,
#             # or else that it's not yet in the repo (in which case,
#             # commit and tag it)
#             #
#             # The full outline of what happens when is listed after
#             # the code to determine if the tag exists and if any
#             # matching files still need to be committed
#             #
#             git_tag_cmd = "git tag -a -m INSTRUCTOR_FEEDBACK " + tag
#             path_to_repo = os.getcwd()
#             regex = re.compile(pattern, flags=re.IGNORECASE)
#
#             # First figure out if the tag already exists:
#             logger.debug("Looking for tag \"" + tag + "\" in " + os.getcwd())
#             git_cmd = "git tag -l " + tag
#             sz_stdout, sz_stderr, ret = run_command_capture_output(git_cmd, True)
#             if sz_stdout == "":
#                 tagged = False
#             else:
#                 tagged = True
#
#             # Next, figure out if any matching files need to be committed:
#             logger.debug("Looking for untracked and/or committed, modified files")
#             git_cmd = "git status --porcelain"
#             sz_stdout, sz_stderr, ret = run_command_capture_output(git_cmd, True)
#
#             modified_staged = list()
#             modified_not_staged = list()
#             untracked = list()
#             untracked_subdirs = list()
#
#             for line in sz_stdout.splitlines():
#                 # line format: file:///C:/Program%20Files/Git/mingw64/share/doc/git-doc/git-status.html#_short_format
#                 # [index][working tree]<space>filename
#                 # examples of lines:
#                 # M File.txt            # present in repo, but not staged
#                 # M  NewFile.txt         # modified, added to index
#                 # A  SubDir/FooFile.txt  # added to index
#                 # ?? ExtraFile.txt       # untracked
#                 #
#                 # Note that git does NOT include the contents of untracked
#                 # subdirs in this output, so if a new file is put into a new
#                 # subdir (say, SubDir2\Grade.txt) git status will list
#                 # ?? SubDir2             # note that Grade.txt is NOT listed
#                 # Thus, we actually do need to traverse the file system to
#                 # find new files
#
#                 # does this line's file match the pattern?
#                 both_codes = line[0:2]
#                 filename = line[3:]
#                 match = re.search(regex, filename)
#
#                 # If there's a new, untracked subdir
#                 # then we'll need to os.walk it to find
#                 # any matching files
#                 # (otherwise we can skip that)
#                 if both_codes == "??" and \
#                         filename[len(filename) - 1:] == '/':
#                     untracked_subdirs.append(os.path.join(path_to_repo, filename))
#
#                 if match:
#                     code_index = line[0]
#                     code_working = line[1]
#
#                     if both_codes == "??":
#                         untracked.append(filename)
#                         continue
#                     if both_codes == "!!":
#                         printError(filename + " (in " + os.getcwd() + "):" \
#                                                                       "\n\tWARNIG: This matched the pattern but it" \
#                                                                       " also matches something in .gitignore\n" \
#                                                                       "(This will NOT be committed now)\n")
#                         continue
#
#                     codes_changed = "M ARC"
#
#                     if codes_changed.find(code_index) != -1:
#                         # changed in the index
#                         if code_working == " ":
#                             modified_staged.append(filename)
#                             # code_working & _index will never both be blank
#                             # (that would mean no changes)
#                         elif code_working == "M":
#                             modified_not_staged.append(filename)
#
#             # find matching file(s) in untracked subdirs:
#             # Skip this unless there's an untracked directory
#             # (these can contain more stuff, and git doesn't scan through
#             # the untracked dir)
#             if untracked_subdirs:
#                 for subdir in untracked_subdirs:
#                     # walk through the subdir
#                     # (starting the walk here avoids any of the
#                     # files that git told us about)
#                     for root, dirs, files in os.walk(subdir):
#                         for name in files:
#
#                             match = re.search(regex, name)
#                             if match:
#                                 path = os.path.join(root, name)
#                                 local_dir = path.replace(path_to_repo, "")
#                                 # remove the leading /
#                                 if local_dir[0] == os.sep:
#                                     local_dir = local_dir[1:]
#                                 logger.debug("found a match at " + local_dir)
#                                 untracked.append(local_dir)
#
#             # print_list(path_to_repo, modified_staged, Fore.CYAN, "modified, staged files:")
#             # print_list(path_to_repo, modified_not_staged, Fore.YELLOW, "modified, unstaged files:")
#             # print_list(path_to_repo, untracked, Fore.RED, "untracked files:")
#             if modified_staged:
#                 need_commit = True
#             else:
#                 need_commit = False
#
#             files_to_add = modified_not_staged + untracked
#             # The two 'expected' cases are listed at the top
#             # Here's the full  outline:
#             # if not tagged:
#             #   if file absent:
#             #       note and skip
#             #   if file present but untracked:
#             #       add, commit, tag, done
#             #   if file committed and unchanged:
#             #       tag it?  <ERROR>
#             #
#             # if tagged:
#             #   file should be in repo (else error)
#             #   if file not updated:
#             #       note and skip
#             #   if file has been updated:
#             #       update existing tag to have number after it
#             #       commit changes
#             #       tag the current commit with the desired tag
#
#             if not tagged:
#                 #   if file absent:
#                 if not need_commit and not files_to_add:
#                     #       note and skip
#                     self.no_feedback_ever.append(os.getcwd())
#                     return
#                 #   if file present but untracked:
#                 else:
#                     #       add, commit, tag, done
#                     git_cmd = "git add " + " ".join(files_to_add)
#                     call_shell(git_cmd)
#
#                     call_shell("git commit -m Adding_Instructor_Feedback")
#                     sz_stdout, sz_stderr, ret = run_command_capture_output(git_tag_cmd)
#
#                     self.new_feedback.append(os.getcwd())
#                     return
#
#             #   if file committed and unchanged:
#             #       tag it?  <ERROR>
#             #   we're not checking for previously committed files
#             #   so we don't handle this case
#             #   It *shouldn't* happen, anyways, so hopefully it won't
#             #       (It might happen if the teacher commits their
#             #       feedback manually)
#
#             if tagged:
#                 #   file should be in repo (else error)
#                 #   if file not updated:
#                 if not need_commit and not files_to_add:
#                     #       note and skip
#                     self.current_feedback_not_changed.append(os.getcwd())
#                 #   if file has been updated:
#                 else:
#                     #       update existing tag to have number after its
#                     renumber_current_tag(tag)
#
#                     git_cmd = "git add " + " ".join(files_to_add)
#                     call_shell(git_cmd)
#
#                     #       commit changes
#                     call_shell("git commit -m Adding_Instructor_Feedback")
#
#                     #       tag the current commit with the desired tag:
#                     sz_stdout, sz_stderr, ret = run_command_capture_output(git_tag_cmd)
#
#                     self.current_feedback_updated.append(os.getcwd())
#
#             # if files_to_add:
#             #    # modified_staged are already in the index, ready to be committed
#             #    files_to_add = modified_not_staged + untracked
#             #    git_cmd = "git add " + " ".join(files_to_add)
#             #    call_shell(git_cmd)
#             #    call_shell("git commit -m Adding_Instructor_Feedback")
#             #    # TODO: we can use a string with spaces for the -m message,
#             #    # but only if we pass it as a single string object in the list
#             #    # of strings (i.e., call_shell can't just call .split() )
#             #    call_shell("git tag -a " + tag + " -m INSTRUCTOR_FEEDBACK_ADDED")
#             #    logger.debug( "Added " + " ".join(files_to_add) )
#             #    return True
#             # else:
#             #    print_error( "Found NO feedback to add in " + \
#             #        path_to_repo.replace(assign_dir, ""))
#             #    return False
#
#         # to test:
#         # run the following in a repo, then run this code
#         # E:\Work\Tech_Research\Git\Tests\Batch_Files\commitFeedback.bat
#
#         return commit_feedback
#
#
# # I think I can replace all of this with "git add *"
# class upload_list_collector(object):
#     # ""A class to collect up the info about which projects were uploaded
#     # for the instructor""
#
#     def __init__(self):
#         #""Set up the empty lists""
#         self.unchanged = list()
#         self.uploaded = list()
#
#     def generate_upload_list_collector(self):
#         def upload_list_collector():
#
#             p = subprocess.Popen("git push --progress".split(), \
#                                  stderr=subprocess.STDOUT, \
#                                  stdout=subprocess.PIPE,
#                                  universal_newlines=True)
#             sz_stdout, sz_stderr = p.communicate()
#             p.wait()
#
#             logger.debug("In response to 'git push', got: " + sz_stdout)
#
#             if sz_stdout.find("Everything up-to-date") != -1:
#                 self.unchanged.append(os.getcwd())
#             else:
#                 if sz_stdout.find("To git@") == -1:
#                     logger.error("Expected to find \"Writing objects:\" in output but didn't")
#                 self.uploaded.append(os.getcwd())
#
#             # the tags don't automatically upload,
#             # so push them separately:
#             p = subprocess.Popen("git push origin --tags --progress".split(), \
#                                  stderr=subprocess.STDOUT, \
#                                  stdout=subprocess.PIPE,
#                                  universal_newlines=True)
#             sz_stdout, sz_stderr = p.communicate()
#             p.wait()
#
#             logger.debug("In response to 'git push origin --tags', got: " + sz_stdout)
#             return True
#
#         return upload_list_collector
