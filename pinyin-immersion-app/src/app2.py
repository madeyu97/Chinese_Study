# src/app2.py
"""
Second entry point, so the same repository can be deployed twice.

Streamlit Community Cloud identifies an app by repository + branch + main
file path, and refuses a second deployment that matches an existing one.
Pointing the second app at this file makes the combination unique.

Nothing here is specific to either person: WHO the app belongs to is
decided entirely by the APP_USER secret in that deployment's settings.

    app 1 (matt)    main module: pinyin-immersion-app/src/main_app.py
    app 2 (selina)  main module: pinyin-immersion-app/src/app2.py

runpy re-executes main_app.py on every rerun, which is what Streamlit
needs. A plain import would run once and then be served from Python's
module cache, freezing the UI.
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "main_app.py"),
               run_name="__main__")
