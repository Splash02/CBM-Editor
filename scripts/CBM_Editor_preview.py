import os
import sys
from pathlib import Path

os.environ["CBM_EDITOR_EDITION"] = "preview"

package_parent = str(Path(__file__).resolve().parent.parent)
if package_parent not in sys.path:
    sys.path.insert(0, package_parent)

from cbm_editor.application import main

main()
