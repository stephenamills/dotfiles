#!/usr/bin/env python3
"""Safely transcribe course media with one persistent WhisperKit worker.

Every supplied course root is read-only except for its top-level
``transcripts/`` directory. Live runs stream discovery and transcription in one
pass; ``--scan`` and ``--dry-run`` retain the complete fail-closed preflight
before any live work can create output directories, process-owned ``.part``
files, or absent ``.txt`` transcripts.

This is a simplified derivative of ``bulk_transcribe_network_whisperkit.py``.
Its intentionally fixed M5 Pro configuration is:

* model: ``large-v3-v20240930_turbo``
* task: native-language transcription (with recognized Language-tree codes)
* chunking: VAD
* audio encoder: CPU + Neural Engine
* text decoder: CPU + GPU
* mel spectrogram: WhisperKit's CPU + GPU default
* concurrent VAD workers: 16
* word timestamps: disabled

Transcription runs through one long-lived ``whisperkit-worker`` child that keeps
the Core ML model resident across every file in a run, with exactly one request
in flight. The worker is built from vendored Swift source against one pinned
clean Argmax checkout, and its decoding options reproduce those
``whisperkit-cli transcribe`` would build for the same invocation. There is no
fallback to ``whisperkit-cli``: a worker that cannot build, load, or answer is a
run failure. Video and uncommon audio containers first require one ffmpeg
conversion subprocess.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass, field, replace
import errno
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import selectors
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterator
import unicodedata


MODEL = "large-v3-v20240930_turbo"
MODEL_ROOT = Path(
    os.environ.get("WHISPERKIT_MODEL_ROOT")
    or Path.home() / "Documents/huggingface/models/argmaxinc/whisperkit-coreml"
)
MODEL_PATH = MODEL_ROOT / f"openai_whisper-{MODEL}"
MODEL_REQUIRED_BUNDLES = ("AudioEncoder.mlmodelc", "TextDecoder.mlmodelc")
DEFAULT_LANGUAGE = "en"
LANGUAGE_PATH_CODES = {
    "chinese (cantonese)": "yue",
    "french": "fr",
    "greek": "el",
    "latin": "la",
    "russian": "ru",
    "spanish": "es",
    "thai": "th",
}
CHUNKING_STRATEGY = "vad"
AUDIO_ENCODER_COMPUTE_UNITS = "cpuAndNeuralEngine"
TEXT_DECODER_COMPUTE_UNITS = "cpuAndGPU"
CONCURRENT_WORKERS = 16
DEFAULT_TRANSCRIBE_TIMEOUT_SECONDS = 600
DEFAULT_TRANSCRIBE_RETRIES = 1
DEFAULT_EXTRACT_RETRIES = 1
DEFAULT_TIMESTAMP_INTERVAL_SECONDS = 120
CHILD_TERMINATE_GRACE_SECONDS = 10
# A cold Core ML load of the turbo model, including Neural Engine
# specialization, has been measured at roughly 90 seconds on this machine.  The
# ready timeout is deliberately several times that so a slow first load after an
# OS update is never mistaken for a hung worker.
WORKER_READY_TIMEOUT_SECONDS = 600
WORKER_BUILD_TIMEOUT_SECONDS = 3600
WORKER_CHECK_TIMEOUT_SECONDS = 120
WORKER_DUPLICATE_RESPONSE_GRACE_SECONDS = 0.01
# A resident Core ML model degrades over a long run: after a few hundred files a
# worker starts failing to allocate IOSurface-backed buffers and then returns
# empty output indefinitely.  Recycling the worker well before that point costs
# one warm model load (well under a second) and bounds the growth.
WORKER_RECYCLE_REQUEST_LIMIT = 100
WORKER_SOURCE = Path(__file__).resolve().parent / "whisperkit-worker"
WORKER_CACHE_ROOT = Path.home() / ".agents" / "cache" / "whisperkit-worker"
# The worker may only be built against this exact Argmax revision, checked out
# clean.  Both the path and the revision are folded into the cache fingerprint.
ARGMAX_SOURCE_PATH = Path(
    os.environ.get("ARGMAX_OSS_SWIFT_PATH")
    or Path(__file__).resolve().parent.parent / "argmax-oss-swift"
)
ARGMAX_REQUIRED_REVISION = "dcf3a00f0ae4d5b57bc0aad92063b102b70d5fd1"
# Directories holding one of these manifests are self-contained source
# repositories shipped alongside a course, not lesson media.  Anything below
# them (bundled UI sounds, sample clips, node_modules fixtures) is pruned during
# discovery so it never becomes a transcript.
SOURCE_MANIFEST_NAMES = frozenset(
    {
        "cargo.toml",
        "composer.json",
        "gemfile",
        "go.mod",
        "package.json",
        "package.swift",
        "pom.xml",
        "pubspec.yaml",
        "pyproject.toml",
        "requirements.txt",
        "build.gradle",
        "build.gradle.kts",
    }
)
LEGACY_WHISPER_TOKEN_PATTERN = re.compile(r"<\|[^|\r\n]*\|>")
TIMESTAMP_CLOCK_PATTERN = r"\d{2,}:[0-5]\d:[0-5]\d"
LEADING_TIMESTAMP_PATTERN = re.compile(
    rf"\A(?:\ufeff)?\[(?:"
    rf"{TIMESTAMP_CLOCK_PATTERN}|"
    rf"{TIMESTAMP_CLOCK_PATTERN}\.\d{{3}} --> "
    rf"{TIMESTAMP_CLOCK_PATTERN}\.\d{{3}}"
    rf")\](?=\s|\Z)"
)

DIRECT_AUDIO_EXTENSIONS = frozenset(
    {
        ".flac",
        ".m4a",
        ".mp3",
        ".wav",
    }
)
# WAV files are commonly bundled as short game/UI sound effects.  They are
# intentionally ignored by course discovery rather than sent to WhisperKit.
IGNORED_MEDIA_EXTENSIONS = frozenset({".wav"})
AUDIO_EXTENSIONS = DIRECT_AUDIO_EXTENSIONS | frozenset(
    {
        ".aac",
        ".ac3",
        ".aif",
        ".aiff",
        ".amr",
        ".ape",
        ".caf",
        ".mka",
        ".opus",
        ".ra",
        ".wma",
    }
)
VIDEO_EXTENSIONS = frozenset(
    {
        ".3gp",
        ".asf",
        ".avi",
        ".f4v",
        ".flv",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".mts",
        ".mxf",
        ".ogv",
        ".rm",
        ".rmvb",
        ".ts",
        ".vob",
        ".webm",
        ".wmv",
    }
)
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
AMBIGUOUS_MPEG_TS_EXTENSION = ".ts"
MPEG_TS_PACKET_SIZES = (188, 192, 204)
MPEG_TS_MIN_SYNC_PACKETS = 4
MPEG_TS_PROBE_BYTES = max(MPEG_TS_PACKET_SIZES) * (
    MPEG_TS_MIN_SYNC_PACKETS + 1
)
RENAME_EXCL = 0x00000004
RESUME_STATE_VERSION = 4
SUPPORTED_RESUME_STATE_VERSIONS = frozenset({1, 2, 3, 4})
# v3 serialized the retired engine selector.  Both recognized values now mean
# the same thing -- one persistent WhisperKit worker -- so both migrate, but an
# unrecognized value still means the checkpoint was written by something this
# script does not understand.
LEGACY_ENGINE_VALUES = frozenset({"whisperkit", "parakeet"})
COMMAND_NAME = "transcribe-courses"
