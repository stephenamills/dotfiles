#!/usr/bin/env python3
"""Deterministic tests for the batch transcript installer and CLI output."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import errno
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import transcribe_courses as subject


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
    ) -> subject.InstallResult:
        return subject.install_transcript(
            self.parent_fd,
            destination_name,
            transcript,
            destination_path=self.directory / destination_name,
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
            ("", b""),
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


class OutputContractTests(unittest.TestCase):
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
    ) -> subject.Preflight:
        return subject.Preflight(
            courses=[course],
            items=items,
            programs=subject.Programs("whisperkit-cli", "ffmpeg"),
            work_total=sum(item.selected for item in items),
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
                return_code = subject.run_live(preflight, title=None)

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

    def test_failure_status_sets_exit_one_and_failure_counter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            course = subject.Course(Path(temporary))
            item = self.make_item(
                course,
                "failed.mp3",
                "failed.txt",
                selected=True,
            )
            preflight = self.make_preflight(course, [item])
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
                    return_value=subject.InstallResult.failed("injected failure"),
                ),
            ):
                return_code = subject.run_live(preflight, title=None)

        self.assertEqual(return_code, 1)
        self.assertIn("FAIL failed.mp3: injected failure", errors.getvalue())
        self.assertIn(
            "attempted=1 succeeded=0 skipped=0 limited=0 failed=1",
            output.getvalue(),
        )
        self.assertGreater(errors.flush_count, 0)


if __name__ == "__main__":
    unittest.main()
