'''
Created on Jun 18, 2012

@author: MikePanitz
'''
# Left here so I don't need to retype this
# from mikesgradingtool.SubmissionHelpers.StudentSubmission import StudentSubmission
import pprint

from mikesgradingtool.utils.my_logging import get_logger

logger = get_logger(__name__)

'''
StudentSubmissionList object:
    Init( SS )
        SS is most recent
        create empty list (of most recent, SS list pairs)
    Add( SS )
        # if SS is more recent than current most recent,
        #           replace current & put it into list
        # else add SS to list
    MoveTo(SS, newDir)
        Move SS to the newDir
        If SS is most recent, then update the most recent dir to the new loc
        Iterate through all other dirs, and fixup SS's, as needed
'''


class StudentSubmissionList:

    def __init__(self, StudentSub):
        self.fullName = StudentSub.getFullName()
        self.mostRecent = StudentSub
        self.previousSubmissions = list()

    def __str__(self):
        return str(self.fullName) + "\n\tMost Recent: " + str(self.mostRecent)\
            + "\n\tPrevious: " + \
            pprint.pformat([str(item)
                            for item in self.previousSubmissions], width=200)

    def Add(self, StudentSub):
        if StudentSub.timestamp > self.mostRecent.timestamp:
            self.previousSubmissions.append(self.mostRecent)
            self.mostRecent = StudentSub
            logger.info(f"NEW MOST RECENT: {StudentSub.getFullName()}  " +
                        str(StudentSub.timestamp))
        else:
            self.previousSubmissions.append(StudentSub)

    def fixup(self, oldPath, newPath):
        for sub in [self.mostRecent] + self.previousSubmissions:
            sub.fixup(oldPath, newPath)

#    MoveTo(SS, newDir)
#        Move SS to the newDir
#        If SS is most recent, then update the most recent dir to the new loc.
#        Iterate through all other dirs, and fixup SS's, as neede
