import functools
import logging

FILTER_TO_USE = "mikesgradingtool.Autograder.file_handlers.Javascript_Handler"
FILTER_TO_USE = "NO OUTPUT"
FILTER_TO_USE = "" # empty string means allow everything

@functools.lru_cache(30) # one for each file, more or less
def get_logger(name):
    # print("Creating console_handler! : " + name)
    logger = logging.getLogger(name)

    #file_handler = logging.FileHandler("C:\\MikesStuff\\Pers\\Dropbox\\Work\\Courses\\NUnit_Autograders\\DELETE_ME\\GradingTool_log.txt", mode="a")
    console_handler = logging.StreamHandler()
    # console_handler = logging.FileHandler("C:\\MikesStuff\\Work\\Student_Work\\NUnit_Autograders\\Autograder-py\\Junk_To_Ignore\\logging_output\\Autograder.txt.log")
    # console_handler.addFilter(logging.Filter(FILTER_TO_USE))
    #file_handler.addFilter(logging.Filter(FILTER_TO_USE))

    # https://docs.python.org/2/library/logging.html#logrecord-attributes
    formatter = logging.Formatter(
        "LOG:%(levelname)s %(module)s:%(lineno)s %(funcName)s\t%(message)s")

    # More verbose format:
    # "[%(asctime)s - %(funcName)10s() at %(filename)s:%(lineno)s -
    # %(levelname)-8s ]\n%(message)s"
    console_handler.setFormatter(formatter)
    #file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    #logger.addHandler(file_handler)

    logger.setLevel(logging.ERROR)
    # logger.critical("created logger: " + name)
    # logger.setLevel(logging.DEBUG)
    return logger
