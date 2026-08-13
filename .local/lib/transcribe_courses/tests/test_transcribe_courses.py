#!/usr/bin/env python3
"""Deterministic tests for the standalone transcription package and CLI."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock

import transcribe_courses as subject


def mpeg_transport_stream_bytes(
    packet_size: int = 188,
    packet_count: int = 4,
    sync_offset: int = 0,
) -> bytes:
    packet = bytearray(packet_size)
    packet[sync_offset] = 0x47
    return bytes(packet) * packet_count


class FlushRecordingStream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.parent_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)

    def tearDown(self) -> None:
        os.close(self.parent_fd)
        self.temporary.cleanup()

    def install(
        self,
        transcript: str,
        destination_name: str = "lesson.txt",
        *,
        overwrite: bool = False,
        overwrite_empty: bool = False,
        expected_snapshot: subject.TranscriptSnapshot | None = None,
    ) -> subject.InstallResult:
        return subject.install_transcript(
            self.parent_fd,
            destination_name,
            transcript,
            destination_path=self.directory / destination_name,
            overwrite=overwrite,
            overwrite_empty=overwrite_empty,
            expected_snapshot=expected_snapshot,
        )

    def part_names(self) -> list[str]:
        return sorted(
            path.name
            for path in self.directory.iterdir()
            if path.name.endswith(".part")
        )

    def test_successful_exclusive_rename_has_exact_content_and_no_part(self) -> None:
        def rename_part(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> bool:
            os.rename(
                source_name,
                destination_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            return True

        with mock.patch.object(
            subject,
            "exclusive_rename",
            side_effect=rename_part,
        ):
            result = self.install("café 🐍")

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        self.assertEqual(
            (self.directory / "lesson.txt").read_bytes(),
            "café 🐍\n".encode("utf-8"),
        )
        self.assertEqual(self.part_names(), [])

    def test_unsupported_rename_uses_exclusive_destination_creation(self) -> None:
        with mock.patch.object(subject, "exclusive_rename", return_value=False):
            result = self.install("SMB fallback")

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        self.assertEqual(
            (self.directory / "lesson.txt").read_bytes(),
            b"SMB fallback\n",
        )
        self.assertEqual(self.part_names(), [])

    def test_rename_eexist_skips_and_preserves_existing_bytes(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"SENTINEL")
        conflict = FileExistsError(errno.EEXIST, "exists", destination.name)

        with mock.patch.object(
            subject,
            "exclusive_rename",
            side_effect=conflict,
        ):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.SKIPPED)
        self.assertEqual(destination.read_bytes(), b"SENTINEL")
        self.assertEqual(self.part_names(), [])

    def test_fallback_creation_eexist_skips_and_preserves_existing_bytes(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"SENTINEL")

        with mock.patch.object(subject, "exclusive_rename", return_value=False):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.SKIPPED)
        self.assertEqual(destination.read_bytes(), b"SENTINEL")
        self.assertEqual(self.part_names(), [])

    def test_unrelated_part_file_eexist_is_a_failure_not_a_skip(self) -> None:
        part_name = f".lesson.txt.{os.getpid()}.fixed.part"
        (self.directory / part_name).write_bytes(b"UNRELATED")

        with mock.patch.object(subject.secrets, "token_hex", return_value="fixed"):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertEqual((self.directory / part_name).read_bytes(), b"UNRELATED")

    def test_destination_write_failure_removes_verified_partial_file(self) -> None:
        real_write = subject.write_payload_and_sync
        call_count = 0

        def fail_second_write(file_descriptor: int, payload: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_write(file_descriptor, payload)
                return
            os.write(file_descriptor, b"partial")
            os.close(file_descriptor)
            raise OSError(errno.EIO, "injected write failure")

        with (
            mock.patch.object(subject, "exclusive_rename", return_value=False),
            mock.patch.object(
                subject,
                "write_payload_and_sync",
                side_effect=fail_second_write,
            ),
        ):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertIn("injected write failure", result.detail or "")
        self.assertFalse((self.directory / "lesson.txt").exists())
        self.assertEqual(self.part_names(), [])

    def test_destination_fsync_failure_removes_verified_partial_file(self) -> None:
        real_fsync = subject.os.fsync
        call_count = 0

        def fail_second_fsync(file_descriptor: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_fsync(file_descriptor)
                return
            raise OSError(errno.EIO, "injected fsync failure")

        with (
            mock.patch.object(subject, "exclusive_rename", return_value=False),
            mock.patch.object(subject.os, "fsync", side_effect=fail_second_fsync),
        ):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertIn("injected fsync failure", result.detail or "")
        self.assertFalse((self.directory / "lesson.txt").exists())
        self.assertEqual(self.part_names(), [])

    def test_destination_close_failure_removes_verified_partial_file(self) -> None:
        real_fdopen = subject.os.fdopen
        call_count = 0

        class CloseFailingOutput:
            def __init__(self, output: io.BufferedWriter):
                self.output = output

            def write(self, payload: bytes) -> int:
                return self.output.write(payload)

            def flush(self) -> None:
                self.output.flush()

            def fileno(self) -> int:
                return self.output.fileno()

            def close(self) -> None:
                self.output.close()
                raise OSError(errno.EIO, "injected close failure")

        def fail_second_close(
            file_descriptor: int,
            *args: object,
            **kwargs: object,
        ) -> io.BufferedWriter | CloseFailingOutput:
            nonlocal call_count
            call_count += 1
            output = real_fdopen(file_descriptor, *args, **kwargs)
            if call_count == 2:
                return CloseFailingOutput(output)
            return output

        with (
            mock.patch.object(subject, "exclusive_rename", return_value=False),
            mock.patch.object(subject.os, "fdopen", side_effect=fail_second_close),
        ):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertIn("injected close failure", result.detail or "")
        self.assertFalse((self.directory / "lesson.txt").exists())
        self.assertEqual(self.part_names(), [])

    def test_cleanup_failure_leaves_partial_and_reports_manual_review_path(
        self,
    ) -> None:
        real_write = subject.write_payload_and_sync
        real_unlink = subject.os.unlink
        call_count = 0

        def fail_second_write(file_descriptor: int, payload: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_write(file_descriptor, payload)
                return
            os.write(file_descriptor, b"partial")
            os.close(file_descriptor)
            raise OSError(errno.EIO, "injected write failure")

        def block_destination_cleanup(
            path: str,
            *,
            dir_fd: int | None = None,
        ) -> None:
            if path == "lesson.txt":
                raise PermissionError(errno.EACCES, "injected cleanup failure")
            real_unlink(path, dir_fd=dir_fd)

        with (
            mock.patch.object(subject, "exclusive_rename", return_value=False),
            mock.patch.object(
                subject,
                "write_payload_and_sync",
                side_effect=fail_second_write,
            ),
            mock.patch.object(
                subject.os,
                "unlink",
                side_effect=block_destination_cleanup,
            ),
        ):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertEqual(
            (self.directory / "lesson.txt").read_bytes(),
            b"partial",
        )
        self.assertIn("manual review", result.detail or "")
        self.assertIn(str(self.directory / "lesson.txt"), result.detail or "")
        self.assertEqual(self.part_names(), [])

    def test_identity_mismatch_leaves_partial_for_manual_review(self) -> None:
        real_write = subject.write_payload_and_sync
        real_stat = subject.os.stat
        witness = self.directory / "witness.txt"
        witness.write_bytes(b"witness")
        call_count = 0

        def fail_second_write(file_descriptor: int, payload: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_write(file_descriptor, payload)
                return
            os.write(file_descriptor, b"partial")
            os.close(file_descriptor)
            raise OSError(errno.EIO, "injected write failure")

        def substitute_identity(
            path: str,
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            if path == "lesson.txt":
                return real_stat(witness)
            return real_stat(
                path,
                dir_fd=dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with (
            mock.patch.object(subject, "exclusive_rename", return_value=False),
            mock.patch.object(
                subject,
                "write_payload_and_sync",
                side_effect=fail_second_write,
            ),
            mock.patch.object(subject.os, "stat", side_effect=substitute_identity),
        ):
            result = self.install("replacement")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertEqual(
            (self.directory / "lesson.txt").read_bytes(),
            b"partial",
        )
        self.assertIn("identity could not be verified", result.detail or "")
        self.assertIn("manual review", result.detail or "")

    def test_keyboard_interrupt_removes_verified_partial_destination(self) -> None:
        real_write = subject.write_payload_and_sync
        call_count = 0

        def interrupt_second_write(file_descriptor: int, payload: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_write(file_descriptor, payload)
                return
            os.write(file_descriptor, b"partial")
            os.close(file_descriptor)
            raise KeyboardInterrupt

        with (
            mock.patch.object(subject, "exclusive_rename", return_value=False),
            mock.patch.object(
                subject,
                "write_payload_and_sync",
                side_effect=interrupt_second_write,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.install("replacement")

        self.assertFalse((self.directory / "lesson.txt").exists())
        self.assertEqual(self.part_names(), [])

    def test_utf8_and_trailing_newline_behavior(self) -> None:
        cases = (
            ("plain", b"plain\n"),
            ("already\n", b"already\n"),
            ("two\n\n", b"two\n\n"),
            ("雪 café", "雪 café\n".encode("utf-8")),
        )
        with mock.patch.object(subject, "exclusive_rename", return_value=False):
            for index, (transcript, expected) in enumerate(cases):
                with self.subTest(transcript=transcript):
                    name = f"lesson-{index}.txt"
                    result = self.install(transcript, name)
                    self.assertIs(
                        result.status,
                        subject.InstallStatus.INSTALLED,
                    )
                    self.assertEqual((self.directory / name).read_bytes(), expected)
        self.assertEqual(self.part_names(), [])

    def test_empty_transcript_is_rejected_without_creating_destination(self) -> None:
        result = self.install(" \n ")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertFalse((self.directory / "lesson.txt").exists())
        self.assertIn("empty transcript", result.detail or "")

    def test_overwrite_atomically_replaces_existing_regular_file(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"SENTINEL")

        result = self.install("replacement", overwrite=True)

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        self.assertEqual(destination.read_bytes(), b"replacement\n")
        self.assertEqual(self.part_names(), [])

    def test_overwrite_failure_preserves_existing_file(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"SENTINEL")

        with mock.patch.object(
            subject.os,
            "replace",
            side_effect=OSError(errno.EIO, "injected replace failure"),
        ):
            result = self.install("replacement", overwrite=True)

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertEqual(destination.read_bytes(), b"SENTINEL")
        self.assertEqual(self.part_names(), [])

    def test_overwrite_empty_replaces_only_zero_byte_destination(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"")

        result = self.install("replacement", overwrite_empty=True)

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        self.assertEqual(destination.read_bytes(), b"replacement\n")
        self.assertEqual(self.part_names(), [])

    def test_overwrite_empty_preserves_destination_that_became_nonempty(
        self,
    ) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"FINISHED")

        result = self.install("replacement", overwrite_empty=True)

        self.assertIs(result.status, subject.InstallStatus.SKIPPED)
        self.assertEqual(destination.read_bytes(), b"FINISHED")
        self.assertEqual(self.part_names(), [])

    def test_timestamp_upgrade_atomically_replaces_unchanged_destination(
        self,
    ) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"plain transcript")
        _payload, snapshot = subject.read_regular_file_snapshot(destination)

        result = self.install(
            "[00:00:00]\nreplacement",
            expected_snapshot=snapshot,
        )

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        self.assertEqual(
            destination.read_bytes(),
            b"[00:00:00]\nreplacement\n",
        )
        self.assertEqual(self.part_names(), [])

    def test_timestamp_upgrade_preserves_concurrently_changed_destination(
        self,
    ) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"plain transcript")
        _payload, snapshot = subject.read_regular_file_snapshot(destination)
        destination.write_bytes(b"[00:00:00]\nconcurrent replacement\n")

        result = self.install(
            "[00:00:00]\nstale replacement",
            expected_snapshot=snapshot,
        )

        self.assertIs(result.status, subject.InstallStatus.SKIPPED)
        self.assertEqual(
            destination.read_bytes(),
            b"[00:00:00]\nconcurrent replacement\n",
        )
        self.assertIn("changed after preflight", result.detail or "")
        self.assertEqual(self.part_names(), [])

    def test_timestamp_upgrade_detects_path_swap_after_content_check(
        self,
    ) -> None:
        destination = self.directory / "lesson.txt"
        archived = self.directory / "lesson-old.txt"
        destination.write_bytes(b"plain transcript")
        _payload, snapshot = subject.read_regular_file_snapshot(destination)
        real_read = subject.read_regular_file_snapshot

        def swap_after_read(
            path: str | Path,
            *,
            dir_fd: int | None = None,
        ) -> tuple[bytes, subject.TranscriptSnapshot]:
            result = real_read(path, dir_fd=dir_fd)
            os.replace(
                destination.name,
                archived.name,
                src_dir_fd=self.parent_fd,
                dst_dir_fd=self.parent_fd,
            )
            destination.write_bytes(b"[00:00:00]\nconcurrent replacement\n")
            return result

        with mock.patch.object(
            subject,
            "read_regular_file_snapshot",
            side_effect=swap_after_read,
        ):
            result = self.install(
                "[00:00:00]\nstale replacement",
                expected_snapshot=snapshot,
            )

        self.assertIs(result.status, subject.InstallStatus.SKIPPED)
        self.assertEqual(
            destination.read_bytes(),
            b"[00:00:00]\nconcurrent replacement\n",
        )
        self.assertIn("changed after verification", result.detail or "")
        self.assertEqual(self.part_names(), [])

    def test_empty_timestamp_upgrade_result_preserves_old_bytes(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"plain transcript")
        _payload, snapshot = subject.read_regular_file_snapshot(destination)

        result = self.install(" \n", expected_snapshot=snapshot)

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertEqual(destination.read_bytes(), b"plain transcript")
        self.assertEqual(self.part_names(), [])

    def test_failed_timestamp_upgrade_replace_preserves_old_bytes(self) -> None:
        destination = self.directory / "lesson.txt"
        destination.write_bytes(b"plain transcript")
        _payload, snapshot = subject.read_regular_file_snapshot(destination)

        with mock.patch.object(
            subject.os,
            "replace",
            side_effect=OSError(errno.EIO, "injected replace failure"),
        ):
            result = self.install(
                "[00:00:00]\nreplacement",
                expected_snapshot=snapshot,
            )

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertEqual(destination.read_bytes(), b"plain transcript")
        self.assertEqual(self.part_names(), [])


class WhisperKitDirectTests(unittest.TestCase):
    def test_language_paths_use_native_whisper_codes(self) -> None:
        expected = {
            "Chinese (Cantonese)": "yue",
            "French": "fr",
            "Greek": "el",
            "Latin": "la",
            "Russian": "ru",
            "Spanish": "es",
            "Thai": "th",
        }

        for language, code in expected.items():
            with self.subTest(language=language):
                course = subject.Course(
                    Path("/tmp/transcription-fixtures/Language")
                    / language
                    / "Course"
                )
                effective = subject.effective_options_for_course(
                    subject.TranscriptionOptions(),
                    course,
                )
                self.assertEqual(effective.language, code)

    def test_explicit_language_override_and_auto_are_preserved(self) -> None:
        course = subject.Course(
            Path("/tmp/transcription-fixtures/Language/Spanish/Course")
        )

        explicit = subject.effective_options_for_course(
            subject.TranscriptionOptions(language="fr"),
            course,
        )
        automatic = subject.effective_options_for_course(
            subject.TranscriptionOptions(language=None),
            course,
        )

        self.assertEqual(explicit.language, "fr")
        self.assertIsNone(automatic.language)

    def test_worker_request_carries_language_and_timestamp_mode(self) -> None:
        worker = mock.Mock()
        worker.completed_requests = 0
        worker.transcribe.return_value = {
            "type": "result",
            "text": "text",
            "segments": [{"start": 0.0, "end": 1.0, "text": "text"}],
            "duration": 1.0,
            "processing_time": 0.1,
        }
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            subject, "active_worker", return_value=worker
        ):
            subject.run_whisperkit_worker(
                "/worker",
                Path("/audio.wav"),
                subject.TranscriptionOptions(
                    language="fr",
                    timestamps=True,
                    retries=0,
                    timeout_seconds=123,
                ),
                Path(temporary),
            )

        worker.transcribe.assert_called_once_with(
            Path("/audio.wav"),
            None,
            language="fr",
            timestamps=True,
        )

    def test_auto_language_is_forwarded_as_null_and_plain_mode_disables_timestamps(
        self,
    ) -> None:
        worker = mock.Mock()
        worker.completed_requests = 0
        worker.transcribe.return_value = {
            "type": "result",
            "text": "text",
            "segments": [],
            "duration": 1.0,
            "processing_time": 0.1,
        }
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            subject, "active_worker", return_value=worker
        ):
            subject.run_whisperkit_worker(
                "/worker",
                Path("/audio.wav"),
                subject.TranscriptionOptions(language=None, retries=0),
                Path(temporary),
            )

        self.assertIsNone(worker.transcribe.call_args.kwargs["language"])
        self.assertFalse(worker.transcribe.call_args.kwargs["timestamps"])

    def test_worker_environment_pins_model_path_and_compute_placement(self) -> None:
        environment = subject.worker_environment()

        self.assertEqual(
            environment["WHISPERKIT_WORKER_MODEL_PATH"],
            str(subject.MODEL_PATH),
        )
        self.assertEqual(
            environment["WHISPERKIT_AUDIO_ENCODER_COMPUTE_UNITS"],
            subject.AUDIO_ENCODER_COMPUTE_UNITS,
        )
        self.assertEqual(
            environment["WHISPERKIT_TEXT_DECODER_COMPUTE_UNITS"],
            subject.TEXT_DECODER_COMPUTE_UNITS,
        )

    def test_timeout_restarts_worker_then_retry_succeeds(self) -> None:
        worker = mock.Mock()
        worker.completed_requests = 0
        worker.transcribe.side_effect = [
            subject.WorkerRequestTimeout("WhisperKit worker timed out after 1 seconds"),
            {
                "type": "result",
                "text": "  recovered transcript  \n",
                "segments": [],
                "duration": 1.0,
                "processing_time": 0.1,
            },
        ]
        errors = FlushRecordingStream()

        with (
            tempfile.TemporaryDirectory() as temporary,
            redirect_stderr(errors),
            mock.patch.object(subject, "active_worker", return_value=worker),
            mock.patch.object(subject, "reset_worker") as reset,
        ):
            directory = Path(temporary)
            review_log = subject.ReviewLog(directory / "review.txt")
            transcript, error = subject.run_whisperkit_worker(
                "/worker",
                Path("/audio.wav"),
                subject.TranscriptionOptions(timeout_seconds=1, retries=1),
                directory,
                review_log,
                Path("/source/lesson.mp4"),
            )
            review_text = review_log.path.read_text(encoding="utf-8")

        self.assertEqual(transcript, "recovered transcript")
        self.assertIsNone(error)
        reset.assert_called_once_with("request timeout")
        self.assertIn("WHISPERKIT RETRY", errors.getvalue())
        self.assertIn("WHISPERKIT TIMEOUT", review_text)
        self.assertIn("/source/lesson.mp4", review_text)

    def test_ffmpeg_timeout_kills_owned_child(self) -> None:
        process = mock.Mock()
        process.communicate.side_effect = [
            subject.subprocess.TimeoutExpired(["ffmpeg"], 1),
            ("", ""),
        ]
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                subject.subprocess,
                "Popen",
                return_value=process,
            ),
            mock.patch.object(subject, "terminate_owned_child") as terminate,
        ):
            directory = Path(temporary)
            error = subject.extract_audio(
                directory / "lesson.mp4",
                directory / "audio.wav",
                "ffmpeg",
                timeout_seconds=1,
            )

        terminate.assert_called_once_with(process)
        self.assertIn("timed out after 1 seconds", error or "")

    def test_empty_results_are_retried_then_fail(self) -> None:
        worker = mock.Mock()
        worker.completed_requests = 0
        worker.transcribe.return_value = {
            "type": "result",
            "text": " \n",
            "segments": [],
            "duration": 1.0,
            "processing_time": 0.1,
        }

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            subject, "active_worker", return_value=worker
        ):
            transcript, error = subject.run_whisperkit_worker(
                "/worker",
                Path("/audio.wav"),
                subject.TranscriptionOptions(retries=1),
                Path(temporary),
            )

        self.assertIsNone(transcript)
        self.assertIn("empty transcript", error or "")

    def test_timestamp_segments_are_rendered_for_tutorial_cross_reference(
        self,
    ) -> None:
        worker = mock.Mock()
        worker.completed_requests = 0
        worker.transcribe.return_value = {
            "type": "result",
            "text": "First step Second step",
            "segments": [
                {"start": 1.25, "end": 3.5, "text": " First step "},
                {"start": 125.0, "end": 130.125, "text": "Second step"},
            ],
            "duration": 200.0,
            "processing_time": 4.0,
        }

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            subject, "active_worker", return_value=worker
        ):
            transcript, error = subject.run_whisperkit_worker(
                "/worker",
                Path("/lesson.wav"),
                subject.TranscriptionOptions(timestamps=True, retries=0),
                Path(temporary),
            )

        self.assertIsNone(error)
        self.assertEqual(
            transcript,
            "[00:00:00]\nFirst step\n\n"
            "[00:02:00]\nSecond step",
        )

    def test_zero_timestamp_interval_emits_every_segment_range(self) -> None:
        transcript, error = subject.timestamped_transcript(
            [{"start": 1.25, "end": 3.5, "text": "Step"}],
            interval_seconds=0,
        )

        self.assertIsNone(error)
        self.assertEqual(
            transcript,
            "[00:00:01.250 --> 00:00:03.500] Step",
        )

    def test_malformed_segments_fail_without_producing_a_transcript(self) -> None:
        for segments in (
            "not-a-list",
            [{"start": 0.0, "end": 1.0}],
            [{"start": None, "end": 1.0, "text": "x"}],
            [{"start": float("inf"), "end": 1.0, "text": "x"}],
        ):
            with self.subTest(segments=segments):
                transcript, error = subject.timestamped_transcript(segments, 120)
                self.assertIsNone(transcript)
                self.assertIn("invalid WhisperKit segments", error or "")

    def test_worker_timing_metrics_record_audio_seconds_and_rtf(self) -> None:
        worker = mock.Mock()
        worker.completed_requests = 0
        worker.transcribe.return_value = {
            "type": "result",
            "text": "text",
            "segments": [],
            "duration": 600.0,
            "processing_time": 12.0,
        }

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            subject, "active_worker", return_value=worker
        ):
            subject.run_whisperkit_worker(
                "/worker",
                Path("/audio.wav"),
                subject.TranscriptionOptions(retries=0),
                Path(temporary),
            )
            metrics = subject._LAST_ENGINE_METRICS

        self.assertIsNotNone(metrics)
        assert metrics is not None
        self.assertEqual(metrics.audio_seconds, 600.0)
        self.assertGreater(metrics.engine_seconds, 0)
        self.assertIsNotNone(metrics.rtf)

    def test_direct_item_installs_with_overwrite_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "lesson.wav"
            media.write_bytes(b"audio")
            course = subject.Course(root)
            item = subject.WorkItem(
                course=course,
                media=media,
                relative_media=Path("lesson.wav"),
                relative_output=Path("lesson.txt"),
                identity=subject.identity_from_stat(media.stat()),
                input_kind="direct",
                selected=True,
            )
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with (
                    mock.patch.object(
                        subject,
                        "run_whisperkit_worker",
                        return_value=("transcript", None),
                    ) as direct,
                    mock.patch.object(
                        subject,
                        "install_transcript",
                        return_value=subject.InstallResult.installed(),
                    ) as install,
                ):
                    options = subject.TranscriptionOptions(overwrite=True)
                    result = subject.transcribe_item(
                        item,
                        subject.Programs("ffmpeg", "/worker"),
                        parent_fd,
                        options,
                    )
            finally:
                os.close(parent_fd)

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        self.assertEqual(direct.call_args.args[0], "/worker")
        self.assertEqual(direct.call_args.args[1], media)
        install.assert_called_once_with(
            parent_fd,
            "lesson.txt",
            "transcript",
            destination_path=root / "transcripts" / "lesson.txt",
            overwrite=True,
            overwrite_empty=False,
            expected_snapshot=None,
        )


class TimestampUpgradeTests(unittest.TestCase):
    OPTIONS = subject.TranscriptionOptions(
        timestamps=True,
        upgrade_timestamps=True,
    )

    def setUp(self) -> None:
        self.worker_bootstrap = mock.patch.object(
            subject,
            "bootstrap_worker",
            return_value=(
                subject.Programs("/bin/true", "/worker"),
                None,
                None,
            ),
        )
        self.worker_bootstrap.start()
        self.addCleanup(self.worker_bootstrap.stop)

    def test_timestamp_upgrade_classifier(self) -> None:
        cases = {
            "empty": (b"", True),
            "whitespace": (" \n\t\u2003".encode(), True),
            "plain": (b"ordinary transcript", True),
            "periodic": (b"[00:00:00]\nTranscript", False),
            "periodic-later-interval": (b"[12:34:56]\nTranscript", False),
            "exact-segment": (
                b"[00:00:01.250 --> 00:00:03.500] Transcript",
                False,
            ),
            "legacy-token": (
                b"[00:00:00]\nTranscript <|0.00|> <|en|>",
                True,
            ),
            "malformed-leading-marker": (b"[00:00:00]Transcript", True),
            "leading-whitespace": (b" [00:00:00]\nTranscript", True),
            "invalid-utf8": (b"[00:00:00]\n\xff", True),
        }

        for name, (payload, expected) in cases.items():
            with self.subTest(name=name):
                self.assertIs(
                    subject.transcript_needs_timestamp_upgrade(payload),
                    expected,
                )

    def make_migration_course(
        self,
        base: Path,
    ) -> tuple[Path, dict[str, bytes | None]]:
        course_root = base / "Course"
        transcripts = course_root / "transcripts"
        transcripts.mkdir(parents=True)
        destinations: dict[str, bytes | None] = {
            "empty": b"",
            "exact": b"[00:00:01.250 --> 00:00:03.500] Finished",
            "legacy": b"[00:00:00]\nText <|endoftext|>",
            "missing": None,
            "periodic": b"[00:01:00]\nFinished",
            "plain": b"Plain transcript",
            "whitespace": b" \n\t",
        }
        for stem, payload in destinations.items():
            (course_root / f"{stem}.mp4").write_bytes(b"media")
            if payload is not None:
                (transcripts / f"{stem}.txt").write_bytes(payload)
        return course_root, destinations

    def preflight(
        self,
        course_root: Path,
        limit: int | None = None,
    ) -> subject.Preflight:
        with mock.patch.object(
            subject,
            "resolve_program",
            return_value=("/bin/true", None),
        ):
            return subject.perform_preflight(
                [str(course_root)],
                limit=limit,
                options=self.OPTIONS,
            )

    def test_preflight_selects_only_missing_and_upgrade_needed_transcripts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root, _destinations = self.make_migration_course(
                Path(temporary)
            )
            preflight = self.preflight(course_root)

        selected = {
            item.relative_media.stem
            for item in preflight.items
            if item.selected
        }
        self.assertEqual(
            selected,
            {"empty", "legacy", "missing", "plain", "whitespace"},
        )
        self.assertEqual(preflight.work_total, 5)
        clean = {
            item.relative_media.stem
            for item in preflight.items
            if item.existing and not item.timestamp_upgrade_needed
        }
        self.assertEqual(clean, {"exact", "periodic"})
        for item in preflight.items:
            if item.existing:
                self.assertIsNotNone(item.transcript_snapshot)

    def test_upgrade_limit_and_summary_distinguish_clean_skips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root, _destinations = self.make_migration_course(
                Path(temporary)
            )
            preflight = self.preflight(course_root, limit=2)
            summary = subject.summary_for_course(
                preflight,
                preflight.courses[0],
            )
            output = FlushRecordingStream()
            with redirect_stdout(output):
                subject.print_preflight(preflight, dry_run=True)

        self.assertEqual(
            {
                item.relative_media.stem
                for item in preflight.items
                if item.selected
            },
            {"empty", "legacy"},
        )
        self.assertEqual(summary.discovered, 7)
        self.assertEqual(summary.would_transcribe, 2)
        self.assertEqual(summary.limited, 3)
        self.assertEqual(summary.skipped, 2)
        self.assertIn(
            "would_transcribe=2 limited=3",
            output.getvalue(),
        )
        self.assertEqual(output.getvalue().count(" LIMIT "), 3)

    def test_upgrade_mode_is_mutually_exclusive_and_enables_timestamps(
        self,
    ) -> None:
        parser = subject.build_parser()
        parsed = parser.parse_args(["--upgrade-timestamps", "/course"])
        options = subject.options_from_args(parsed)

        self.assertTrue(options.upgrade_timestamps)
        self.assertTrue(options.timestamps)
        settings = FlushRecordingStream()
        with redirect_stdout(settings):
            subject.print_settings(options)
        self.assertIn("timestamps=120s", settings.getvalue())
        self.assertIn("overwrite=timestamp-upgrade", settings.getvalue())
        for conflict in ("--overwrite", "--overwrite-empty"):
            with (
                self.subTest(conflict=conflict),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                parser.parse_args(
                    ["--upgrade-timestamps", conflict, "/course"]
                )
            self.assertEqual(raised.exception.code, 2)

    def test_dry_run_and_live_use_upgrade_timestamp_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            transcripts = course_root / "transcripts"
            transcripts.mkdir(parents=True)
            media = course_root / "lesson.mp4"
            media.write_bytes(b"media")
            (transcripts / "lesson.txt").write_text(
                "plain transcript",
                encoding="utf-8",
            )
            preflight = self.preflight(course_root)
            dry_output = FlushRecordingStream()
            live_output = FlushRecordingStream()

            with redirect_stdout(dry_output):
                subject.print_preflight(preflight, dry_run=True)
            with (
                redirect_stdout(live_output),
                mock.patch.object(
                    subject,
                    "transcribe_item",
                    return_value=subject.InstallResult.installed(),
                ),
            ):
                result = subject.run_live(preflight, title=None)

        self.assertEqual(result, 0)
        self.assertIn("UPGRADE-TIMESTAMPS", dry_output.getvalue())
        self.assertIn("UPGRADE-TIMESTAMPS", live_output.getvalue())
        self.assertIn(
            "attempted=1 succeeded=1 skipped=0 limited=0 failed=0",
            live_output.getvalue(),
        )

    def test_rescanning_current_course_skips_already_upgraded_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            transcripts = course_root / "transcripts"
            transcripts.mkdir(parents=True)
            (course_root / "lesson.mp4").write_bytes(b"media")
            destination = transcripts / "lesson.txt"
            destination.write_text("plain transcript", encoding="utf-8")

            before = self.preflight(course_root)
            destination.write_text(
                "[00:00:00]\nupgraded transcript\n",
                encoding="utf-8",
            )
            resumed = self.preflight(course_root)

        self.assertEqual(before.work_total, 1)
        self.assertTrue(before.items[0].selected)
        self.assertEqual(resumed.work_total, 0)
        self.assertFalse(resumed.items[0].selected)
        self.assertFalse(resumed.items[0].timestamp_upgrade_needed)

    def test_transcribe_item_passes_preflight_snapshot_to_installer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            transcripts = course_root / "transcripts"
            transcripts.mkdir(parents=True)
            media = course_root / "lesson.mp3"
            media.write_bytes(b"audio")
            destination = transcripts / "lesson.txt"
            destination.write_text("plain transcript", encoding="utf-8")
            preflight = self.preflight(course_root)
            item = preflight.items[0]
            parent_fd = os.open(
                transcripts,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            try:
                with (
                    mock.patch.object(
                        subject,
                        "run_whisperkit_worker",
                        return_value=("[00:00:00]\nreplacement", None),
                    ),
                    mock.patch.object(
                        subject,
                        "install_transcript",
                        return_value=subject.InstallResult.installed(),
                    ) as install,
                ):
                    result = subject.transcribe_item(
                        item,
                        preflight.programs,
                        parent_fd,
                        self.OPTIONS,
                    )
            finally:
                os.close(parent_fd)

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        install.assert_called_once_with(
            parent_fd,
            "lesson.txt",
            "[00:00:00]\nreplacement",
            destination_path=(
                item.course.transcript_root / item.relative_output
            ),
            overwrite=False,
            overwrite_empty=False,
            expected_snapshot=item.transcript_snapshot,
        )

    def test_plain_upgrade_result_is_rejected_before_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            transcripts = course_root / "transcripts"
            transcripts.mkdir(parents=True)
            (course_root / "lesson.mp3").write_bytes(b"audio")
            destination = transcripts / "lesson.txt"
            destination.write_text("old plain transcript", encoding="utf-8")
            preflight = self.preflight(course_root)
            parent_fd = os.open(
                transcripts,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            try:
                with mock.patch.object(
                    subject,
                    "run_whisperkit_worker",
                    return_value=("new but still plain", None),
                ):
                    result = subject.transcribe_item(
                        preflight.items[0],
                        preflight.programs,
                        parent_fd,
                        self.OPTIONS,
                    )
            finally:
                os.close(parent_fd)
            remaining = destination.read_text(encoding="utf-8")

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertIn("no clean leading timestamp", result.detail or "")
        self.assertEqual(remaining, "old plain transcript")


class ResumeCheckpointTests(unittest.TestCase):
    def test_checkpoint_round_trip_and_completion_are_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            roots = ["/courses/One", "/courses/Two"]
            options = subject.TranscriptionOptions(
                language="es",
                timestamps=True,
                timestamp_interval_seconds=90,
                timeout_seconds=77,
                retries=3,
                overwrite=True,
            )
            checkpoint = subject.ResumeCheckpoint.create(
                roots,
                ["/authors/Author"],
                "author-roots",
                next_index=1,
                directory=directory,
                options=options,
            )

            loaded = subject.ResumeCheckpoint.load(checkpoint.path)
            self.assertEqual(loaded.course_roots, roots)
            self.assertEqual(loaded.next_index, 1)
            self.assertEqual(loaded.current_course, "/courses/Two")
            self.assertEqual(loaded.status, "active")
            self.assertEqual(loaded.options, options)

            loaded.set_cursor(2, "complete")
            completed = subject.ResumeCheckpoint.load(checkpoint.path)

            self.assertEqual(completed.next_index, 2)
            self.assertIsNone(completed.current_course)
            self.assertEqual(completed.status, "complete")
            self.assertEqual(
                list(directory.glob("*.part")),
                [],
            )

    def test_checkpoint_persists_timestamp_upgrade_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            options = subject.TranscriptionOptions(
                timestamps=True,
                timestamp_interval_seconds=60,
                upgrade_timestamps=True,
            )
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/authors/Author"],
                "author-roots",
                directory=Path(temporary),
                options=options,
            )

            loaded = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertEqual(loaded.options, options)
        self.assertTrue(loaded.options.timestamps)
        self.assertTrue(loaded.options.upgrade_timestamps)

    def test_checkpoint_round_trips_topic_root_source_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = subject.ResumeCheckpoint.create(
                ["/topics/Example Topic/Author/Course"],
                ["/topics/Example Topic"],
                "topic-roots",
                directory=Path(temporary),
            )

            loaded = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertEqual(loaded.source_mode, "topic-roots")
        self.assertEqual(loaded.source_roots, ["/topics/Example Topic"])

    def test_checkpoint_without_upgrade_field_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=Path(temporary),
            )
            payload = json.loads(
                checkpoint.path.read_text(encoding="utf-8")
            )
            payload["transcription_options"].pop("upgrade_timestamps")
            checkpoint.path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            loaded = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertFalse(loaded.options.upgrade_timestamps)
        self.assertFalse(loaded.options.timestamps)

    def test_resume_course_index_selects_exact_course(self) -> None:
        roots = [
            "/courses/Before",
            "/courses/Example Course",
            "/courses/After",
        ]

        index = subject.resume_course_index(
            roots,
            "/courses/Example Course",
        )

        self.assertEqual(index, 1)

    def test_prior_author_command_is_parsed_as_data(self) -> None:
        command = (
            "python3 ~/.agents/skills/batch-transcribe-courses/scripts/"
            "transcribe_courses.py \\\n"
            "  --author-roots --skip-preflight --limit 7 -- \\\n"
            "  '/tmp/transcription-fixtures/Music/Example Author/First Course' "
            "'/tmp/transcription-fixtures/Music/Example Author/Second Course **'"
        )

        recovered = subject.recover_author_invocation(command)

        self.assertEqual(recovered.limit, 7)
        self.assertEqual(
            recovered.roots,
            [
                "/tmp/transcription-fixtures/Music/Example Author/First Course",
                "/tmp/transcription-fixtures/Music/Example Author/Second Course **",
            ],
        )
        self.assertEqual(recovered.source_mode, "author-roots")

    def test_prior_topic_command_is_parsed_as_data(self) -> None:
        command = (
            "transcribe-courses --topic-roots --skip-preflight --limit=4 "
            "-- '/tmp/transcription-fixtures/Example Topic'"
        )

        recovered = subject.recover_author_invocation(command)

        self.assertEqual(recovered.limit, 4)
        self.assertEqual(
            recovered.roots,
            ["/tmp/transcription-fixtures/Example Topic"],
        )
        self.assertEqual(recovered.source_mode, "topic-roots")

    def test_prior_author_command_without_skip_flag_is_parsed(self) -> None:
        recovered = subject.recover_author_invocation(
            "python3 transcribe_courses.py --author-roots -- '/tmp/Author'"
        )
        self.assertEqual(recovered.roots, ["/tmp/Author"])
        self.assertEqual(recovered.source_mode, "author-roots")


class StreamingTests(unittest.TestCase):
    def test_stream_skips_typescript_but_keeps_mpeg_transport_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            root.mkdir()
            (root / "drizzle.config.ts").write_text(
                'import { defineConfig } from "drizzle-kit";\n',
                encoding="utf-8",
            )
            (root / "lesson.ts").write_bytes(mpeg_transport_stream_bytes())
            processed: list[str] = []

            def process(
                item: subject.WorkItem,
                _programs: subject.Programs,
                _options: subject.TranscriptionOptions,
                summary: subject.CourseSummary,
                _prefix: str,
                _review: subject.ReviewLog | None,
            ) -> None:
                processed.append(item.relative_media.name)
                summary.succeeded += 1

            with (
                mock.patch.object(subject, "process_item", side_effect=process),
                mock.patch.object(subject, "volume_is_live", return_value=True),
            ):
                summary, consumed, limited, failed = subject.stream_course(
                    subject.Course(root),
                    subject.Programs("ffmpeg", "/worker"),
                    subject.TranscriptionOptions(),
                    None,
                    None,
                    subject.ReviewLog(Path(temporary) / "review.txt"),
                    "1/1",
                )

        self.assertEqual(processed, ["lesson.ts"])
        self.assertEqual(summary.discovered, 1)
        self.assertEqual(consumed, 1)
        self.assertFalse(limited)
        self.assertTrue(failed)

    def test_stream_course_sorts_and_starts_before_walk_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            root.mkdir()
            for name in ("b.mp4", "a.mp4"):
                (root / name).write_bytes(b"media")
            walk_events: list[str] = []
            processed: list[str] = []

            def walk(*_args: object, **_kwargs: object):
                walk_events.append("yield-first")
                yield str(root), [], ["b.mp4", "a.mp4"]
                walk_events.append("walk-finished")

            def transcribe(item: subject.WorkItem, *_args: object) -> subject.InstallResult:
                processed.append(item.relative_media.name)
                self.assertEqual(walk_events, ["yield-first"])
                return subject.InstallResult.installed()

            with (
                mock.patch.object(subject.os, "walk", side_effect=walk),
                mock.patch.object(subject, "transcribe_item", side_effect=transcribe),
                mock.patch.object(subject, "volume_is_live", return_value=True),
            ):
                summary, consumed, limited, failed = subject.stream_course(
                    subject.Course(root),
                    subject.Programs("ffmpeg", "/worker"),
                    subject.TranscriptionOptions(),
                    None,
                    None,
                    subject.ReviewLog(Path(temporary) / "review.txt"),
                    "1/1",
                )

        self.assertEqual(processed, ["a.mp4", "b.mp4"])
        self.assertEqual(summary.succeeded, 2)
        self.assertEqual(consumed, 2)
        self.assertFalse(limited)
        self.assertFalse(failed)
        self.assertEqual(walk_events, ["yield-first", "walk-finished"])

    def test_stream_collision_is_reviewed_and_does_not_fail_course(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            root.mkdir()
            (root / "first.mp4").write_bytes(b"media")
            (root / "second.mp4").write_bytes(b"media")
            review = subject.ReviewLog(Path(temporary) / "review.txt")
            with (
                mock.patch.object(subject, "collision_key", return_value="same"),
                mock.patch.object(
                    subject,
                    "transcribe_item",
                    return_value=subject.InstallResult.installed(),
                ),
                mock.patch.object(subject, "volume_is_live", return_value=True),
            ):
                summary, consumed, limited, failed = subject.stream_course(
                    subject.Course(root),
                    subject.Programs("ffmpeg", "/worker"),
                    subject.TranscriptionOptions(),
                    None,
                    None,
                    review,
                    "1/1",
                )
            review_text = review.path.read_text(encoding="utf-8")

        self.assertEqual(summary.discovered, 2)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(consumed, 1)
        self.assertFalse(limited)
        self.assertFalse(failed)
        self.assertEqual(review.issue_count, 1)
        self.assertIn("OUTPUT COLLISION", review_text)

    def test_stream_missing_mirrored_directory_avoids_destination_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            (root / "Module").mkdir(parents=True)
            (root / "Module" / "lesson.mp4").write_bytes(b"media")
            with (
                mock.patch.object(subject, "destination_exists") as destination,
                mock.patch.object(
                    subject,
                    "process_item",
                    side_effect=lambda item, _programs, _options, summary, _prefix, _review: setattr(
                        summary, "succeeded", summary.succeeded + 1
                    ),
                ),
                mock.patch.object(subject, "volume_is_live", return_value=True),
            ):
                summary, _consumed, _limited, _failed = subject.stream_course(
                    subject.Course(root),
                    subject.Programs("ffmpeg", "/worker"),
                    subject.TranscriptionOptions(),
                    None,
                    None,
                    subject.ReviewLog(Path(temporary) / "review.txt"),
                    "1/1",
                )

        destination.assert_not_called()
        self.assertEqual(summary.succeeded, 1)

    def test_stream_upgrade_reads_only_existing_file_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            (root / "Module").mkdir(parents=True)
            (root / "Module" / "existing.mp4").write_bytes(b"media")
            (root / "Module" / "missing.mp4").write_bytes(b"media")
            transcript_dir = root / "transcripts" / "Module"
            transcript_dir.mkdir(parents=True)
            (transcript_dir / "existing.txt").write_text(
                "plain transcript", encoding="utf-8"
            )
            original = subject.read_regular_file_snapshot
            snapshots: list[str] = []

            def snapshot(path: str | Path, *, dir_fd: int | None = None):
                snapshots.append(os.fspath(path))
                return original(path, dir_fd=dir_fd)

            with (
                mock.patch.object(subject, "read_regular_file_snapshot", side_effect=snapshot),
                mock.patch.object(
                    subject,
                    "transcribe_item",
                    return_value=subject.InstallResult.installed(),
                ),
                mock.patch.object(subject, "volume_is_live", return_value=True),
            ):
                summary, _consumed, _limited, _failed = subject.stream_course(
                    subject.Course(root),
                    subject.Programs("ffmpeg", "/worker"),
                    subject.TranscriptionOptions(
                        timestamps=True,
                        upgrade_timestamps=True,
                    ),
                    None,
                    None,
                    subject.ReviewLog(Path(temporary) / "review.txt"),
                    "1/1",
                )

        self.assertEqual(summary.succeeded, 2)
        self.assertEqual(snapshots, ["existing.txt"])

    def test_stream_limit_stops_walk_and_reports_paused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            root.mkdir()
            for name in ("a.mp4", "b.mp4"):
                (root / name).write_bytes(b"media")
            with (
                mock.patch.object(
                    subject,
                    "process_item",
                    side_effect=lambda item, _programs, _options, summary, _prefix, _review: setattr(
                        summary, "succeeded", summary.succeeded + 1
                    ),
                ),
                mock.patch.object(subject, "volume_is_live", return_value=True),
            ):
                summary, consumed, limited, failed = subject.stream_course(
                    subject.Course(root),
                    subject.Programs("ffmpeg", "/worker"),
                    subject.TranscriptionOptions(),
                    1,
                    None,
                    subject.ReviewLog(Path(temporary) / "review.txt"),
                    "1/1",
                )

        self.assertEqual(summary.discovered, 2)
        self.assertEqual(consumed, 1)
        self.assertTrue(limited)
        self.assertFalse(failed)


class OutputContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.worker_preparation = mock.patch.object(
            subject,
            "prepare_worker_for_live_run",
            return_value=None,
        )
        self.worker_preparation.start()
        self.addCleanup(self.worker_preparation.stop)
        self.worker_bootstrap = mock.patch.object(
            subject,
            "bootstrap_worker",
            return_value=(
                subject.Programs("/bin/true", "/worker"),
                None,
                None,
            ),
        )
        self.worker_bootstrap.start()
        self.addCleanup(self.worker_bootstrap.stop)

    def make_item(
        self,
        course: subject.Course,
        source: str,
        destination: str,
        *,
        existing: bool = False,
        selected: bool = False,
    ) -> subject.WorkItem:
        return subject.WorkItem(
            course=course,
            media=course.root / source,
            relative_media=Path(source),
            relative_output=Path(destination),
            identity=subject.MediaIdentity(1, 2, 3, 4),
            input_kind="direct",
            existing=existing,
            selected=selected,
        )

    def make_preflight(
        self,
        course: subject.Course,
        items: list[subject.WorkItem],
        options: subject.TranscriptionOptions = subject.TranscriptionOptions(),
    ) -> subject.Preflight:
        return subject.Preflight(
            courses=[course],
            items=items,
            programs=subject.Programs("ffmpeg", "/worker"),
            work_total=sum(item.selected for item in items),
            options=options,
        )

    def test_dry_run_prints_course_root_and_every_mapping(self) -> None:
        course = subject.Course(Path("/library/Provider/Course"))
        items = [
            self.make_item(course, "existing.mp3", "existing.txt", existing=True),
            self.make_item(course, "ready.mp3", "ready.txt", selected=True),
            self.make_item(course, "limited.mp3", "limited.txt"),
        ]
        preflight = self.make_preflight(course, items)
        output = FlushRecordingStream()

        with redirect_stdout(output):
            subject.print_preflight(preflight, dry_run=True)

        rendered = output.getvalue()
        self.assertIn("Course: /library/Provider/Course", rendered)
        for source, destination in (
            ("existing.mp3", "existing.txt"),
            ("ready.mp3", "ready.txt"),
            ("limited.mp3", "limited.txt"),
        ):
            self.assertIn(
                f"{source} -> transcripts/{destination}",
                rendered,
            )
        self.assertIn(" WOULD (direct) ready.mp3", rendered)
        self.assertGreater(output.flush_count, 0)

    def test_each_argument_is_used_directly_as_a_course_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = base / "Course One"
            second = base / "Course Two"
            (first / "Module").mkdir(parents=True)
            second.mkdir()
            (first / "Module" / "Lesson.mp4").write_bytes(b"media")
            (second / "Intro.m4a").write_bytes(b"media")
            resolved_first = first.resolve()
            resolved_second = second.resolve()

            with mock.patch.object(
                subject,
                "resolve_program",
                return_value=("/bin/true", None),
            ):
                preflight = subject.perform_preflight(
                    [str(first), str(second)],
                    limit=None,
                )

        self.assertEqual(
            [course.root for course in preflight.courses],
            [resolved_first, resolved_second],
        )
        self.assertEqual(
            [
                (item.course.root, item.relative_media, item.relative_output)
                for item in preflight.items
            ],
            [
                (
                    resolved_first,
                    Path("Module/Lesson.mp4"),
                    Path("Module/Lesson.txt"),
                ),
                (resolved_second, Path("Intro.m4a"), Path("Intro.txt")),
            ],
        )

    def test_overwrite_selects_existing_transcripts_without_deleting_first(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            transcripts = course_root / "transcripts"
            transcripts.mkdir(parents=True)
            (course_root / "lesson.mp4").write_bytes(b"media")
            destination = transcripts / "lesson.txt"
            destination.write_bytes(b"SENTINEL")
            with mock.patch.object(
                subject,
                "resolve_program",
                return_value=("/bin/true", None),
            ):
                normal = subject.perform_preflight(
                    [str(course_root)],
                    limit=None,
                )
                overwrite = subject.perform_preflight(
                    [str(course_root)],
                    limit=None,
                    options=subject.TranscriptionOptions(overwrite=True),
                )
            remaining_bytes = destination.read_bytes()

        self.assertFalse(normal.items[0].selected)
        self.assertEqual(normal.work_total, 0)
        self.assertTrue(overwrite.items[0].selected)
        self.assertEqual(overwrite.work_total, 1)
        self.assertEqual(remaining_bytes, b"SENTINEL")

    def test_overwrite_empty_selects_missing_and_zero_byte_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            transcripts = course_root / "transcripts"
            transcripts.mkdir(parents=True)
            for name in ("empty.mp4", "finished.mp4", "missing.mp4"):
                (course_root / name).write_bytes(b"media")
            (transcripts / "empty.txt").write_bytes(b"")
            (transcripts / "finished.txt").write_bytes(b"FINISHED")
            with mock.patch.object(
                subject,
                "resolve_program",
                return_value=("/bin/true", None),
            ):
                preflight = subject.perform_preflight(
                    [str(course_root)],
                    limit=None,
                    options=subject.TranscriptionOptions(
                        overwrite_empty=True
                    ),
                )

        selected = {
            item.relative_media.name
            for item in preflight.items
            if item.selected
        }
        self.assertEqual(selected, {"empty.mp4", "missing.mp4"})
        finished = next(
            item
            for item in preflight.items
            if item.relative_media.name == "finished.mp4"
        )
        self.assertTrue(finished.existing)
        self.assertFalse(finished.existing_empty)
        self.assertFalse(finished.selected)

    def test_author_roots_expand_exactly_one_directory_level(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_author = base / "First Author"
            second_author = base / "Second Author"
            alpha = first_author / "Alpha Course"
            zulu = first_author / "zulu Course"
            bravo = second_author / "Bravo Course"
            (alpha / "Module One").mkdir(parents=True)
            zulu.mkdir(parents=True)
            bravo.mkdir(parents=True)
            (first_author / "cover.jpg").write_bytes(b"not a course")
            (alpha / "Module One" / "Lesson.mp4").write_bytes(b"media")
            review_log = subject.ReviewLog(base / "review.txt")

            expanded = subject.expand_author_roots(
                [str(first_author), str(second_author)],
                review_log,
            )

        self.assertEqual(
            expanded,
            [
                str(alpha.resolve()),
                str(zulu.resolve()),
                str(bravo.resolve()),
            ],
        )
        self.assertNotIn(str((alpha / "Module One").resolve()), expanded)
        self.assertEqual(review_log.issue_count, 0)
        self.assertFalse(review_log.path.exists())

    def test_empty_author_root_is_logged_while_valid_author_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            empty_author = base / "Empty Author"
            missing_author = base / "Missing Author"
            valid_author = base / "Valid Author"
            course = valid_author / "Course"
            empty_author.mkdir()
            course.mkdir(parents=True)
            (empty_author / "README.txt").write_text("not a course")
            review_log = subject.ReviewLog(base / "review.txt")

            expanded = subject.expand_author_roots(
                [str(empty_author), str(missing_author), str(valid_author)],
                review_log,
            )
            review_text = review_log.path.read_text(encoding="utf-8")

        self.assertEqual(expanded, [str(course.resolve())])
        self.assertEqual(review_log.issue_count, 2)
        self.assertIn("Manual Review", review_text)
        self.assertIn(str(empty_author.resolve()), review_text)
        self.assertIn("contains no immediate course directories", review_text)
        self.assertIn(str(missing_author), review_text)
        self.assertIn("invalid input root", review_text)

    def test_topic_roots_expand_authors_then_courses_and_ignore_omega(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            topic_alpha = base / "Topic Alpha"
            topic_beta = base / "Topic Beta"
            topic_alpha_course = (
                topic_alpha / "Author One" / "Course One"
            )
            alpha_course = (
                topic_beta / "alpha Author" / "Alpha Course"
            )
            zulu_course = (
                topic_beta / "alpha Author" / "zulu Course"
            )
            bravo_course = (
                topic_beta / "Zulu Author" / "Bravo Course"
            )
            for path in (
                topic_alpha_course,
                alpha_course / "Module",
                zulu_course,
                bravo_course,
                topic_beta / "Ω - Hands On" / "Ignored" / "Course",
                topic_beta / "Ω - Urban Design" / "Ignored" / "Course",
                topic_beta / "Ω Books" / "Ignored" / "Course",
                topic_beta / "Ω More" / "Ignored" / "Course",
                topic_beta
                / "alpha Author"
                / "Ω Private Courses"
                / "Ignored Course",
            ):
                path.mkdir(parents=True)
            (alpha_course / "Module" / "Lesson.mp4").write_bytes(b"media")
            (topic_beta / "cover.jpg").write_bytes(b"not an author")
            review_log = subject.ReviewLog(base / "review.txt")

            expanded = subject.expand_topic_roots(
                [str(topic_alpha), str(topic_beta)],
                review_log,
            )

        self.assertEqual(
            expanded,
            [
                str(topic_alpha_course.resolve()),
                str(alpha_course.resolve()),
                str(zulu_course.resolve()),
                str(bravo_course.resolve()),
            ],
        )
        self.assertNotIn(str((alpha_course / "Module").resolve()), expanded)
        self.assertEqual(review_log.issue_count, 0)
        self.assertFalse(review_log.path.exists())

    def test_topic_mode_prunes_omega_media_directories_recursively(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            normal_module = course_root / "Module"
            omega_top = course_root / "Ω Private"
            omega_nested = normal_module / "Ω Hidden"
            omega_top.mkdir(parents=True)
            omega_nested.mkdir(parents=True)
            (course_root / "intro.mp4").write_bytes(b"media")
            (normal_module / "lesson.mp4").write_bytes(b"media")
            (omega_top / "secret.mp4").write_bytes(b"media")
            (omega_nested / "secret.mp4").write_bytes(b"media")

            topic_items, topic_errors = subject.discover_media(
                subject.Course(
                    course_root.resolve(),
                    ignore_omega_directories=True,
                )
            )
            normal_items, normal_errors = subject.discover_media(
                subject.Course(course_root.resolve())
            )

        self.assertEqual(topic_errors, [])
        self.assertEqual(normal_errors, [])
        self.assertEqual(
            [item.relative_media.as_posix() for item in topic_items],
            ["intro.mp4", "Module/lesson.mp4"],
        )
        self.assertEqual(len(normal_items), 4)

    def test_empty_and_missing_topic_roots_are_logged_while_valid_continues(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            empty_topic = base / "Empty Topic"
            missing_topic = base / "Missing Topic"
            valid_topic = base / "Valid Topic"
            course = valid_topic / "Author" / "Course"
            (empty_topic / "Ω Books" / "Ignored").mkdir(parents=True)
            course.mkdir(parents=True)
            review_log = subject.ReviewLog(base / "review.txt")

            expanded = subject.expand_topic_roots(
                [str(empty_topic), str(missing_topic), str(valid_topic)],
                review_log,
            )
            review_text = review_log.path.read_text(encoding="utf-8")

        self.assertEqual(expanded, [str(course.resolve())])
        self.assertEqual(review_log.issue_count, 2)
        self.assertIn(str(empty_topic.resolve()), review_text)
        self.assertIn(
            "contains no immediate author directories after Ω exclusions",
            review_text,
        )
        self.assertIn(str(missing_topic), review_text)
        self.assertIn("invalid input root", review_text)

    def test_direct_cli_unsupported_audio_container_uses_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            course_root.mkdir()
            (course_root / "direct.mp3").write_bytes(b"media")
            (course_root / "convert.aac").write_bytes(b"media")

            with mock.patch.object(
                subject,
                "resolve_program",
                return_value=("/bin/true", None),
            ):
                preflight = subject.perform_preflight(
                    [str(course_root)],
                    limit=None,
                )

        self.assertEqual(
            {
                item.relative_media.name: item.input_kind
                for item in preflight.items
            },
            {
                "convert.aac": "ffmpeg",
                "direct.mp3": "direct",
            },
        )

    def test_ts_discovery_distinguishes_typescript_from_transport_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            course_root.mkdir()
            source = course_root / "drizzle.config.ts"
            source.write_text(
                'import { config } from "dotenv";\nexport default config;\n',
                encoding="utf-8",
            )
            media = course_root / "lesson.ts"
            media.write_bytes(mpeg_transport_stream_bytes())

            items, errors = subject.discover_media(subject.Course(course_root))
            direct = subject.direct_media_files(course_root)
            source_is_transport_stream = (
                subject.has_mpeg_transport_stream_signature(source)
            )
            media_is_transport_stream = (
                subject.has_mpeg_transport_stream_signature(media)
            )

        self.assertEqual(len(errors), 1)
        self.assertIn("drizzle.config.ts", errors[0])
        self.assertIn("unsupported file type .ts", errors[0])
        self.assertFalse(source_is_transport_stream)
        self.assertTrue(media_is_transport_stream)
        self.assertEqual(
            [item.relative_media.name for item in items],
            ["lesson.ts"],
        )
        self.assertEqual([path.name for path in direct], ["lesson.ts"])

    def test_ogg_and_unknown_regular_files_are_failed_and_not_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = Path(temporary) / "Course"
            course_root.mkdir()
            (course_root / "sound.ogg").write_bytes(b"audio")
            (course_root / "notes.xyz").write_bytes(b"unknown")
            (course_root / "lesson.mp3").write_bytes(b"audio")

            items, errors = subject.discover_media(subject.Course(course_root))

        self.assertEqual([item.relative_media.name for item in items], ["lesson.mp3"])
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("sound.ogg" in error for error in errors))
        self.assertTrue(any("notes.xyz" in error for error in errors))
        self.assertTrue(all("allowlisted media types only" in error for error in errors))

    def test_ts_signature_accepts_common_packet_strides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                188: mpeg_transport_stream_bytes(188),
                192: mpeg_transport_stream_bytes(192, sync_offset=4),
                204: mpeg_transport_stream_bytes(204),
            }
            for packet_size, payload in fixtures.items():
                path = root / f"packet-{packet_size}.ts"
                path.write_bytes(payload)
                with self.subTest(packet_size=packet_size):
                    self.assertTrue(
                        subject.has_mpeg_transport_stream_signature(path)
                    )

    def test_music_tree_discovers_only_video_containers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = (
                Path(temporary) / "fixture" / "Music" / "Author" / "Course"
            )
            nested = course_root / "Samples"
            nested.mkdir(parents=True)
            (course_root / "lesson.mp4").write_bytes(b"video")
            (course_root / "song.mp3").write_bytes(b"audio")
            (nested / "instrument.wav").write_bytes(b"audio")
            (nested / "preview.m4a").write_bytes(b"audio")

            items, errors = subject.discover_media(
                subject.Course(course_root.resolve())
            )

        self.assertEqual(len(errors), 2)
        self.assertTrue(all("allowlisted media types only" in error for error in errors))
        self.assertEqual(
            [item.relative_media.as_posix() for item in items],
            ["lesson.mp4"],
        )

    def test_non_music_tree_still_discovers_audio_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course_root = (
                Path(temporary) / "fixture" / "General" / "Author" / "Course"
            )
            course_root.mkdir(parents=True)
            (course_root / "lesson.mp4").write_bytes(b"video")
            (course_root / "lecture.mp3").write_bytes(b"audio")

            items, errors = subject.discover_media(
                subject.Course(course_root.resolve())
            )

        self.assertEqual(errors, [])
        self.assertEqual(
            [item.relative_media.name for item in items],
            ["lecture.mp3", "lesson.mp4"],
        )

    def test_discovery_mode_option_is_not_supported(self) -> None:
        errors = FlushRecordingStream()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            subject.build_parser().parse_args(
                ["--discover-course-roots", "/library"]
            )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments", errors.getvalue())

    def test_live_preflight_is_compact_and_flushes_one_course_summary(self) -> None:
        course = subject.Course(Path("/library/Course"))
        items = [
            self.make_item(course, "existing.mp3", "existing.txt", existing=True),
            self.make_item(course, "ready.mp3", "ready.txt", selected=True),
            self.make_item(course, "limited.mp3", "limited.txt"),
        ]
        preflight = self.make_preflight(course, items)
        output = FlushRecordingStream()

        with redirect_stdout(output):
            subject.print_preflight(preflight, dry_run=False)

        rendered = output.getvalue()
        self.assertEqual(rendered.count("PREFLIGHT course="), 1)
        self.assertIn(
            "discovered=3 skipped=1 ready=1 limited=1",
            rendered,
        )
        self.assertNotIn("ready.mp3", rendered)
        self.assertNotIn("-> transcripts/", rendered)
        self.assertGreater(output.flush_count, 0)

    def test_main_flushes_preflight_activity_before_scanning(self) -> None:
        output = FlushRecordingStream()
        course = subject.Course(Path("/course"))
        preflight = self.make_preflight(course, [])

        def inspect_initial_output(
            *_args: object,
            **_kwargs: object,
        ) -> subject.Preflight:
            self.assertTrue(output.getvalue().startswith("PREFLIGHT scanning "))
            self.assertGreater(output.flush_count, 0)
            return preflight

        with (
            redirect_stdout(output),
            mock.patch.object(
                subject,
                "perform_preflight",
                side_effect=inspect_initial_output,
            ),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
        ):
            return_code = subject.main(["--dry-run", "/course"])

        self.assertEqual(return_code, 0)
        self.assertEqual(output.getvalue().splitlines()[0].split()[0], "PREFLIGHT")

    def test_skip_preflight_processes_roots_one_at_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_root = base / "Course One"
            second_root = base / "Course Two"
            first_root.mkdir()
            second_root.mkdir()
            first = subject.Preflight(
                courses=[subject.Course(first_root.resolve())],
                items=[],
                programs=subject.Programs("ffmpeg", "/worker"),
                work_total=2,
            )
            second = subject.Preflight(
                courses=[subject.Course(second_root.resolve())],
                items=[],
                programs=subject.Programs("ffmpeg", "/worker"),
                work_total=1,
            )
            calls: list[tuple[str, str, int | None]] = []

            def preflight_one(
                roots: list[str],
                limit: int | None,
                _options: subject.TranscriptionOptions,
                *,
                ignore_omega_directories: bool = False,
                programs: subject.Programs | None = None,
            ) -> subject.Preflight:
                self.assertFalse(ignore_omega_directories)
                self.assertIsNotNone(programs)
                name = Path(roots[0]).name
                calls.append(("scan", name, limit))
                return first if name == first_root.name else second

            def run_one(
                preflight: subject.Preflight,
                _title: subject.ProcessTitle | None,
                _review_log: subject.ReviewLog | None,
            ) -> int:
                calls.append(
                    ("run", preflight.courses[0].name, preflight.work_total)
                )
                return 0

            output = FlushRecordingStream()
            with (
                redirect_stdout(output),
                mock.patch.object(subject, "print_settings"),
                mock.patch.object(
                    subject,
                    "perform_preflight",
                    side_effect=preflight_one,
                ),
                mock.patch.object(
                    subject,
                    "resolve_program",
                    return_value=("/bin/true", None),
                ),
                mock.patch.object(subject, "print_preflight"),
                mock.patch.object(subject, "run_live", side_effect=run_one),
            ):
                return_code = subject.run_fast_start(
                    [str(first_root), str(second_root)],
                    limit=3,
                    title=None,
                    scan=True,
                )

        self.assertEqual(return_code, 0)
        self.assertEqual(
            calls,
            [
                ("scan", "Course One", 3),
                ("run", "Course One", 2),
                ("scan", "Course Two", 1),
                ("run", "Course Two", 1),
            ],
        )
        self.assertLess(
            output.getvalue().index("course="),
            output.getvalue().index("Fast-start summary:"),
        )

    def test_fast_start_passes_topic_omega_exclusion_to_each_course(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            root.mkdir()
            preflight = subject.Preflight(
                courses=[
                    subject.Course(
                        root,
                        ignore_omega_directories=True,
                    )
                ],
                items=[],
                programs=subject.Programs("ffmpeg", "/worker"),
                work_total=0,
            )

            with (
                redirect_stdout(FlushRecordingStream()),
                mock.patch.object(subject, "print_settings"),
                mock.patch.object(
                    subject,
                    "perform_preflight",
                    return_value=preflight,
                ) as perform,
                mock.patch.object(
                    subject,
                    "bootstrap_worker",
                    return_value=(
                        subject.Programs("/bin/true", "/bin/true"),
                        None,
                        None,
                    ),
                ),
                mock.patch.object(subject, "print_preflight"),
                mock.patch.object(subject, "run_live", return_value=0),
            ):
                return_code = subject.run_fast_start(
                    [str(root)],
                    limit=None,
                    title=None,
                    roots_prevalidated=True,
                    ignore_omega_directories=True,
                    scan=True,
                )

        self.assertEqual(return_code, 0)
        perform.assert_called_once_with(
            [str(root)],
            None,
            subject.TranscriptionOptions(),
            ignore_omega_directories=True,
            programs=subject.Programs("/bin/true", "/bin/true"),
        )

    def test_interruption_checkpoint_stays_on_interrupted_course(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_root = base / "Course One"
            second_root = base / "Course Two"
            first_root.mkdir()
            second_root.mkdir()
            roots = [str(first_root), str(second_root)]
            checkpoint = subject.ResumeCheckpoint.create(
                roots,
                roots,
                "course-roots",
                directory=base / "state",
            )
            first = subject.Preflight(
                courses=[subject.Course(first_root)],
                items=[],
                programs=subject.Programs("ffmpeg", "/worker"),
                work_total=0,
            )

            with (
                redirect_stdout(FlushRecordingStream()),
                mock.patch.object(subject, "print_settings"),
                mock.patch.object(
                    subject,
                    "perform_preflight",
                    side_effect=[first, KeyboardInterrupt()],
                ),
                mock.patch.object(
                    subject,
                    "bootstrap_worker",
                    return_value=(
                        subject.Programs("/bin/true", "/bin/true"),
                        None,
                        None,
                    ),
                ),
                mock.patch.object(subject, "print_preflight"),
                mock.patch.object(subject, "run_live", return_value=0),
                self.assertRaises(KeyboardInterrupt),
            ):
                subject.run_fast_start(
                    roots,
                    limit=None,
                    title=None,
                    checkpoint=checkpoint,
                    roots_prevalidated=True,
                    scan=True,
                )

            resumed = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertEqual(resumed.next_index, 1)
        self.assertEqual(resumed.current_course, str(second_root))
        self.assertEqual(resumed.status, "active")

    def test_skip_preflight_continues_after_course_scan_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_root = base / "Course One"
            second_root = base / "Course Two"
            first_root.mkdir()
            second_root.mkdir()
            second = subject.Preflight(
                courses=[subject.Course(second_root.resolve())],
                items=[],
                programs=subject.Programs("ffmpeg", "/worker"),
                work_total=1,
            )
            errors = FlushRecordingStream()

            with (
                redirect_stdout(FlushRecordingStream()),
                redirect_stderr(errors),
                mock.patch.object(subject, "print_settings"),
                mock.patch.object(
                    subject,
                    "perform_preflight",
                    side_effect=[
                        subject.PreflightError(["injected scan failure"]),
                        second,
                    ],
                ),
                mock.patch.object(
                    subject,
                    "resolve_program",
                    return_value=("/bin/true", None),
                ),
                mock.patch.object(subject, "print_preflight"),
                mock.patch.object(subject, "run_live", return_value=0) as run_live,
            ):
                return_code = subject.run_fast_start(
                    [str(first_root), str(second_root)],
                    limit=None,
                    title=None,
                    review_log=subject.ReviewLog(base / "review.txt"),
                    scan=True,
                )
            review_text = (base / "review.txt").read_text(encoding="utf-8")

        self.assertEqual(return_code, 2)
        self.assertIn("injected scan failure", errors.getvalue())
        self.assertIn(
            "injected scan failure",
            review_text,
        )
        run_live.assert_called_once_with(second, None, mock.ANY)

    def test_main_skip_preflight_uses_fast_start_path(self) -> None:
        output = FlushRecordingStream()
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")
        with (
            redirect_stdout(output),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "validate_fast_start_roots",
                return_value=[Path("/course")],
            ),
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ),
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
            mock.patch.object(subject, "perform_preflight") as global_preflight,
        ):
            return_code = subject.main(
                ["--skip-preflight", "--limit", "10", "/course"]
        )

        self.assertEqual(return_code, 0)
        fast.assert_called_once_with(
            ["/course"],
            10,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=0,
            roots_prevalidated=True,
            ignore_omega_directories=False,
            scan=False,
        )
        global_preflight.assert_not_called()
        self.assertIn("FAST START roots=1 start=1 limit=10", output.getvalue())

    def test_main_persists_upgrade_mode_in_fast_start_checkpoint(self) -> None:
        output = FlushRecordingStream()
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")
        expected_options = subject.TranscriptionOptions(
            timestamps=True,
            timestamp_interval_seconds=60,
            upgrade_timestamps=True,
        )
        with (
            redirect_stdout(output),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "validate_fast_start_roots",
                return_value=[Path("/course")],
            ),
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ) as create,
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
        ):
            return_code = subject.main(
                [
                    "--skip-preflight",
                    "--upgrade-timestamps",
                    "--timestamp-interval",
                    "60",
                    "/course",
                ]
            )

        self.assertEqual(return_code, 0)
        create.assert_called_once_with(
            ["/course"],
            ["/course"],
            "course-roots",
            next_index=0,
            options=expected_options,
        )
        fast.assert_called_once_with(
            ["/course"],
            None,
            None,
            options=expected_options,
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=0,
            roots_prevalidated=True,
            ignore_omega_directories=False,
            scan=False,
        )

    def test_main_resume_uses_saved_cursor_without_expanding_or_validating(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            roots = [
                "/courses/Completed",
                "/courses/Interrupted",
                "/courses/Later",
            ]
            checkpoint = subject.ResumeCheckpoint.create(
                roots,
                ["/authors/Author"],
                "author-roots",
                next_index=1,
                directory=base,
            )
            output = FlushRecordingStream()

            with (
                redirect_stdout(output),
                mock.patch.object(
                    subject.ProcessTitle,
                    "capture",
                    return_value=None,
                ),
                mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
                mock.patch.object(subject, "expand_author_roots") as expand,
                mock.patch.object(subject, "validate_fast_start_roots") as validate,
            ):
                return_code = subject.main(
                    ["--resume", str(checkpoint.path)]
                )

        self.assertEqual(return_code, 0)
        fast.assert_called_once_with(
            roots,
            None,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=mock.ANY,
            start_index=1,
            roots_prevalidated=True,
            ignore_omega_directories=False,
            scan=False,
        )
        expand.assert_not_called()
        validate.assert_not_called()
        self.assertIn(
            "next=2/3 course=/courses/Interrupted",
            output.getvalue(),
        )

    def test_main_resume_from_starts_checkpoint_at_exact_expanded_course(
        self,
    ) -> None:
        output = FlushRecordingStream()
        expanded = [
            "/author/Before",
            "/author/Example Course",
            "/author/After",
        ]
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")

        with (
            redirect_stdout(output),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "expand_author_roots",
                return_value=expanded,
            ),
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ) as create,
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
        ):
            return_code = subject.main(
                [
                    "--author-roots",
                    "--skip-preflight",
                    "--resume-from",
                    "/author/Example Course",
                    "/author",
                ]
            )

        self.assertEqual(return_code, 0)
        create.assert_called_once_with(
            expanded,
            ["/author"],
            "author-roots",
            next_index=1,
            options=subject.TranscriptionOptions(),
        )
        fast.assert_called_once_with(
            expanded,
            None,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=1,
            roots_prevalidated=True,
            ignore_omega_directories=False,
            scan=False,
        )
        self.assertIn("start=2/3", output.getvalue())

    def test_main_resume_from_command_recovers_roots_without_eval(self) -> None:
        command = (
            "python3 ~/.agents/skills/batch-transcribe-courses/scripts/"
            "transcribe_courses.py --author-roots --skip-preflight -- "
            "'/author/Groove3' '/author/Later'"
        )
        expanded = [
            "/author/Groove3/Before",
            "/author/Groove3/Current",
            "/author/Groove3/After",
            "/author/Later/Course",
        ]
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")

        with (
            redirect_stdout(FlushRecordingStream()),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(subject.sys, "stdin", io.StringIO(command)),
            mock.patch.object(
                subject,
                "expand_author_roots",
                return_value=expanded,
            ) as expand,
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ) as create,
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
        ):
            return_code = subject.main(
                [
                    "--resume-from-command",
                    "/author/Groove3/Current",
                ]
            )

        self.assertEqual(return_code, 0)
        expand.assert_called_once_with(
            ["/author/Groove3", "/author/Later"],
            mock.ANY,
        )
        create.assert_called_once_with(
            expanded,
            ["/author/Groove3", "/author/Later"],
            "author-roots",
            next_index=1,
            options=subject.TranscriptionOptions(),
        )
        fast.assert_called_once_with(
            expanded,
            None,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=1,
            roots_prevalidated=True,
            ignore_omega_directories=False,
            scan=False,
        )

    def test_main_resume_from_topic_command_preserves_omega_exclusion(
        self,
    ) -> None:
        command = (
            "python3 ~/.agents/skills/batch-transcribe-courses/scripts/"
            "transcribe_courses.py --topic-roots --skip-preflight -- "
            "'/topics/Example Topic'"
        )
        expanded = [
            "/topics/Example Topic/Author/Before",
            "/topics/Example Topic/Author/Current",
            "/topics/Example Topic/Author/After",
        ]
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")

        with (
            redirect_stdout(FlushRecordingStream()),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(subject.sys, "stdin", io.StringIO(command)),
            mock.patch.object(
                subject,
                "expand_topic_roots",
                return_value=expanded,
            ) as expand,
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ) as create,
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
        ):
            return_code = subject.main(
                [
                    "--resume-from-command",
                    "/topics/Example Topic/Author/Current",
                ]
            )

        self.assertEqual(return_code, 0)
        expand.assert_called_once_with(
            ["/topics/Example Topic"],
            mock.ANY,
        )
        create.assert_called_once_with(
            expanded,
            ["/topics/Example Topic"],
            "topic-roots",
            next_index=1,
            options=subject.TranscriptionOptions(),
        )
        fast.assert_called_once_with(
            expanded,
            None,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=1,
            roots_prevalidated=True,
            ignore_omega_directories=True,
            scan=False,
        )

    def test_main_author_roots_routes_expanded_courses_to_fast_start(self) -> None:
        output = FlushRecordingStream()
        expanded = ["/author/Course One", "/author/Course Two"]
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")
        with (
            redirect_stdout(output),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "expand_author_roots",
                return_value=expanded,
            ) as expand,
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ),
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
            mock.patch.object(subject, "perform_preflight") as global_preflight,
        ):
            return_code = subject.main(
                [
                    "--author-roots",
                    "--skip-preflight",
                    "--limit",
                    "10",
                    "/author",
                ]
        )

        self.assertEqual(return_code, 0)
        expand.assert_called_once_with(["/author"], mock.ANY)
        fast.assert_called_once_with(
            expanded,
            10,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=0,
            roots_prevalidated=True,
            ignore_omega_directories=False,
            scan=False,
        )
        global_preflight.assert_not_called()
        self.assertIn(
            "AUTHOR ROOTS expanded authors=1 courses=2",
            output.getvalue(),
        )
        self.assertIn(
            "FAST START roots=2 start=1 limit=10",
            output.getvalue(),
        )

    def test_main_topic_roots_routes_expanded_courses_to_fast_start(self) -> None:
        output = FlushRecordingStream()
        expanded = [
            "/topic/Author One/Course One",
            "/topic/Author Two/Course Two",
        ]
        checkpoint = mock.Mock(spec=subject.ResumeCheckpoint)
        checkpoint.path = Path("/state/resume.json")
        with (
            redirect_stdout(output),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "expand_topic_roots",
                return_value=expanded,
            ) as expand,
            mock.patch.object(
                subject.ResumeCheckpoint,
                "create",
                return_value=checkpoint,
            ) as create,
            mock.patch.object(subject, "run_fast_start", return_value=0) as fast,
            mock.patch.object(subject, "perform_preflight") as global_preflight,
        ):
            return_code = subject.main(
                [
                    "--topic-roots",
                    "--skip-preflight",
                    "--limit",
                    "10",
                    "/topic",
                ]
            )

        self.assertEqual(return_code, 0)
        expand.assert_called_once_with(["/topic"], mock.ANY)
        create.assert_called_once_with(
            expanded,
            ["/topic"],
            "topic-roots",
            next_index=0,
            options=subject.TranscriptionOptions(),
        )
        fast.assert_called_once_with(
            expanded,
            10,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=checkpoint,
            start_index=0,
            roots_prevalidated=True,
            ignore_omega_directories=True,
            scan=False,
        )
        global_preflight.assert_not_called()
        self.assertIn(
            "TOPIC ROOTS expanded topics=1 courses=2",
            output.getvalue(),
        )

    def test_topic_resume_keeps_recursive_omega_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            roots = ["/topic/Author/Course"]
            checkpoint = subject.ResumeCheckpoint.create(
                roots,
                ["/topic"],
                "topic-roots",
                directory=Path(temporary),
            )

            with (
                redirect_stdout(FlushRecordingStream()),
                mock.patch.object(
                    subject.ProcessTitle,
                    "capture",
                    return_value=None,
                ),
                mock.patch.object(
                    subject,
                    "run_fast_start",
                    return_value=0,
                ) as fast,
                mock.patch.object(subject, "expand_topic_roots") as expand,
                mock.patch.object(subject, "validate_fast_start_roots") as validate,
            ):
                return_code = subject.main(
                    ["--resume", str(checkpoint.path)]
                )

        self.assertEqual(return_code, 0)
        fast.assert_called_once_with(
            roots,
            None,
            None,
            options=subject.TranscriptionOptions(),
            review_log=mock.ANY,
            checkpoint=mock.ANY,
            start_index=0,
            roots_prevalidated=True,
            ignore_omega_directories=True,
            scan=False,
        )
        expand.assert_not_called()
        validate.assert_not_called()

    def test_topic_roots_full_preflight_keeps_omega_exclusion(self) -> None:
        expanded = ["/topic/Author/Course"]
        preflight = subject.Preflight(
            courses=[
                subject.Course(
                    Path(expanded[0]),
                    ignore_omega_directories=True,
                )
            ],
            items=[],
            programs=subject.Programs("ffmpeg", "/worker"),
            work_total=0,
        )
        with (
            redirect_stdout(FlushRecordingStream()),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "expand_topic_roots",
                return_value=expanded,
            ),
            mock.patch.object(
                subject,
                "perform_preflight",
                return_value=preflight,
            ) as perform,
        ):
            return_code = subject.main(
                ["--topic-roots", "--dry-run", "/topic"]
            )

        self.assertEqual(return_code, 0)
        perform.assert_called_once_with(
            expanded,
            None,
            subject.TranscriptionOptions(),
            ignore_omega_directories=True,
        )

    def test_main_no_valid_author_roots_does_not_scan_courses(self) -> None:
        errors = FlushRecordingStream()
        with (
            redirect_stdout(FlushRecordingStream()),
            redirect_stderr(errors),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "expand_author_roots",
                return_value=[],
            ),
            mock.patch.object(subject, "perform_preflight") as preflight,
        ):
            return_code = subject.main(["--author-roots", "/author"])

        self.assertEqual(return_code, 2)
        self.assertIn("no course roots were found", errors.getvalue())
        preflight.assert_not_called()

    def test_main_no_valid_topic_roots_does_not_scan_courses(self) -> None:
        errors = FlushRecordingStream()
        with (
            redirect_stdout(FlushRecordingStream()),
            redirect_stderr(errors),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            mock.patch.object(
                subject,
                "expand_topic_roots",
                return_value=[],
            ),
            mock.patch.object(subject, "perform_preflight") as preflight,
        ):
            return_code = subject.main(["--topic-roots", "/topic"])

        self.assertEqual(return_code, 2)
        self.assertIn("no course roots were found", errors.getvalue())
        preflight.assert_not_called()

    def test_topic_and_author_root_modes_are_mutually_exclusive(self) -> None:
        errors = FlushRecordingStream()
        with (
            redirect_stderr(errors),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            self.assertRaises(SystemExit) as raised,
        ):
            subject.main(
                ["--topic-roots", "--author-roots", "/library"]
            )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("not allowed with argument", errors.getvalue())

    def test_skip_preflight_cannot_be_combined_with_dry_run(self) -> None:
        errors = FlushRecordingStream()
        with (
            redirect_stderr(errors),
            mock.patch.object(subject.ProcessTitle, "capture", return_value=None),
            self.assertRaises(SystemExit) as raised,
        ):
            subject.main(["--skip-preflight", "--dry-run", "/course"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("cannot be combined", errors.getvalue())

    def test_race_skip_is_successful_and_counted_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course = subject.Course(Path(temporary))
            items = [
                self.make_item(course, "race.mp3", "race.txt", selected=True),
                self.make_item(course, "ok.mp3", "ok.txt", selected=True),
            ]
            preflight = self.make_preflight(course, items)
            output = FlushRecordingStream()
            errors = FlushRecordingStream()

            with (
                redirect_stdout(output),
                redirect_stderr(errors),
                mock.patch.object(subject, "revalidate_media", return_value=None),
                mock.patch.object(
                    subject,
                    "open_safe_output_parent",
                    side_effect=lambda _item: os.open(
                        temporary,
                        os.O_RDONLY | os.O_DIRECTORY,
                    ),
                ),
                mock.patch.object(subject, "destination_exists", return_value=False),
                mock.patch.object(
                    subject,
                    "transcribe_item",
                    side_effect=[
                        subject.InstallResult.skipped("injected race"),
                        subject.InstallResult.installed(),
                    ],
                ),
            ):
                return_code = subject.run_live(
                    preflight,
                    title=None,
                )

        self.assertEqual(return_code, 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertIn(
            "SKIP destination now exists transcripts/race.txt",
            output.getvalue(),
        )
        self.assertIn(
            "attempted=2 succeeded=1 skipped=1 limited=0 failed=0",
            output.getvalue(),
        )
        self.assertGreater(output.flush_count, 0)

    def test_many_failures_are_logged_and_a_later_file_still_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course = subject.Course(Path(temporary))
            items = [
                self.make_item(
                    course,
                    f"failed-{index:02d}.mp3",
                    f"failed-{index:02d}.txt",
                    selected=True,
                )
                for index in range(12)
            ]
            items.append(
                self.make_item(
                    course,
                    "later-success.mp3",
                    "later-success.txt",
                    selected=True,
                )
            )
            preflight = self.make_preflight(course, items)
            output = FlushRecordingStream()
            errors = FlushRecordingStream()
            review = subject.ReviewLog(Path(temporary) / "review.txt")

            with (
                redirect_stdout(output),
                redirect_stderr(errors),
                mock.patch.object(subject, "revalidate_media", return_value=None),
                mock.patch.object(
                    subject,
                    "open_safe_output_parent",
                    side_effect=lambda _item: os.open(
                        temporary,
                        os.O_RDONLY | os.O_DIRECTORY,
                    ),
                ),
                mock.patch.object(subject, "destination_exists", return_value=False),
                mock.patch.object(
                    subject,
                    "transcribe_item",
                    side_effect=[
                        *[
                            subject.InstallResult.failed(
                                f"injected failure {index}"
                            )
                            for index in range(12)
                        ],
                        subject.InstallResult.installed(),
                    ],
                ),
            ):
                return_code = subject.run_live(
                    preflight,
                    title=None,
                    review_log=review,
                )
            review_payload = review.path.read_text(encoding="utf-8")

        self.assertEqual(return_code, 1)
        self.assertEqual(errors.getvalue().count(" FAIL failed-"), 12)
        self.assertIn("OK transcripts/later-success.txt", output.getvalue())
        self.assertEqual(review.issue_count, 12)
        self.assertEqual(review_payload.count("TRANSCRIPTION FAILURE"), 12)
        self.assertIn(
            "attempted=13 succeeded=1 skipped=0 limited=0 failed=12",
            output.getvalue(),
        )
        self.assertGreater(errors.flush_count, 0)


class CheckpointMigrationTests(unittest.TestCase):
    def test_new_checkpoints_are_v4_without_an_engine_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=Path(temporary),
            )
            payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
            loaded = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertEqual(payload["version"], 4)
        self.assertNotIn("engine", payload["transcription_options"])
        self.assertFalse(loaded.needs_migration)
        self.assertFalse(hasattr(loaded.options, "engine"))

    def test_v3_parakeet_and_whisperkit_migrate_to_v4_on_demand(self) -> None:
        for engine in ("parakeet", "whisperkit"):
            with (
                self.subTest(engine=engine),
                tempfile.TemporaryDirectory() as temporary,
            ):
                checkpoint = subject.ResumeCheckpoint.create(
                    ["/courses/One", "/courses/Two"],
                    ["/courses/One"],
                    "course-roots",
                    directory=Path(temporary),
                )
                payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
                payload["version"] = 3
                payload["transcription_options"]["engine"] = engine
                payload["next_index"] = 1
                payload["current_course"] = "/courses/Two"
                checkpoint.path.write_text(json.dumps(payload), encoding="utf-8")
                before = checkpoint.path.read_bytes()

                loaded = subject.ResumeCheckpoint.load(checkpoint.path)
                self.assertTrue(loaded.needs_migration)
                self.assertEqual(loaded.loaded_version, 3)
                # Loading alone must never touch the file.
                self.assertEqual(checkpoint.path.read_bytes(), before)

                with redirect_stdout(FlushRecordingStream()):
                    loaded.migrate()
                rewritten = json.loads(
                    checkpoint.path.read_text(encoding="utf-8")
                )
                self.assertEqual(rewritten["version"], 4)
                self.assertNotIn("engine", rewritten["transcription_options"])
                self.assertEqual(rewritten["next_index"], 1)
                self.assertFalse(loaded.needs_migration)

    def test_v1_and_v2_load_as_whisper_and_migrate_to_v4(self) -> None:
        for version in (1, 2):
            with (
                self.subTest(version=version),
                tempfile.TemporaryDirectory() as temporary,
            ):
                checkpoint = subject.ResumeCheckpoint.create(
                    ["/courses/One"],
                    ["/courses/One"],
                    "course-roots",
                    directory=Path(temporary),
                )
                payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
                payload["version"] = version
                checkpoint.path.write_text(json.dumps(payload), encoding="utf-8")

                loaded = subject.ResumeCheckpoint.load(checkpoint.path)
                self.assertTrue(loaded.needs_migration)
                with redirect_stdout(FlushRecordingStream()):
                    loaded.migrate()
                rewritten = json.loads(
                    checkpoint.path.read_text(encoding="utf-8")
                )
                self.assertEqual(rewritten["version"], 4)

    def test_unknown_v3_engine_value_remains_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=Path(temporary),
            )
            payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
            payload["version"] = 3
            payload["transcription_options"]["engine"] = "mystery"
            checkpoint.path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(subject.ResumeStateError):
                subject.ResumeCheckpoint.load(checkpoint.path)

    def test_unsupported_future_version_remains_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=Path(temporary),
            )
            payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
            payload["version"] = 5
            checkpoint.path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(subject.ResumeStateError):
                subject.ResumeCheckpoint.load(checkpoint.path)

class TimedRenderingTests(unittest.TestCase):
    def test_exact_bucket_boundary_silence_and_spanning_phrase(self) -> None:
        transcript, error = subject.render_timed_transcript(
            [
                subject.TimedPhrase(0.0, 1.0, "zero"),
                subject.TimedPhrase(119.9, 120.2, "spans"),
                subject.TimedPhrase(120.0, 121.0, "boundary"),
                subject.TimedPhrase(360.0, 361.0, "after silence"),
            ],
            120,
        )

        self.assertIsNone(error)
        self.assertEqual(
            transcript,
            "[00:00:00]\nzero spans\n\n"
            "[00:02:00]\nboundary\n\n"
            "[00:06:00]\nafter silence",
        )
        self.assertNotIn("[00:04:00]", transcript or "")

    def test_multi_hour_and_hundred_hour_markers(self) -> None:
        transcript, error = subject.render_timed_transcript(
            [
                subject.TimedPhrase(12_000.0, 12_001.0, "three hours"),
                subject.TimedPhrase(360_000.0, 360_001.0, "hundred hours"),
            ],
            120,
        )

        self.assertIsNone(error)
        self.assertIn("[03:20:00]", transcript or "")
        self.assertIn("[100:00:00]", transcript or "")


class WhisperKitWorkerProtocolTests(unittest.TestCase):
    FAKE_SOURCE = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import os
        import sys
        import time

        mode = os.environ.get("FAKE_WORKER_MODE", "success")
        start_log = os.environ["FAKE_WORKER_START_LOG"]
        shutdown_log = os.environ["FAKE_WORKER_SHUTDOWN_LOG"]
        model = os.environ["FAKE_WORKER_MODEL"]
        revision = os.environ["FAKE_WORKER_REVISION"]
        with open(start_log, "a", encoding="utf-8") as output:
            output.write(str(os.getpid()) + "\\n")
        with open(start_log, encoding="utf-8") as source:
            start_number = len(source.readlines())

        def emit(frame):
            sys.stdout.write(json.dumps(frame, separators=(",", ":")) + "\\n")
            sys.stdout.flush()

        if mode == "stderr_flood":
            sys.stderr.write("x" * 1000000 + "\\n")
            sys.stderr.flush()
        if mode == "bad_revision":
            revision = "0000000000000000000000000000000000000000"
        emit({
            "type": "ready",
            "engine": "whisperkit",
            "model": model,
            "model_path": "/fake/model",
            "audio_encoder_compute_units": "cpuAndNeuralEngine",
            "text_decoder_compute_units": "cpuAndGPU",
            "concurrent_worker_count": 16,
            "chunking_strategy": "vad",
            "argmax_revision": revision,
            "worker_version": "fake",
            "model_load_seconds": 0.25,
        })
        request_number = 0
        for line in sys.stdin:
            request = json.loads(line)
            if request["type"] == "shutdown":
                with open(shutdown_log, "a", encoding="utf-8") as output:
                    output.write(str(os.getpid()) + "\\n")
                break
            request_number += 1
            request_id = request["id"]
            if mode == "echo_request":
                emit({
                    "id": request_id,
                    "type": "result",
                    "text": json.dumps(
                        {
                            "language": request.get("language"),
                            "timestamps": request.get("timestamps"),
                            "audio_path": request.get("audio_path"),
                        },
                        sort_keys=True,
                    ),
                    "segments": [],
                    "duration": 1.0,
                    "processing_time": 0.01,
                })
                continue
            if mode in {"crash_once", "stale_once", "invalid_json_once", "timeout_once"} and start_number == 1:
                if mode == "crash_once":
                    sys.exit(9)
                if mode == "stale_once":
                    emit({"id": "stale", "type": "result", "text": "bad", "duration": 1, "processing_time": 0.1, "segments": []})
                    continue
                if mode == "invalid_json_once":
                    sys.stdout.write("not-json\\n")
                    sys.stdout.flush()
                    continue
                time.sleep(2)
            if mode == "duplicate":
                frame = {"id": request_id, "type": "result", "text": "Hello world.", "duration": 1, "processing_time": 0.1, "segments": [{"start": 0.0, "end": 0.8, "text": "Hello world."}]}
                emit(frame)
                emit(frame)
                continue
            if mode == "always_empty":
                emit({"id": request_id, "type": "result", "text": "", "segments": [], "duration": 1.0, "processing_time": 0.01})
                continue
            if mode == "empty_once" and start_number == 1:
                emit({"id": request_id, "type": "result", "text": "", "segments": [], "duration": 1.0, "processing_time": 0.01})
                continue
            if mode == "invalid_audio":
                emit({"id": request_id, "type": "error", "code": "invalid_audio", "message": "too short", "retriable": False})
                continue
            if mode == "model_load":
                emit({"id": request_id, "type": "error", "code": "model_load_failed", "message": "model vanished", "retriable": True})
                continue
            if mode == "processing_retry" and start_number == 1:
                emit({"id": request_id, "type": "error", "code": "processing_failed", "message": "retry me", "retriable": True})
                continue
            emit({
                "id": request_id,
                "type": "result",
                "text": "Hello world.",
                "segments": [
                    {"start": 0.0, "end": 0.8, "text": "Hello world."},
                ],
                "duration": 1.0,
                "processing_time": 0.01,
            })
        """
    )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.worker = self.directory / "fake-worker"
        self.worker.write_text(self.FAKE_SOURCE, encoding="utf-8")
        self.worker.chmod(0o700)
        self.start_log = self.directory / "starts.txt"
        self.shutdown_log = self.directory / "shutdowns.txt"
        self.environment = mock.patch.dict(
            os.environ,
            {
                "FAKE_WORKER_START_LOG": str(self.start_log),
                "FAKE_WORKER_SHUTDOWN_LOG": str(self.shutdown_log),
                "FAKE_WORKER_MODEL": subject.MODEL,
                "FAKE_WORKER_REVISION": subject.ARGMAX_REQUIRED_REVISION,
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        subject.shutdown_worker()
        self.environment.stop()
        self.temporary.cleanup()

    def run_worker(
        self,
        mode: str,
        *,
        retries: int = 1,
        timeout: int = 5,
        timestamps: bool = True,
        language: str | None = "en",
    ) -> tuple[str | None, str | None]:
        os.environ["FAKE_WORKER_MODE"] = mode
        return subject.run_whisperkit_worker(
            str(self.worker),
            self.directory / "audio.wav",
            subject.TranscriptionOptions(
                timestamps=timestamps,
                retries=retries,
                timeout_seconds=timeout,
                language=language,
            ),
            self.directory,
        )

    def start_count(self) -> int:
        if not self.start_log.exists():
            return 0
        return len(self.start_log.read_text(encoding="utf-8").splitlines())

    def test_worker_is_reused_across_files_and_shuts_down_cleanly(self) -> None:
        first, first_error = self.run_worker("success")
        second, second_error = self.run_worker("success")
        subject.shutdown_worker()

        self.assertIsNone(first_error)
        self.assertIsNone(second_error)
        self.assertEqual(first, "[00:00:00]\nHello world.")
        self.assertEqual(second, first)
        self.assertEqual(self.start_count(), 1)
        self.assertEqual(
            len(self.shutdown_log.read_text(encoding="utf-8").splitlines()),
            1,
        )

    def test_request_carries_language_timestamps_and_audio_path(self) -> None:
        transcript, error = self.run_worker(
            "echo_request",
            retries=0,
            timestamps=False,
            language="fr",
        )

        self.assertIsNone(error)
        self.assertEqual(
            json.loads(transcript or "{}"),
            {
                "audio_path": str(self.directory / "audio.wav"),
                "language": "fr",
                "timestamps": False,
            },
        )

    def test_ready_frame_with_wrong_revision_is_rejected(self) -> None:
        transcript, error = self.run_worker("bad_revision", retries=0)

        self.assertIsNone(transcript)
        self.assertIn("invalid WhisperKit ready frame", error or "")

    def test_crash_stale_and_invalid_json_restart_then_succeed(self) -> None:
        for mode in ("crash_once", "stale_once", "invalid_json_once"):
            with self.subTest(mode=mode):
                subject.shutdown_worker()
                self.start_log.write_text("", encoding="utf-8")
                transcript, error = self.run_worker(mode, retries=1)
                self.assertIsNone(error)
                self.assertIn("Hello world.", transcript or "")
                self.assertEqual(self.start_count(), 2)

    def test_request_ignores_legacy_timeout_and_finishes(self) -> None:
        transcript, error = self.run_worker("timeout_once", retries=0, timeout=1)
        self.assertIsNone(error)
        self.assertIn("Hello world.", transcript or "")
        self.assertEqual(self.start_count(), 1)

    def test_stderr_flood_does_not_deadlock_or_corrupt_protocol(self) -> None:
        transcript, error = self.run_worker("stderr_flood", retries=0)
        self.assertIsNone(error)
        self.assertIn("Hello world.", transcript or "")

    def test_permanent_invalid_audio_is_not_retried(self) -> None:
        transcript, error = self.run_worker("invalid_audio", retries=3)
        self.assertIsNone(transcript)
        self.assertEqual(error, "too short")
        self.assertEqual(self.start_count(), 1)

    def test_retriable_engine_error_restarts_the_worker_then_succeeds(self) -> None:
        transcript, error = self.run_worker("processing_retry", retries=1)
        self.assertIsNone(error)
        self.assertIn("Hello world.", transcript or "")
        # Retrying into the same resident model reproduces Core ML resource
        # exhaustion, so a retriable error restarts the worker first.
        self.assertEqual(self.start_count(), 2)

    def test_mid_run_model_load_failure_retries_only_once(self) -> None:
        transcript, error = self.run_worker("model_load", retries=4)
        self.assertIsNone(transcript)
        self.assertEqual(error, "model vanished")
        self.assertEqual(self.start_count(), 2)

    def test_empty_result_restarts_the_worker_and_retries(self) -> None:
        transcript, error = self.run_worker("empty_once", retries=1)

        self.assertIsNone(error)
        self.assertIn("Hello world.", transcript or "")
        self.assertEqual(self.start_count(), 2)

    def test_more_than_ten_empty_files_do_not_block_a_later_success(self) -> None:
        errors: list[str] = []
        for _ in range(12):
            transcript, error = self.run_worker("always_empty", retries=0)
            self.assertIsNone(transcript)
            self.assertIn("empty timestamped transcript", error or "")
            errors.append(error or "")

        transcript, error = self.run_worker("success", retries=0)

        self.assertEqual(len(errors), 12)
        self.assertIsNone(error)
        self.assertIn("Hello world.", transcript or "")
        self.assertEqual(self.start_count(), 13)

    def test_exhausted_empty_results_restart_for_the_full_retry_budget(self) -> None:
        transcript, error = self.run_worker("always_empty", retries=3)

        self.assertIsNone(transcript)
        self.assertIn("attempts=4", error or "")
        self.assertEqual(self.start_count(), 4)

    def test_worker_is_recycled_before_the_request_limit_is_exceeded(self) -> None:
        original = subject.WORKER_RECYCLE_REQUEST_LIMIT
        subject.WORKER_RECYCLE_REQUEST_LIMIT = 3
        try:
            for _ in range(7):
                _transcript, error = self.run_worker("success", retries=0)
                self.assertIsNone(error)
        finally:
            subject.WORKER_RECYCLE_REQUEST_LIMIT = original

        # 7 requests at a 3-request limit means the worker is replaced twice.
        self.assertEqual(self.start_count(), 3)


    def test_duplicate_result_is_rejected(self) -> None:
        transcript, error = self.run_worker("duplicate", retries=1)
        self.assertIsNone(transcript)
        self.assertIn("duplicate response", error or "")
        self.assertEqual(self.start_count(), 2)


class WorkerWiringTests(unittest.TestCase):
    def test_engine_flag_is_gone_from_the_parser(self) -> None:
        parser = subject.build_parser()
        default = subject.options_from_args(parser.parse_args(["/course"]))

        self.assertFalse(hasattr(default, "engine"))
        with (
            redirect_stderr(FlushRecordingStream()),
            self.assertRaises(SystemExit) as raised,
        ):
            parser.parse_args(["--engine", "parakeet", "/course"])
        self.assertEqual(raised.exception.code, 2)

    def test_transcribe_item_routes_through_the_persistent_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "lesson.wav"
            media.write_bytes(b"audio")
            item = subject.WorkItem(
                course=subject.Course(root),
                media=media,
                relative_media=Path("lesson.wav"),
                relative_output=Path("lesson.txt"),
                identity=subject.MediaIdentity(1, 2, 3, 4),
                input_kind="direct",
            )
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with (
                    mock.patch.object(
                        subject,
                        "run_whisperkit_worker",
                        return_value=("WhisperKit text", None),
                    ) as worker,
                    mock.patch.object(
                        subject,
                        "install_transcript",
                        return_value=subject.InstallResult.installed(),
                    ),
                ):
                    result = subject.transcribe_item(
                        item,
                        subject.Programs("ffmpeg", "/worker"),
                        parent_fd,
                        subject.TranscriptionOptions(),
                    )
            finally:
                os.close(parent_fd)

        self.assertIs(result.status, subject.InstallStatus.INSTALLED)
        worker.assert_called_once()
        self.assertEqual(worker.call_args.args[0], "/worker")

    def test_unresolved_worker_fails_without_reaching_the_installer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "lesson.wav"
            media.write_bytes(b"audio")
            item = subject.WorkItem(
                course=subject.Course(root),
                media=media,
                relative_media=Path("lesson.wav"),
                relative_output=Path("lesson.txt"),
                identity=subject.MediaIdentity(1, 2, 3, 4),
                input_kind="direct",
            )
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with mock.patch.object(subject, "install_transcript") as install:
                    result = subject.transcribe_item(
                        item,
                        subject.Programs("ffmpeg", None),
                        parent_fd,
                        subject.TranscriptionOptions(),
                    )
            finally:
                os.close(parent_fd)

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertIn("was not resolved", result.detail or "")
        install.assert_not_called()

    def test_worker_failure_never_reaches_installer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "lesson.wav"
            media.write_bytes(b"audio")
            item = subject.WorkItem(
                course=subject.Course(root),
                media=media,
                relative_media=Path("lesson.wav"),
                relative_output=Path("lesson.txt"),
                identity=subject.MediaIdentity(1, 2, 3, 4),
                input_kind="direct",
            )
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with (
                    mock.patch.object(
                        subject,
                        "run_whisperkit_worker",
                        return_value=(None, "invalid response"),
                    ),
                    mock.patch.object(subject, "install_transcript") as install,
                ):
                    result = subject.transcribe_item(
                        item,
                        subject.Programs("ffmpeg", "/worker"),
                        parent_fd,
                        subject.TranscriptionOptions(),
                    )
            finally:
                os.close(parent_fd)

        self.assertIs(result.status, subject.InstallStatus.FAILED)
        self.assertIn("invalid response", result.detail or "")
        install.assert_not_called()

    def test_non_english_course_is_transcribed_rather_than_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            spanish = base / "Language" / "Spanish" / "Course"
            english = base / "English Course"
            spanish.mkdir(parents=True)
            english.mkdir()
            roots = [str(spanish), str(english)]
            checkpoint = subject.ResumeCheckpoint.create(
                roots,
                roots,
                "course-roots",
                directory=base / "state",
            )
            review = subject.ReviewLog(base / "review.txt")
            with (
                mock.patch.object(
                    subject,
                    "bootstrap_worker",
                    return_value=(
                        subject.Programs("ffmpeg", "/worker"),
                        None,
                        None,
                    ),
                ),
                mock.patch.object(
                    subject,
                    "stream_course",
                    return_value=(subject.CourseSummary(), 0, False, False),
                ) as stream,
                redirect_stdout(FlushRecordingStream()),
                redirect_stderr(FlushRecordingStream()),
            ):
                result = subject.run_fast_start(
                    roots,
                    None,
                    None,
                    review_log=review,
                    checkpoint=checkpoint,
                    roots_prevalidated=True,
                )

            loaded = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertEqual(result, 0)
        self.assertEqual(loaded.failed_courses, [])
        self.assertEqual(stream.call_count, 2)

    def test_resume_bootstrap_failure_preserves_checkpoint_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=base / "checkpoints",
            )
            # Age the file back to v3 so a successful run would have migrated it.
            payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
            payload["version"] = 3
            payload["transcription_options"]["engine"] = "parakeet"
            checkpoint.path.write_text(json.dumps(payload), encoding="utf-8")
            before = checkpoint.path.read_bytes()
            before_hash = hashlib.sha256(before).hexdigest()
            with (
                mock.patch.object(
                    subject,
                    "resume_state_directory",
                    return_value=base / "state",
                ),
                mock.patch.object(
                    subject,
                    "prepare_worker_for_live_run",
                    return_value="injected bootstrap failure",
                ),
                redirect_stdout(FlushRecordingStream()),
                redirect_stderr(FlushRecordingStream()),
            ):
                result = subject.main(["--resume", str(checkpoint.path)])
            after = checkpoint.path.read_bytes()
            loaded = subject.ResumeCheckpoint.load(checkpoint.path)

        self.assertEqual(result, 2)
        self.assertEqual(hashlib.sha256(after).hexdigest(), before_hash)
        self.assertEqual(after, before)
        self.assertEqual(loaded.loaded_version, 3)
        self.assertEqual(loaded.next_index, 0)
        self.assertEqual(loaded.failed_courses, [])

    def test_successful_resume_migrates_a_v3_parakeet_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=base / "checkpoints",
            )
            payload = json.loads(checkpoint.path.read_text(encoding="utf-8"))
            payload["version"] = 3
            payload["transcription_options"]["engine"] = "parakeet"
            checkpoint.path.write_text(json.dumps(payload), encoding="utf-8")

            with (
                mock.patch.object(
                    subject,
                    "resume_state_directory",
                    return_value=base / "state",
                ),
                mock.patch.object(
                    subject, "prepare_worker_for_live_run", return_value=None
                ),
                mock.patch.object(subject, "run_fast_start", return_value=0),
                redirect_stdout(FlushRecordingStream()),
                redirect_stderr(FlushRecordingStream()),
            ):
                result = subject.main(["--resume", str(checkpoint.path)])
            rewritten = json.loads(checkpoint.path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(rewritten["version"], 4)
        self.assertNotIn("engine", rewritten["transcription_options"])

    def test_new_run_bootstrap_failure_creates_no_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            course = base / "Course"
            course.mkdir()
            state = base / "state"
            with (
                mock.patch.object(subject, "resume_state_directory", return_value=state),
                mock.patch.object(
                    subject,
                    "prepare_worker_for_live_run",
                    return_value="injected bootstrap failure",
                ),
                mock.patch.object(
                    subject.ResumeCheckpoint,
                    "create",
                    wraps=subject.ResumeCheckpoint.create,
                ) as create,
                redirect_stdout(FlushRecordingStream()),
                redirect_stderr(FlushRecordingStream()),
            ):
                result = subject.main([str(course)])
            created = list(state.glob("resume-*.json")) if state.exists() else []

        self.assertEqual(result, 2)
        create.assert_not_called()
        self.assertEqual(created, [])

    def test_resume_rejects_option_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            checkpoint = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=base / "checkpoints",
            )
            with (
                mock.patch.object(subject, "resume_state_directory", return_value=base / "state"),
                mock.patch.object(subject, "prepare_worker_for_live_run", return_value=None),
                mock.patch.object(subject, "run_fast_start", return_value=0),
                redirect_stdout(FlushRecordingStream()),
                redirect_stderr(FlushRecordingStream()),
            ):
                result = subject.main(["--resume", str(checkpoint.path)])

            with (
                redirect_stderr(FlushRecordingStream()),
                self.assertRaises(SystemExit) as raised,
            ):
                subject.main(
                    ["--resume", str(checkpoint.path), "--language", "fr"]
                )

        self.assertEqual(result, 0)
        self.assertEqual(raised.exception.code, 2)

    def test_retry_failed_creates_a_new_checkpoint_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = subject.ResumeCheckpoint.create(
                ["/courses/One"],
                ["/courses/One"],
                "course-roots",
                directory=base / "source",
            )
            source.record_failed_course("/courses/One")
            source.set_cursor(1, source.final_status())
            source_before = source.path.read_bytes()
            state = base / "state"
            output = FlushRecordingStream()
            with (
                mock.patch.object(subject, "resume_state_directory", return_value=state),
                mock.patch.object(subject, "prepare_worker_for_live_run", return_value=None),
                mock.patch.object(subject, "run_fast_start", return_value=0),
                redirect_stdout(output),
                redirect_stderr(FlushRecordingStream()),
            ):
                result = subject.main(["--retry-failed", str(source.path)])
            new_states = list(state.glob("resume-*.json"))
            source_after = source.path.read_bytes()

        self.assertEqual(result, 0)
        self.assertEqual(source_after, source_before)
        self.assertEqual(len(new_states), 1)
        self.assertIn("transcribe-courses --resume", output.getvalue())
        self.assertNotIn("transcribe_courses.py", output.getvalue())

    def test_bootstrap_cache_hit_skips_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = Path(temporary) / "fingerprint" / "whisperkit-worker"
            worker.parent.mkdir()
            worker.write_bytes(b"worker")
            worker.chmod(0o700)
            frame = {
                "type": "check",
                "ready": True,
                "engine": "whisperkit",
                "model": subject.MODEL,
                "model_path": "/model",
                "audio_encoder_compute_units": "cpuAndNeuralEngine",
                "text_decoder_compute_units": "cpuAndGPU",
                "argmax_revision": subject.ARGMAX_REQUIRED_REVISION,
                "worker_version": "fingerprint",
            }
            with (
                mock.patch.object(subject, "resolve_program", return_value=("/bin/true", None)),
                mock.patch.object(
                    subject, "resolve_model_path", return_value=(subject.MODEL_PATH, None)
                ),
                mock.patch.object(
                    subject,
                    "worker_cache_path",
                    return_value=(worker, None),
                ),
                mock.patch.object(
                    subject,
                    "_worker_mode_frame",
                    return_value=(frame, None),
                ) as mode,
                mock.patch.object(subject, "build_whisperkit_worker") as build,
            ):
                programs, info, error = subject.bootstrap_worker()

        self.assertIsNone(error)
        self.assertIsNotNone(programs)
        self.assertEqual(info.model_path if info else None, Path("/model"))
        build.assert_not_called()
        mode.assert_called_once_with(
            worker,
            "--check",
            subject.WORKER_CHECK_TIMEOUT_SECONDS,
        )

    def test_bootstrap_rejects_a_worker_built_from_another_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = Path(temporary) / "fingerprint" / "whisperkit-worker"
            worker.parent.mkdir()
            worker.write_bytes(b"worker")
            worker.chmod(0o700)
            frame = {
                "type": "check",
                "ready": True,
                "model": subject.MODEL,
                "model_path": "/model",
                "argmax_revision": "0" * 40,
                "worker_version": "fingerprint",
            }
            with (
                mock.patch.object(subject, "resolve_program", return_value=("/bin/true", None)),
                mock.patch.object(
                    subject, "resolve_model_path", return_value=(subject.MODEL_PATH, None)
                ),
                mock.patch.object(
                    subject, "worker_cache_path", return_value=(worker, None)
                ),
                mock.patch.object(
                    subject, "_worker_mode_frame", return_value=(frame, None)
                ),
            ):
                programs, info, error = subject.bootstrap_worker()

        self.assertIsNone(programs)
        self.assertIsNone(info)
        self.assertIn("Argmax revision", error or "")

    def test_dry_run_never_builds_the_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = Path(temporary) / "missing-worker"
            with (
                mock.patch.object(subject, "resolve_program", return_value=("/bin/true", None)),
                mock.patch.object(
                    subject, "resolve_model_path", return_value=(subject.MODEL_PATH, None)
                ),
                mock.patch.object(
                    subject,
                    "worker_cache_path",
                    return_value=(worker, None),
                ),
                mock.patch.object(subject, "build_whisperkit_worker") as build,
                mock.patch.object(subject, "_worker_mode_frame") as mode,
            ):
                programs, info, error = subject.bootstrap_worker(allow_build=False)

        self.assertIsNone(programs)
        self.assertIsNone(info)
        self.assertIn("dry-run will not build", error or "")
        build.assert_not_called()
        mode.assert_not_called()

    def test_build_refuses_a_dirty_or_moved_argmax_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = Path(temporary) / "whisperkit-worker"
            with mock.patch.object(
                subject,
                "verify_argmax_checkout",
                return_value="Argmax checkout has 3 local modifications",
            ):
                error = subject.build_whisperkit_worker(worker)

        self.assertIn("local modifications", error or "")
        self.assertFalse(worker.exists())

    def test_fingerprint_tracks_the_pinned_revision(self) -> None:
        first, error = subject.worker_fingerprint()
        self.assertIsNone(error)
        with mock.patch.object(subject, "ARGMAX_REQUIRED_REVISION", "f" * 40):
            second, second_error = subject.worker_fingerprint()

        self.assertIsNone(second_error)
        self.assertNotEqual(first, second)

    def test_main_finally_shuts_down_worker_on_keyboard_interrupt(self) -> None:
        worker = mock.Mock()
        subject._ACTIVE_WORKER = worker
        with (
            mock.patch.object(subject, "_main", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            subject.main([])
        worker.shutdown.assert_called_once_with()
        self.assertIsNone(subject._ACTIVE_WORKER)


class SourceRepositoryPruningTests(unittest.TestCase):
    MANIFESTS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Package.swift")

    def build_course(self, root: Path, manifest: str) -> None:
        (root / "Lessons").mkdir(parents=True)
        (root / "Lessons" / "01 Intro.mp4").write_bytes(b"lesson")
        bundled = root / "starter-master"
        (bundled / "public").mkdir(parents=True)
        (bundled / manifest).write_text("{}", encoding="utf-8")
        (bundled / "public" / "correct.wav").write_bytes(b"sound")
        (bundled / "public" / "demo.mp4").write_bytes(b"sound")

    def test_recognized_manifests_prune_the_whole_subtree(self) -> None:
        for manifest in self.MANIFESTS:
            with (
                self.subTest(manifest=manifest),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary) / "Course"
                self.build_course(root, manifest)
                with redirect_stdout(FlushRecordingStream()):
                    items, errors = subject.discover_media(subject.Course(root))

                self.assertEqual(errors, [])
                self.assertEqual(
                    [item.relative_media.as_posix() for item in items],
                    ["Lessons/01 Intro.mp4"],
                )

    def test_pruning_is_informational_and_not_a_course_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            self.build_course(root, "package.json")
            output = FlushRecordingStream()
            with redirect_stdout(output):
                _items, errors = subject.discover_media(subject.Course(root))

        self.assertEqual(errors, [])
        self.assertIn("SOURCE TREE PRUNED", output.getvalue())
        self.assertIn("starter-master", output.getvalue())

    def test_course_root_manifest_never_prunes_the_course(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            root.mkdir(parents=True)
            (root / "package.json").write_text("{}", encoding="utf-8")
            (root / "01 Intro.mp4").write_bytes(b"lesson")
            with redirect_stdout(FlushRecordingStream()):
                items, errors = subject.discover_media(subject.Course(root))

        self.assertEqual(len(errors), 1)
        self.assertIn("package.json", errors[0])
        self.assertIn("allowlisted media types only", errors[0])
        self.assertEqual(
            [item.relative_media.as_posix() for item in items],
            ["01 Intro.mp4"],
        )

    def test_unrecognized_manifest_leaves_media_discoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            (root / "assets").mkdir(parents=True)
            (root / "assets" / "notes.txt").write_text("notes", encoding="utf-8")
            (root / "assets" / "clip.mp4").write_bytes(b"lesson")
            with redirect_stdout(FlushRecordingStream()):
                items, _errors = subject.discover_media(subject.Course(root))

        self.assertEqual(
            [item.relative_media.as_posix() for item in items],
            ["assets/clip.mp4"],
        )

    def test_transport_stream_check_still_applies_outside_source_repositories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            (root / "Lessons").mkdir(parents=True)
            real = root / "Lessons" / "01 lesson.ts"
            real.write_bytes(mpeg_transport_stream_bytes())
            typescript = root / "Lessons" / "helper.ts"
            typescript.write_text("export const x = 1;\n", encoding="utf-8")
            with redirect_stdout(FlushRecordingStream()):
                items, _errors = subject.discover_media(subject.Course(root))

        self.assertEqual(
            [item.relative_media.as_posix() for item in items],
            ["Lessons/01 lesson.ts"],
        )

    def test_transport_streams_inside_source_repositories_are_pruned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Course"
            (root / "app").mkdir(parents=True)
            (root / "app" / "package.json").write_text("{}", encoding="utf-8")
            (root / "app" / "sample.ts").write_bytes(mpeg_transport_stream_bytes())
            (root / "01 Intro.mp4").write_bytes(b"lesson")
            with redirect_stdout(FlushRecordingStream()):
                items, _errors = subject.discover_media(subject.Course(root))

        self.assertEqual(
            [item.relative_media.as_posix() for item in items],
            ["01 Intro.mp4"],
        )


@unittest.skipUnless(
    os.environ.get("WHISPERKIT_LIVE_TESTS") == "1",
    "set WHISPERKIT_LIVE_TESTS=1 for real WhisperKit model tests",
)
class WhisperKitLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        programs, info, error = subject.bootstrap_worker()
        if error or programs is None or info is None:
            raise AssertionError(f"WhisperKit live bootstrap failed: {error}")
        cls.programs = programs
        cls.info = info

    @classmethod
    def tearDownClass(cls) -> None:
        subject.shutdown_worker()

    @staticmethod
    def fixture(name: str) -> Path:
        raw = os.environ.get(name)
        if not raw:
            raise unittest.SkipTest(f"set {name} to a real local audio file")
        return Path(raw).expanduser().resolve(strict=True)

    @staticmethod
    def ffprobe_duration(path: Path) -> float:
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
        return float(completed.stdout.strip())

    def test_real_bootstrap_reports_the_pinned_build(self) -> None:
        self.assertEqual(self.info.argmax_revision, subject.ARGMAX_REQUIRED_REVISION)
        self.assertEqual(
            self.info.audio_encoder_compute_units,
            subject.AUDIO_ENCODER_COMPUTE_UNITS,
        )
        self.assertEqual(
            self.info.text_decoder_compute_units,
            subject.TEXT_DECODER_COMPUTE_UNITS,
        )
        self.assertTrue(self.info.worker_path.is_file())

    def test_real_model_loads_and_reports_load_time(self) -> None:
        worker = subject.active_worker(self.programs.worker or "")
        worker.start()
        ready = worker.ready or {}

        self.assertEqual(ready.get("model"), subject.MODEL)
        self.assertEqual(ready.get("chunking_strategy"), subject.CHUNKING_STRATEGY)
        self.assertEqual(
            ready.get("concurrent_worker_count"), subject.CONCURRENT_WORKERS
        )
        self.assertIsInstance(ready.get("model_load_seconds"), float)

    def test_real_repeated_requests_reuse_one_worker_process(self) -> None:
        audio = self.fixture("WHISPERKIT_LIVE_SHORT_AUDIO")
        worker = subject.active_worker(self.programs.worker or "")
        worker.start()
        assert worker.process is not None
        pid = worker.process.pid

        for _ in range(2):
            frame = worker.transcribe(audio, 600, language="en", timestamps=False)
            self.assertEqual(frame.get("type"), "result")

        assert worker.process is not None
        self.assertEqual(worker.process.pid, pid)

    def test_real_short_clip_transcribes_with_markers(self) -> None:
        audio = self.fixture("WHISPERKIT_LIVE_SHORT_AUDIO")
        self.assertGreaterEqual(self.ffprobe_duration(audio), 30.0)
        with tempfile.TemporaryDirectory() as temporary:
            transcript, error = subject.run_whisperkit_worker(
                self.programs.worker or "",
                audio,
                subject.TranscriptionOptions(
                    timestamps=True,
                    retries=0,
                    timeout_seconds=600,
                ),
                Path(temporary),
            )
        self.assertIsNone(error)
        self.assertRegex(transcript or "", subject.LEADING_TIMESTAMP_PATTERN)

    def test_real_multilingual_option_is_accepted(self) -> None:
        audio = self.fixture("WHISPERKIT_LIVE_SHORT_AUDIO")
        worker = subject.active_worker(self.programs.worker or "")
        for language in (None, "en", "es"):
            with self.subTest(language=language):
                frame = worker.transcribe(
                    audio, 600, language=language, timestamps=False
                )
                self.assertEqual(frame.get("type"), "result")
                self.assertIsInstance(frame.get("text"), str)

    def test_real_long_lesson_reports_consistent_duration_and_segments(self) -> None:
        audio = self.fixture("WHISPERKIT_LIVE_LONG_AUDIO")
        expected_duration = self.ffprobe_duration(audio)
        self.assertGreaterEqual(expected_duration, 10 * 60)
        worker = subject.active_worker(self.programs.worker or "")
        frame = worker.transcribe(audio, 3600, language="en", timestamps=True)
        _text, duration, _processing, segments = subject.validate_worker_result(frame)
        phrases = subject.phrases_from_segments(segments)

        self.assertAlmostEqual(duration, expected_duration, delta=1.0)
        self.assertGreater(len(phrases), 0)
        self.assertTrue(
            all(
                left.start <= right.start
                for left, right in zip(phrases, phrases[1:])
            )
        )
        self.assertLessEqual(phrases[-1].end, duration + 1.0)


if __name__ == "__main__":
    unittest.main()
