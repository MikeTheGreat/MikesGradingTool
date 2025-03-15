#!/usr/bin/env zsh

uv build --wheel

uv tool uninstall mikesgradingtool

highest_version_file=$(ls dist/mikesgradingtool-*-py3-none-any.whl | awk -F '[-.]' '{print $0, $2"."$3"."$4}' | sort -t. -k2,2nr -k3,3nr -k4,4nr | head -n 1 | awk '{print $1}')
echo highest_version_file is: $highest_version_file

uv tool install --verbose "$highest_version_file"

echo "\n\n\n"
mikesgradingtool.exe

############## Previous Build (via Poetry) ###################
#poetry build -f wheel
#
#pipx uninstall mikesgradingtool
#
## Much thanks to ChatGPT for this one:
## This will get the highest numbered file automatically, and then install that
#highest_version_file=$(ls dist/mikesgradingtool-*-py3-none-any.whl | awk -F '[-.]' '{print $0, $2"."$3"."$4}' | sort -t. -k2,2nr -k3,3nr -k4,4nr | head -n 1 | awk '{print $1}')
#
#pipx install --verbose "$highest_version_file"
#
#mikesgradingtool.exe
