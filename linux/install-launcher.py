#!/usr/bin/env python3
"""Install an app-menu shortcut to this extracted folder; does not move files."""
import os
from pathlib import Path

folder = Path(__file__).resolve().parent
# Desktop-entry Exec quoting, including escaping the field-code introducer.
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'

applications = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'applications'
applications.mkdir(parents=True, exist_ok=True)
target = applications / 'hbomb-controller-hub.desktop'
target.write_text('[Desktop Entry]\nType=Application\nName=HBOMB Controller Hub\nComment=PS3, PS5 and Xbox controller diagnostics\nExec=/usr/bin/python3 ' + quote(folder/'controller_hub.py') + '\nIcon=input-gaming\nTerminal=false\nCategories=Game;Utility;\n')
print('Installed app-menu launcher:', target)
print('Keep the extracted folder at its current location. Run this script again if you move it.')
