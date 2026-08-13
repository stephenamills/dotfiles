#!/usr/bin/env python3
"""One-pass, transcript-folder Power BI study-guide generator."""
from __future__ import annotations

import argparse, concurrent.futures, datetime as dt, json, os, re, shlex, shutil, signal, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path

MAX_CONCURRENCY = 6
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [
    Path.home() / "Downloads" / "Microsoft Power BI Desktop for Business Intelligence",
    Path.home() / "Downloads" / "Microsoft Power BI Data Analyst",
    Path.home() / "Downloads" / "Microsoft Power BI for Beginners",
]
_active: set[subprocess.Popen] = set()
_active_lock = threading.Lock()

def slug(value: str) -> str:
    value = value.encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-") or "unit"

def natural_key(value: str):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r"(\d+)", value)]

def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def atomic_json(path: Path, value):
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")

def course_root(value: Path) -> Path:
    value = value.expanduser().resolve()
    return value.parent if value.name.casefold() == "transcripts" else value

def resolve_roots(values: list[str] | None) -> list[Path]:
    roots = [course_root(Path(v)) for v in values] if values else [course_root(p) for p in DEFAULT_ROOTS]
    return list(dict.fromkeys(roots))

def discover(roots: list[Path]):
    units = []
    for root in roots:
        transcripts = root / "transcripts"
        if not transcripts.is_dir():
            continue
        course = slug(root.name)
        topics: dict[Path, list[Path]] = {}
        for p in transcripts.rglob("*.txt"):
            if not p.is_file():
                continue
            rel = p.relative_to(transcripts)
            topic_dir = rel.parent if rel.parent != Path(".") else Path(p.stem)
            topics.setdefault(topic_dir, []).append(p)
        for topic, files in sorted(topics.items(), key=lambda x: natural_key(x[0].as_posix())):
            files = sorted(files, key=lambda p: natural_key(p.name))
            title = topic.name if topic != Path(".") else files[0].stem
            uid = f"{course}__{slug(topic.as_posix())}"
            output = root / "study guides" / f"{title} - Study Guide.md"
            units.append({"id": uid, "course": course, "course_root": root, "topic": topic.as_posix(),
                          "title": title, "sources": files, "output": output,
                          "source_files": [str(p) for p in files], "output_path": str(output)})
    return sorted(units, key=lambda u: (u["course"], natural_key(u["topic"])))

def state_dir(root: Path) -> Path:
    return root / ".study-guide-powerbi"

def load_runs(root: Path):
    p = state_dir(root) / "runs.json"
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError): return []

def selected(units, args):
    if getattr(args, "unit", None):
        wanted = set(args.unit)
        units = [u for u in units if u["id"] in wanted]
    if getattr(args, "missing_only", False):
        units = [u for u in units if not u["output"].is_file()]
    return units

DEPTH_CONTRACT = (SKILL_DIR / "references" / "depth-contract.md").read_text(encoding="utf-8")
PROMPT = DEPTH_CONTRACT + """

Apply the contract specifically to a Power BI learner. Explain model, row, and filter context and preserve DAX/M syntax when the transcript supports them. Return only the final Markdown guide.

TOPIC: {title}

TRANSCRIPTS:
{source}
"""

def prompt_for(unit) -> str:
    chunks = []
    for p in unit["sources"]:
        chunks.append(f"\n--- {p.name} ---\n{p.read_text(encoding='utf-8', errors='replace')}")
    return PROMPT.format(title=unit["title"], source="".join(chunks))

def stop_processes(*_):
    with _active_lock:
        processes = list(_active)
    for p in processes:
        try: os.killpg(p.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try: p.terminate()
            except OSError: pass

def invoke(unit, args, run_dir: Path):
    work = run_dir / slug(unit["id"])
    work.mkdir(parents=True, exist_ok=True)
    artifact = work / "final.md"
    prompt = prompt_for(unit)
    codex = shlex.split(os.environ.get("CODEX_BIN", "codex"))
    cmd = codex + ["--ask-for-approval", "never", "exec", "--ephemeral", "--skip-git-repo-check", "--ignore-rules", "--color", "never", "--cd", str(work), "-o", str(artifact), "-"]
    if args.model: cmd += ["--model", args.model]
    if args.reasoning_effort: cmd += ["-c", f"model_reasoning_effort={args.reasoning_effort}"]
    if args.verbosity: cmd += ["-c", f"model_verbosity={args.verbosity}"]
    try:
        p = subprocess.Popen(cmd, cwd=work, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, text=True)
        with _active_lock: _active.add(p)
        try:
            out, err = p.communicate(prompt, timeout=args.timeout_minutes * 60 if args.timeout_minutes else None)
        finally:
            with _active_lock: _active.discard(p)
        text = artifact.read_text(encoding="utf-8", errors="replace") if artifact.is_file() else (out or "")
        ok = p.returncode == 0 and bool(text.strip())
        return ok, text, "" if ok else (err.strip()[-2000:] or "empty final response" if p.returncode == 0 else f"exit {p.returncode}")
    except subprocess.TimeoutExpired:
        stop_processes(); return False, "", "timeout"
    except KeyboardInterrupt:
        stop_processes(); raise
    except Exception as exc:
        return False, "", str(exc)

def install(unit, text: str, run_dir: Path):
    target = unit["output"]
    if target.exists():
        archive = run_dir / "archive" / target.name
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, archive)
    atomic_write(target, text)

