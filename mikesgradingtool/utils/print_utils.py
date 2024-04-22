from colorama import init, Fore, Style  # Back

init()  # starts colorama


def printError(szErrorToPrint):
    print(Fore.RED + Style.BRIGHT + "ERROR: " +
          szErrorToPrint + Style.RESET_ALL)


class GradingToolError(Exception):
    def __init__(self, message):  # , errors

        # Call the base class constructor with the parameters it needs
        super().__init__(message)

        # Now for your custom code...
        # self.errors = errors

def print_list(assign_dir, the_list, color, msg, missing_msg=None, **kwargs):
    fprinted = False
    verbose = kwargs["verbose"] if "verbose" in kwargs else False
    indent = kwargs["indent"] if "indent" in kwargs else "\t"

    if not the_list and missing_msg is not None:
        print_color(color, missing_msg)
        fprinted = True
    if the_list:
        if not verbose:
            msg += f" ({len(the_list)} items)"
        print_color(color, msg)

        for item in the_list:
            print( indent + item.replace(assign_dir, ""))
            fprinted = True

        if verbose:
            print(f"{len(the_list)} items")

    if fprinted and verbose:
        print("\n" + "=" * 20 + "\n")

def print_color(color, msg, color_bg=None):
    # ""msg is a string to print
    # color is a member of Fore.*
    # msg will be printed in color, BRIGHT, and then all styles will be reset""
    print(color + Style.BRIGHT, end='')
    if color_bg is not None:
        print(color_bg, end='')
    print(msg + Style.RESET_ALL)
