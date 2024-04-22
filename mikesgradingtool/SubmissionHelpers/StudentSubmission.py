'''
Created on Jun 18, 2012

@author: MikePanitz
'''
import datetime
import glob
import os
import pprint
import re
import shutil

from mikesgradingtool.utils.my_logging import get_logger
from mikesgradingtool.utils.print_utils import printError

logger = get_logger(__name__)


class StudentSubmission:
    # class static variables:
    # prog = re.compile(
    # "[^,]+,[^,]+,[^,]+,[^,]+\d\d\d\d-\d\d-\d\d_\d\d-\d\d-\d\d$",
    # re.IGNORECASE)
    prog = re.compile("[^,]+,[^,]+,[^,]", re.IGNORECASE)
    DATE_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"

    def __init__(self, *args):
        # This is either the path to the student's feedback file
        # OR
        # a list of paths (if there's more than 1 feedback file)
        self.feedbackFilePath = None

        if len(args) >= 1:
            self.path = args[0]
        else:
            self.path = ""

        if len(args) >= 2:
            self.lastName = args[1]
        else:
            self.lastName = ""

        if len(args) >= 3:
            self.firstName = args[2]
        else:
            self.firstName = ""

        if len(args) >= 4:
            self.assign = args[3]
        else:
            self.assign = ""

        if len(args) >= 5:
            self.timestamp = datetime.datetime.strptime(
                args[4].strip(), StudentSubmission.DATE_TIME_FORMAT)
        else:
            self.timestamp = datetime.datetime.min

        # "srcString" support
        # if len(args) >= 6:
        #    self.srcString = args[5]
        # else:
        #    self.srcString  = ""
        pass

    def __str__(self):
        return str(pprint.pformat(self.__dict__, width=200))

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return self.__dict__ == other.__dict__

    def getTimestampString(self):
        return datetime.datetime.strftime(
            self.timestamp, StudentSubmission.DATE_TIME_FORMAT)

    def getFullName(self):
        return self.lastName + ", " + self.firstName

    # _c for 'canonical' - lowercased
    def getLastName_c(self):
        return self.lastName.lower()

    def getFirstName_c(self):
        return self.firstName.lower()

    def moveTo(self, newDir):
        #        if newDir IS the same as the current dir:
        #            return false
        #        if newDir is NOT the same as the current dir:
        #            move submission to newDir
        #            update fullpath
        #            return true
        (head, tail) = os.path.split(self.path)
        logger.info("moveTo:\n\tpath:" + self.path + "\n\thead:" + head +
                    "\n\tnewDir:" + newDir + "\n\ttail: " + tail)
        if newDir == head:  # told to move to same place
            return False
        else:  # newDir != self.path:
            dest = os.path.join(newDir, tail)
            if os.path.exists(dest):
                printError(" Can't move duplicate folder because destination" +
                           " already exists\n\t" + dest)

                return False
            print((self.getFullName() +
                   ": moved a directory\n\tfrom: " +
                   self.path + "\n\tto:   " + dest + "\n"))
            shutil.move(self.path, dest)  # move to newDir
            self.path = os.path.join(newDir, tail)  # update fullpath
            return True

    # This method is called to notify the StuSub that
    # the folder "oldPath" has been moved to a new location - "newPath"
    def fixup(self, oldPath, newPath):
        # if the overall directory is a subdir of newPath, then fixup the path
        prefix = os.path.commonpath([oldPath, self.path])
        if len(oldPath) == len(prefix) and len(oldPath) < len(self.path):
                # change text of path to reflect new location
            self.path = os.path.join(newPath, self.path[len(prefix) + 1:])

        # if the feedback path is in a subdir of newPath,
        # then fixup the feedback path
        if self.feedbackFilePath is not None:
            # feedbackFilePath may be a single file, or a list of files
            # we'll push it all into a list in order to deal with it consistently
            # (then unpack it later, if needed)
            if type(self.feedbackFilePath) is list:
                feedbackFilesPaths = self.feedbackFilePath
            else:
                feedbackFilesPaths = [self.feedbackFilePath]
            transformedFiles = list()
            # print(f"type of oldPath:{str(type(oldPath))}\n\toldPath:{oldPath}\ntype of self.feedbackFilePath:{str(type(self.feedbackFilePath))}\nself.feedbackFilePath:{self.feedbackFilePath}\n")
            for feedbackFile in feedbackFilesPaths:
                prefix = os.path.commonpath([oldPath, feedbackFile])

                if len(oldPath) == len(prefix) and \
                        len(oldPath) < len(feedbackFile):
                    # change text of path to reflect new location
                    newFeedbackFile = os.path.join(
                        newPath, feedbackFile[len(prefix) + 1:])
                else:
                    newFeedbackFile = feedbackFile

                transformedFiles.append(newFeedbackFile)

            if len(transformedFiles) == 1:
                self.feedbackFilePath = transformedFiles[0]
            else:
                self.feedbackFilePath = transformedFiles

    @staticmethod
    def isValidString(sz):
        if StudentSubmission.prog.search(sz.strip()) is not None:
            # print "valid: " + sz.strip()
            return True
        else:
            # print "INVALID: " + sz.strip()
            return False

    # Returns None if the string is not a valid Student Submission String
    # Returns the StudentSubmission object otherwise

    @staticmethod
    def parseString(sz):
        # print "parseString: " + sz
        if not os.path.exists(sz):
            return None

        (head, tail) = os.path.split(sz)
        if head is None or tail is None:
            print("MISSING")
            # parseString only parses full paths
            return None

        if not StudentSubmission.isValidString(tail):
            return None

        # print "sz: " + sz
        # print "head: %s\ntail:%s" % (head,tail)

        # sub.srcString = sz

        parts = tail.split(',')

        sub = StudentSubmission()

        sub.lastName = parts[0].strip()
        sub.firstName = parts[1].strip()
        # print "parts[0]: " + parts[0] + "\tparts[1]: " + parts[1]
        # + "\tparts[2]: " + parts[2]
        sub.assign = parts[2].strip()
        try:
            sub.timestamp = datetime.datetime.strptime(
                parts[3].strip(), StudentSubmission.DATE_TIME_FORMAT)
        except ValueError:
            # return False # not a valid datetime format
            sub.timestamp = datetime.datetime(
                datetime.MINYEAR, 1, 1, 0, 0, 0, 0)

        sub.path = sz.strip()

        # feedbackFilePath = os.path.join(sz, tail+".doc*")
        feedbackFilePath = os.path.join(
            sz, "*" + sub.lastName.lower() + "*.doc*")
        # logger.debug("feedbackFilePath: " + str(feedbackFilePath) )
        fbFiles = glob.glob(feedbackFilePath)
        # logger.debug("fbFiles: " + str(fbFiles) )

        if len(fbFiles) == 1:
            sub.feedbackFilePath = fbFiles[0]
        elif len(fbFiles) > 1:
            err = sub.getFullName() + " had multiple feedback files\n\t" + \
                "\n\t".join(fbFiles)
            sub.feedbackFilePath = fbFiles
            print(err)
        # else there are zero feedback files, which is fine -
        # leave feedbackFilePath as None

        return sub
