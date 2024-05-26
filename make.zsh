poetry build -f wheel

pipx uninstall mikesgradingtool

# Much thanks to ChatGPT for this one:
# This will get the highest numbered file automatically, and then install that
highest_version_file=$(ls dist/mikesgradingtool-*-py3-none-any.whl | awk -F '[-.]' '{print $0, $2"."$3"."$4}' | sort -t. -k2,2nr -k3,3nr -k4,4nr | head -n 1 | awk '{print $1}')

pipx install --verbose "$highest_version_file"

mikesgradingtool.exe
