#!/usr/bin/env python3
"""Minimal --check worker used only by the installed-command smoke test."""

import json
import os
from pathlib import Path
import sys


if sys.argv[1:] != ["--check"]:
    raise SystemExit("fake worker supports only --check")

print(
    json.dumps(
        {
            "type": "check",
            "ready": True,
            "engine": "whisperkit",
            "model": "large-v3-v20240930_turbo",
            "model_path": os.environ["WHISPERKIT_WORKER_MODEL_PATH"],
            "audio_encoder_compute_units": "cpuAndNeuralEngine",
            "text_decoder_compute_units": "cpuAndGPU",
            "argmax_revision": "dcf3a00f0ae4d5b57bc0aad92063b102b70d5fd1",
            "worker_version": Path(sys.argv[0]).parent.name,
            "model_load_seconds": 0.0,
        },
        separators=(",", ":"),
    )
)
