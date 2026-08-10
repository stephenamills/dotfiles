#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
def main():
    data=sys.stdin.read(); cwd=Path.cwd(); manifest=next(cwd.rglob("tasks.json"),None)
    if not manifest:return 2
    entries=json.loads(manifest.read_text())
    for e in entries:
        p=Path(e["artifact_path"])
        if os.environ.get("FAKE_CODEX_FAIL_UNIT")==e["unit_id"]: continue
        p.parent.mkdir(parents=True,exist_ok=True); p.write_text("# "+e["unit_id"]+"\n\nGenerated study guide.\n")
    print(json.dumps({"type":"turn.completed","argv":sys.argv,"env":{"CODEX_BIN":os.environ.get("CODEX_BIN")}})); return 0
if __name__=="__main__":sys.exit(main())
