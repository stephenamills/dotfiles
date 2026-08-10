#!/usr/bin/env python3
"""Smoke tests for the lite runner; the suite uses the bundled fake Codex binary."""
import os, tempfile
from pathlib import Path
from study_guide_lite import extract_epub_text, main

def test_list_and_dry_run():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); (root/"transcripts").mkdir(); (root/"transcripts"/"A.txt").write_text("source")
        os.environ["STUDY_GUIDE_LITE_SKILL"]=str(Path(__file__).parents[2]/"batch-study-guide-autocad")
        assert main(["list-units","--root",td])==0
        assert main(["generate-all","--root",td,"--dry-run"])==0

if __name__=="__main__": test_list_and_dry_run(); print("ok")
