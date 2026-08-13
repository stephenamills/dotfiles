#!/usr/bin/env python3
"""Benchmark the persistent WhisperKit worker on local audio files.

Reports the one-time model load and, per file, the worker's own processing
time, the audio duration, and the resulting real-time factor.  Because the
worker keeps the model resident, the load cost is paid once for the whole run
rather than once per file.

With more than one ``--placement`` the same files are run under each Core ML
compute placement and each placement's transcripts are hashed, so a faster
placement can be adopted only when its output is byte-identical to the
baseline placement's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

import transcribe_courses as transcriber


DEFAULT_PLACEMENT = (
    f"{transcriber.AUDIO_ENCODER_COMPUTE_UNITS}:"
    f"{transcriber.TEXT_DECODER_COMPUTE_UNITS}"
)
COMPUTE_UNIT_NAMES = ("cpuOnly", "cpuAndGPU", "cpuAndNeuralEngine", "all")


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def placement(raw: str) -> tuple[str, str]:
    encoder, separator, decoder = raw.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError(
            "placement must be ENCODER:DECODER, e.g. cpuAndNeuralEngine:cpuAndGPU"
        )
    for name in (encoder, decoder):
        if name not in COMPUTE_UNIT_NAMES:
            raise argparse.ArgumentTypeError(
                f"unknown compute unit {name!r}; expected one of "
                f"{', '.join(COMPUTE_UNIT_NAMES)}"
            )
    return encoder, decoder


def build_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Benchmark persistent-worker transcription only.  Supply "
            "direct-audio files copied to local SSD; ffmpeg extraction and "
            "transcript installation are excluded."
        )
    )
    result.add_argument("audio", nargs="+", type=Path)
    result.add_argument("--runs", type=positive_int, default=3)
    result.add_argument("--timeout", type=positive_int, default=3600)
    result.add_argument(
        "--placement",
        dest="placements",
        action="append",
        type=placement,
        help=(
            "ENCODER:DECODER compute placement; repeat to compare placements. "
            f"Defaults to {DEFAULT_PLACEMENT}."
        ),
    )
    result.add_argument("--timestamps", action="store_true")
    result.add_argument("--language", default=transcriber.DEFAULT_LANGUAGE)
    result.add_argument("--json", dest="json_path", type=Path)
    result.add_argument(
        "--transcript-dir",
        type=Path,
        help="write each placement's transcripts here for manual diffing",
    )
    return result


def audio_duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    duration = float(completed.stdout.strip())
    if duration <= 0:
        raise ValueError(f"non-positive audio duration for {path}")
    return duration


def run_placement(
    worker_path: str,
    encoder: str,
    decoder: str,
    audio_files: list[Path],
    durations: dict[Path, float],
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Load one worker at this placement and time every file through it.

    Production pins the placement to the module constants so a stray
    environment variable cannot silently change what runs.  Benchmarking is the
    one place that deliberately overrides them.
    """

    transcriber.AUDIO_ENCODER_COMPUTE_UNITS = encoder
    transcriber.TEXT_DECODER_COMPUTE_UNITS = decoder
    transcriber.shutdown_worker()

    worker = transcriber.active_worker(worker_path)
    load_started = time.monotonic()
    worker.start()
    load_wall_seconds = time.monotonic() - load_started
    ready = worker.ready or {}
    reported_load = ready.get("model_load_seconds")

    files: list[dict[str, object]] = []
    transcripts: dict[str, str] = {}
    try:
        for audio in audio_files:
            duration = durations[audio]
            samples: list[float] = []
            transcript = ""
            for _ in range(arguments.runs):
                started = time.monotonic()
                frame = worker.transcribe(
                    audio,
                    arguments.timeout,
                    language=(
                        None
                        if arguments.language.casefold() == "auto"
                        else arguments.language
                    ),
                    timestamps=arguments.timestamps,
                )
                elapsed = time.monotonic() - started
                if frame.get("type") != "result":
                    raise RuntimeError(
                        f"worker returned {frame.get('type')} for {audio}: "
                        f"{frame.get('message')}"
                    )
                text, _duration, worker_seconds, segments = (
                    transcriber.validate_worker_result(frame)
                )
                if arguments.timestamps:
                    rendered, error = transcriber.timestamped_transcript(segments)
                    if error:
                        raise RuntimeError(error)
                    transcript = rendered or ""
                else:
                    transcript = text.strip()
                samples.append(elapsed)
                del worker_seconds
            best = min(samples)
            transcripts[audio.name] = transcript
            files.append(
                {
                    "file": str(audio),
                    "audio_seconds": duration,
                    "wall_seconds_best": best,
                    "wall_seconds_median": statistics.median(samples),
                    "wall_seconds_all": samples,
                    "rtf_best": duration / best if best > 0 else None,
                    "sha256": hashlib.sha256(
                        transcript.encode("utf-8")
                    ).hexdigest(),
                    "characters": len(transcript),
                }
            )
            print(
                f"  {audio.name}: audio={duration:.1f}s "
                f"best={best:.2f}s rtf={duration / best:.1f}x "
                f"sha={files[-1]['sha256'][:12]}",
                flush=True,
            )
    finally:
        transcriber.shutdown_worker()

    if arguments.transcript_dir is not None:
        target = arguments.transcript_dir / f"{encoder}-{decoder}"
        target.mkdir(parents=True, exist_ok=True)
        for name, text in transcripts.items():
            (target / f"{name}.txt").write_text(text, encoding="utf-8")

    total_audio = sum(durations[audio] for audio in audio_files)
    total_best = sum(float(entry["wall_seconds_best"]) for entry in files)
    return {
        "encoder_compute_units": encoder,
        "text_decoder_compute_units": decoder,
        "model_load_seconds_reported": reported_load,
        "model_load_seconds_wall": load_wall_seconds,
        "files": files,
        "total_audio_seconds": total_audio,
        "total_best_seconds": total_best,
        "aggregate_rtf": total_audio / total_best if total_best > 0 else None,
        "combined_sha256": hashlib.sha256(
            "\x00".join(
                transcripts[audio.name] for audio in audio_files
            ).encode("utf-8")
        ).hexdigest(),
    }


