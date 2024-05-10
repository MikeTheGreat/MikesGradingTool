poetry build -f wheel
pipx uninstall mikesgradingtool
pipx install  --verbose dist/mikesgradingtool-0.1.1-py3-none-any.whl
mikesgradingtool.exe
