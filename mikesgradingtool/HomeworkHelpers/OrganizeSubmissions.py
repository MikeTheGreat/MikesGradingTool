from mikesgradingtool.SubmissionHelpers.StudentSubmissionListCollection import \
    StudentSubmissionListCollection

from mikesgradingtool.utils.my_logging import get_logger
logger = get_logger(__name__)

'''
Created on Jun 18, 2012

@author: MikePanitz
Create a StudentSubmissionList

OS.WALK through basedir & all subdirs
    If *dir* appears to be a student submission
        Make an StudentSub out of it
        StudentSubmissionListCollection.Add(SS) 
            # DO process things inside it
    
# Move all the most recent submissions to the base directory
#    (and then fix up anything else that happened to be in one 
#               of the moved dirs)
Iterate through StudentSubmissionListCollection:
    Iterate through each StudentSubmissionList:
        move the most recent dir to the basedir directory 
                w/ StudentSubmissionList.MoveTo(SS, dir)
            StudentSubmissionList.MoveTo will update the most recent 
                dir to the new location
            StudentSubmissionList.MoveTo will fixup all other SS's, as needed

# At this point, all the 'most recent submission' dirs are in-place

Iterate through StudentSubmissionList:
    iterate through the list of submitted dirs:
        if submitted dir is not already inside the most recent dir
            Move that dir into the most recent dir

StudentSubmission object:
    # Represents a directory on-disk
    Parse string
        attrs (name, assign, datetime)
        filename
        fullpath?
    MoveTo(newDir)
        move submission to newDir
        update fullpath
=====        tell containing StudentSubmissionList, 
                    so it can update anything that's inside the dir?

    --- CompareTime(otherSS) # Built into Python, apparently

StudentSubmissionList object:
    Init( SS )
        SS is most recent
        create empty list (of most recent, SS list pairs)
    Add( SS )
        # if SS is more recent than current most, replace current 
        #           & put it into list
        # else add SS to list
    MoveTo(SS, newDir)
        Move SS to the newDir
        If SS is most recent, then update the most recent dir to the new loc
        Iterate through all other dirs, and fixup SS's, as needed

StudentSubmissionListCollection object:
    Init
        pass
    Add( SS )
        If there's a StudentSubmissionList for SS, 
        then call StudentSubmissionList.Add
        Otherwise create a StudentSubmissionList with SS & add to collection   
'''

'''
TODO: Use genexps/listcomprehensions to walk through collections easily?  This way we could reuse the code to inteface with the list-of-all-files that Canvas spews into a single dir
      
'''


def OrganizeSubmissions(dirToOrg):
    newSubs = ConsolidateSubmissions(dirToOrg)
    logger.info("Organized submissions: " + str(newSubs))

    print('\nOrganized submissions into the following directories:')
    for (name, newSubList) in list(newSubs.subLists.items()):
        print("\t" + name)
    print("(" + str(len(newSubs.subLists)) + " directories)")


def ConsolidateSubmissions(srcPath):
    logger.info(f"Told to consolidate {srcPath}")
    # OS.WALK through basedir & all subdirs
    #    If *dir* appears to be a student submission
    #        Make an StudentSub out of it
    #        StudentSubmissionListCollection.Add(SS)
    #            DO process things inside it
    allSubs = StudentSubmissionListCollection(srcPath)
    logger.info("Starting directories:" + str(allSubs))
# Move all the most recent submissions to the base directory
#    (then fix up anything else that happened to be in one of the moved dirs)
# Iterate through StudentSubmissionListCollection:
#    Iterate through each StudentSubmissionList:
#        move the most recent dir to the basedir directory w/
#                           StudentSubmissionList.MoveTo(SS, dir)
#            StudentSubmissionList.MoveTo will update the most recent dir to
#                  the new location
#            StudentSubmissionList.MoveTo will fixup all other SS's, as needed
# III: At this point, all the 'most recent submission' dirs are in-place
#
#    allSubs.Rebase(srcPath)
    logger.info(f"Moving most recent subs to srcPath ({srcPath})")
    for studentName, aList in list(allSubs.subLists.items()):
        oldLoc = aList.mostRecent.path
        logger.info(f"for {studentName}, moving most recent sub ({oldLoc})" +
                    f" to srcPath ({srcPath})")
        if aList.mostRecent.moveTo(srcPath):
            allSubs.fixup(oldLoc, aList.mostRecent.path)
#
#    iterate through the list of submitted dirs:
#        if submitted dir is not already inside the most recent dir
#            Move that dir into the most recent dir
#
# Iterate through StudentSubmissionList:
    logger.info(
        "For each student: Moving older subs to the most recent sub's dir")
    for studentName, aList in list(allSubs.subLists.items()):
        logger.info(f"Adjusting {studentName}")
        for prevSub in aList.previousSubmissions:
            oldLoc = prevSub.path
            logger.info(f"Moving from oldLoc ({oldLoc}) to most recent sub " +
                        f"({aList.mostRecent.path})")
            if prevSub.moveTo(aList.mostRecent.path):
                allSubs.fixup(oldLoc, prevSub.path)
            # moveTo will print out the error message
            # else:
            #    print "Found a duplicate for ",studentName, " at ", oldLoc
            #    print "\t *********** couldn't move! "

    return allSubs
