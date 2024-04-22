'''
Created on Jun 18, 2012

@author: MikePanitz


StudentSubmission:
    parseString also detects feedback files
        If feedbackFile is None: 
            Do the glob thing
            set feedbackFile to result
'''
import os
import shutil

from mikesgradingtool.HomeworkHelpers.OrganizeSubmissions import \
    ConsolidateSubmissions
from mikesgradingtool.utils.my_logging import get_logger
from colorama import Style

logger = get_logger(__name__)


def CopyTemplateToStudents(srcFile, destDir, prefix=""):
 
    #print "src: " + srcFile
    #print "dst: " + destDir
    
    if not os.path.exists(srcFile):
        print(("Template file does not exist! " + srcFile))
        return
    
    if not os.path.exists(destDir):
        print(("Destination directory does not exist! " + destDir))
        return
 
    # print "prefix is:"+prefix+"<<<"
 
    # Get a list of the student submissions
    #    (DO rearrange them nicely)
    newSubs = ConsolidateSubmissions(destDir)
    
    print("\nCopying template to student directory for:")

    for (name,newSubList) in list(newSubs.subLists.items()) :
        
        (root, ext) = os.path.splitext(srcFile)
        path = os.path.normpath(newSubList.mostRecent.path)
        (basePath, fileName) = os.path.split(path)
        #logger.debug("\n\tpath: " + path)
        #logger.debug("\n\tname: " + fileName + ext)
        destFile = path + os.sep + prefix + fileName + ext
        #logger.debug("\n\tdest: " + destFile )
        
        if os.path.exists(destFile):
#            print "\t\tFile already exists for " + name
            print(("    {0:<20}".format(name) + Style.BRIGHT + "File already exists" + Style.RESET_ALL)) 

        else:    
            print(("    {0:<20}".format(name))) 
            shutil.copy2(srcFile, destFile)
    print(("(" + str(len(newSubs.subLists)) + " directories)"))