def generate(units, args):
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dirs = {r: state_dir(r) / "runs" / run_id for r in {u["course_root"] for u in units}}
    records = [{"id": u["id"], "status": "pending", "source_files": u["source_files"], "output_path": u["output_path"]} for u in units]
    if args.dry_run:
        return run_id, records, 0
    for d in run_dirs.values(): d.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGINT, stop_processes)
    def one(item):
        i, u = item
        ok, text, error = invoke(u, args, run_dirs[u["course_root"]])
        if ok:
            install(u, text, run_dirs[u["course_root"]]); return i, {"id": u["id"], "status": "installed", "source_files": u["source_files"], "output_path": u["output_path"]}
        return i, {"id": u["id"], "status": "failed", "error": error, "source_files": u["source_files"], "output_path": u["output_path"]}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, MAX_CONCURRENCY))) as pool:
            for i, rec in pool.map(one, enumerate(units)):
                records[i] = rec
    except KeyboardInterrupt:
        stop_processes()
        for rec in records:
            if rec["status"] == "pending": rec["status"] = "interrupted"
    status = "completed" if all(r["status"] == "installed" for r in records) else "failed"
    byroot = {}
    for u in units: byroot.setdefault(u["course_root"], []).append(u)
    for root in byroot:
        ids = {u["id"] for u in byroot[root]}
        runs = load_runs(root); runs.append({"run_id": run_id, "status": status, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "units": [r for r in records if r["id"] in ids]}); atomic_json(state_dir(root) / "runs.json", runs)
    return run_id, records, 0 if status == "completed" else 1

def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("list-units", "generate-all", "status"):
        p = sub.add_parser(name); p.add_argument("--root", action="append", help="course directory or its transcripts directory")
        p.add_argument("--json", action="store_true")
        if name == "list-units": p.add_argument("--missing-only", action="store_true")
        if name == "generate-all":
            p.add_argument("--missing-only", action="store_true"); p.add_argument("--unit", action="append"); p.add_argument("--concurrency", type=int, default=6); p.add_argument("--max-concurrency", type=int, dest="concurrency"); p.add_argument("--model", default="gpt-5.6-sol"); p.add_argument("--reasoning-effort", "--reasoning", dest="reasoning_effort", default="xhigh"); p.add_argument("--verbosity", default="high"); p.add_argument("--timeout-minutes", type=float, default=30); p.add_argument("--dry-run", action="store_true")
        if name == "status": p.add_argument("run_id", nargs="?")
    return ap

def main(argv=None):
    args = parser().parse_args(argv); roots = resolve_roots(args.root); units = discover(roots)
    if args.command == "list-units":
        rows = [{k: (str(v) if isinstance(v, Path) else v) for k, v in u.items() if k not in {"sources", "course_root"}} | {"source_files": u["source_files"]} for u in selected(units, args)]
        print(json.dumps(rows, indent=2) if args.json else "\n".join(f"{u['id']}\t{u['title']}\t{len(u['sources'])} transcripts\t{u['output']}" for u in selected(units, args))); return 0
    if args.command == "status":
        data = []
        for root in roots: data.extend(load_runs(root))
        if args.run_id: data = [r for r in data if r["run_id"] == args.run_id]
        print(json.dumps(data, indent=2) if args.json else "\n".join(f"{r['run_id']}\t{r['status']}" for r in data)); return 0
    units = selected(units, args); run_id, records, code = generate(units, args)
    print(json.dumps({"run_id": run_id, "counts": {"selected": len(records), "installed": sum(r["status"] == "installed" for r in records), "failed": sum(r["status"] == "failed" for r in records)}, "units": records}, indent=2) if args.json else f"{run_id}: {len(records)} selected"); return code

if __name__ == "__main__": sys.exit(main())
