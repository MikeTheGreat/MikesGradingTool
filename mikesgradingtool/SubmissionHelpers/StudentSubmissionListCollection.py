'''
Created on Jun 18, 2012

@author: MikePanitz

StudentSubmissionListCollection object:
    Init
        pass
    Add( SS )
        If there's a StudentSubmissionList for SS, 
        then call StudentSubmissionList.Add
        Otherwise create a StudentSubmissionList with SS & add to collection        
'''
import os
from collections import OrderedDict

from mikesgradingtool.SubmissionHelpers.StudentSubmission import StudentSubmission
from mikesgradingtool.SubmissionHelpers.StudentSubmissionList import \
    StudentSubmissionList
from mikesgradingtool.utils.my_logging import get_logger
from colorama import Fore, Style

logger = get_logger(__name__)


class StudentSubmissionListCollection:
    def __init__(self, srcPath = None):
        self.subLists = OrderedDict()

        # If we're manually loading this later then skip the folder-walking
        if srcPath is None:
            return

        rootDirContents = os.listdir(srcPath)
        # OS.WALK through basedir & all subdirs
        #    If *dir* appears to be a student submission
        #        Make an StudentSub out of it
        #        StudentSubmissionListCollection.Add(SS)
        #            DO process things inside it

        # Older, unused code:
        # dirs = os.listdir(srcPath)
        # for theDir in dirs:
        for (fullPath, dirs, files) in os.walk(srcPath):
            # fullPath = os.path.join(srcPath, theDir)
            logger.info(f"Full path to next dir: {fullPath}")
            if not os.path.isdir(fullPath):
                continue

            (base, filename) = os.path.split(fullPath)
            if StudentSubmission.isValidString(filename):
                studentSub = StudentSubmission.parseString(fullPath)
                logger.info("This is a student submission: " +
                            studentSub.getFullName() +
                            " " + str(studentSub.timestamp))
                if studentSub:
                    self.Add(studentSub)
                else:
                    print(Style.BRIGHT + Fore.RED +
                          "Found a unparsable folder: " +
                          os.path.basename(fullPath) + " at: " +
                          fullPath + Style.RESET_ALL)
            else:
                if filename in rootDirContents:
                    # TODO  Print this message if sub's path (fullPath) is
                    #       an immediate subdir of srcPath
                    #           (otherwise we can get a lot of messages
                    #           about subsubdirs)
                    print(Style.BRIGHT + Fore.RED +
                          "Found a NON-submission folder: " +
                          os.path.basename(fullPath) + " at: " + fullPath
                          + Style.RESET_ALL)

                # always log non-sub dirs:
                logger.info("Found a NON-submission folder: " +
                            os.path.basename(fullPath) + " at: " + fullPath)

    def __str__(self):
        strSubLists = ""
        for k, v in list(self.subLists.items()):
            # removed from start "\t" + str(k) + ": " +
            strSubLists += "=" * 20 + "\n" + str(v) + "\n\n"
        return "StudentSubmissionListCollection:\n" + strSubLists

    def strShort(self):
        strSubLists = ""
        for k, v in list(self.subLists.items()):
            strSubLists += "\t" + str(k) + "\n"
        return "StudentSubmissionListCollection:\n" + strSubLists

    def Add(self, StudentSub):
        # TODO Why do we need to lower case the student's name, here in StuSubListColl?
        lName = StudentSub.getFullName().lower()
        if lName in self.subLists:
            logger.info(f"adding {lName} to existing list")
            subList = self.subLists[lName]
            subList.Add(StudentSub)
        else:
            logger.info(
                f"adding {lName} to brand new StudentSubmissionList list")
            self.subLists[lName] = StudentSubmissionList(StudentSub)

    def fixup(self, oldLoc, newLoc):
        for studentName, aList in list(self.subLists.items()):
            aList.fixup(oldLoc, newLoc)

    def contains(self, fullName):
        lName = fullName.lower()
        return self.subLists[lName] is not None
