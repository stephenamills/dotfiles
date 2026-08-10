#!/usr/bin/env python3
import os,runpy
from pathlib import Path
here=Path(__file__).resolve(); candidates=[]
if os.environ.get("STUDY_GUIDE_LITE_RUNNER"): candidates.append(Path(os.environ["STUDY_GUIDE_LITE_RUNNER"]))
candidates.append(here.parents[2]/"study-guide-lite/scripts/study_guide_lite.py")
candidates.append(Path.home()/".agents/skills/study-guide-lite/scripts/study_guide_lite.py")
runner=next((p for p in candidates if p.exists()),None)
if runner is None: raise SystemExit("study-guide-lite runner not found")
os.environ["STUDY_GUIDE_LITE_SKILL"]=str(here.parents[1]); runpy.run_path(str(runner),run_name="__main__")
