'''
Created on Jun 18, 2012

@author: MikePanitz


StudentSubmission:
    parseString also detects feedback files
        If feedbackFile is None: 
            Do the glob thing
            set feedbackFile to result
'''
from mikesgradingtool.HomeworkHelpers.OrganizeSubmissions import \
    ConsolidateSubmissions
from mikesgradingtool.SubmissionHelpers.StudentSubmissionListCollection import \
    StudentSubmissionListCollection
from mikesgradingtool.utils.my_logging import get_logger
logger = get_logger(__name__)

import os
import shutil
from colorama import Fore, Style


def CopyRevisionFeedback(src, dest):
    # Step #1: Go through the 'originals' directory
    # & build up a dictionary of student names & their original feedback files

    # Get a list of the original submissions
    #    (but do NOT rearrange them)

    originalSubs = StudentSubmissionListCollection(src)
    logger.debug("Original Submissions: " + originalSubs.strShort())

    # Get a list of the revised submissions
    #    (DO rearrange them nicely)
    newSubs = ConsolidateSubmissions(dest)
    logger.debug("New Submissions: " + originalSubs.strShort())

    print("\nCopying original to revision directory for:")
    for (name, newSubList) in list(newSubs.subLists.items()):
        origSubmissions = []
        logger.debug("NEW SUBMISSION from: " + name +
                     " sublist: " + str(newSubList))

        for (name, origSubList) in list(originalSubs.subLists.items()):
            logger.debug("Original submission from " + name +
                         ": origSubList: " + str(origSubList))
            if origSubList.mostRecent.feedbackFilePath is not None:
                # if orig submission contains the same last name as the new, revised submission,
                # then add all the feedback files to the list
                tempAllSubs = list(origSubList.previousSubmissions)
                tempAllSubs.append(origSubList.mostRecent)
                # logger.debug("tempAllSubs: " + str(tempAllSubs) )

                logger.debug("comparing " + origSubList.mostRecent.getLastName_c() + " to " + newSubList.mostRecent.getLastName_c(
                ) + " and " + origSubList.mostRecent.getFirstName_c() + " to " + newSubList.mostRecent.getFirstName_c())

                if newSubList.mostRecent.getLastName_c() == origSubList.mostRecent.getLastName_c() \
                        and newSubList.mostRecent.getFirstName_c() == origSubList.mostRecent.getFirstName_c():

                    logger.debug("copying from\n" + str(origSubList.mostRecent.feedbackFilePath) +
                                 "\nto\n" + newSubList.mostRecent.path)

                    filtered_older = (olderSubmission.feedbackFilePath
                                      for olderSubmission
                                      in tempAllSubs
                                      if olderSubmission.feedbackFilePath is not None)

                    check_for_multiple_feedback_files = []
                    check_for_multiple_feedback_files.extend(filtered_older)

                    if isinstance(check_for_multiple_feedback_files, list) \
                            and isinstance(check_for_multiple_feedback_files[0], list):
                        print(("Found nested feedback files for " + name))
                        check_for_multiple_feedback_files = \
                            check_for_multiple_feedback_files[0]
                        
                    logger.debug("check_for_multiple_feedback_files: " +
                                 "\n\t".join(check_for_multiple_feedback_files))

                    logger.debug("BEFORE ADDING: " + str(origSubmissions))

                    origSubmissions.extend(check_for_multiple_feedback_files)

                    logger.debug("AFTER ADDING: " + str(origSubmissions))

        if not origSubmissions:
            print((Fore.RED + Style.BRIGHT + "=>" + Style.RESET_ALL + Style.BRIGHT +
                   "  {0:<20} did not have an original version!".format(newSubList.mostRecent.getFullName()) + Style.RESET_ALL))
            continue

        logger.debug("origSubmissions: " + str(origSubmissions))
        if len(origSubmissions) == 1:
            MoveFeedbackTo(origSubmissions[0], newSubList.mostRecent, True)
        else:  # len(origSubmissions) > 1:
            print((Fore.YELLOW + Style.BRIGHT + "==" + Style.RESET_ALL + newSubList.mostRecent.getFullName() +
                   " matched multiple original submissions - moving them all over"))

            for origSub in origSubmissions:
                MoveFeedbackTo(origSub, newSubList.mostRecent,
                               "ORIGINAL_FEEDBACKS")  # Do NOT rename

    # print 'Finished copying feedback to revision directory'
    print(("(" + str(len(newSubs.subLists)) + " directories)"))


def MoveFeedbackTo(origFeedback, newSub, renameOrSubdir):
    if isinstance(renameOrSubdir, str):
        rename = False
        subDir = renameOrSubdir + os.sep
    else:
        rename = True
        subDir = ""

    logger.debug("origFeedback:>>" + str(origFeedback) + "<<")

    origFilename = os.path.basename(origFeedback)
    origExt = os.path.splitext(origFeedback)[1]
    revisedFileBaseName = os.path.basename(newSub.path)
    revisedFilename = revisedFileBaseName + origExt

    newSubDir = os.path.join(newSub.path, subDir)
    revisedNameInRevisedDir = os.path.join(newSubDir, revisedFilename)

    # print "moving to " +revisedNameInRevisedDir
    if os.path.exists(revisedNameInRevisedDir):
        # print Fore.GREEN + Style.BRIGHT + "--" + Style.RESET_ALL + "  {0:<20} already had a revision document ".format( newSub.getFullName()) # + revisedNameInRevisedDir
        print((Style.RESET_ALL + "    {0:<20} already had a revision document ".format(
            newSub.getFullName())))  # + revisedNameInRevisedDir
        return

    if not os.path.exists(newSubDir):
        os.makedirs(newSubDir)
    shutil.copy2(origFeedback, newSubDir)
    print(("    {0:<55}(orig file: {1})".format(
        newSub.getFullName(), origFilename) + Style.RESET_ALL))

    if rename:
        originalNameInRevisedDir = os.path.join(newSubDir, origFilename)
        os.rename(originalNameInRevisedDir, revisedNameInRevisedDir)