def main() -> int:
    arguments = build_parser().parse_args()
    audio_files = [path.expanduser().resolve(strict=True) for path in arguments.audio]
    placements = arguments.placements or [placement(DEFAULT_PLACEMENT)]

    programs, info, error = transcriber.bootstrap_worker()
    if error or programs is None or programs.worker is None or info is None:
        print(f"error: {error}", flush=True)
        return 2
    print(
        f"worker={programs.worker}\n"
        f"model={transcriber.MODEL}\n"
        f"argmax={transcriber.ARGMAX_REQUIRED_REVISION}",
        flush=True,
    )

    durations = {audio: audio_duration(audio) for audio in audio_files}
    results = []
    for encoder, decoder in placements:
        print(f"placement encoder={encoder} decoder={decoder}", flush=True)
        result = run_placement(
            programs.worker,
            encoder,
            decoder,
            audio_files,
            durations,
            arguments,
        )
        load = result["model_load_seconds_wall"]
        assert isinstance(load, float)
        print(
            f"  load={load:.1f}s aggregate_rtf={result['aggregate_rtf']:.1f}x "
            f"combined_sha={str(result['combined_sha256'])[:12]}",
            flush=True,
        )
        results.append(result)

    baseline = results[0]
    for result in results[1:]:
        result["matches_baseline_transcript"] = (
            result["combined_sha256"] == baseline["combined_sha256"]
        )
    baseline["matches_baseline_transcript"] = True

    payload = {
        "model": transcriber.MODEL,
        "model_path": str(transcriber.MODEL_PATH),
        "argmax_revision": transcriber.ARGMAX_REQUIRED_REVISION,
        "worker": programs.worker,
        "runs_per_file": arguments.runs,
        "timestamps": arguments.timestamps,
        "language": arguments.language,
        "placements": results,
    }
    if arguments.json_path is not None:
        arguments.json_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {arguments.json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

