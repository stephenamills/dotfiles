#!/usr/bin/env python3
"""Acceptance tests for the deterministic study-guide batch supervisor."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("study_guide_batch", SCRIPT_DIR / "study_guide_batch.py")
assert SPEC and SPEC.loader
batch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = batch
SPEC.loader.exec_module(batch)
FAKE_CODEX = SCRIPT_DIR / "fake_codex.py"


def transcript_text(label: str, words: int) -> str:
    return " ".join(f"{label} concept explanation example {index}" for index in range(max(1, words // 5)))


class BatchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="study-guide-batch-test-")
        self.root = Path(self.temporary.name)
        (self.root / "transcripts").mkdir()
        self.environ = mock.patch.dict(
            os.environ,
            {
                "CODEX_BIN": str(FAKE_CODEX),
                "FAKE_CODEX_STATE": str(self.root / "fake-state.json"),
                "FAKE_CODEX_SCENARIO": "success",
                "FAKE_CODEX_VERSION": "codex-cli fake-1.0",
                "STUDY_GUIDE_BATCH_TESTING": "1",
                "STUDY_GUIDE_BATCH_BACKOFF_SCALE": "0",
                "CODEX_THREAD_ID": "must-not-leak",
                "CODEX_CI": "must-not-leak",
                "CODEX_SANDBOX": "must-not-leak",
                "CODEX_SANDBOX_NETWORK_DISABLED": "must-not-leak",
                "CODEX_APPROVAL_POLICY": "must-not-leak",
                "CODEX_PERMISSION_PROFILE": "must-not-leak",
                "CI": "must-not-leak",
            },
            clear=False,
        )
        self.environ.start()
        self.write_config()

    def tearDown(self) -> None:
        self.environ.stop()
        self.temporary.cleanup()

    def write_config(self, **overrides: object) -> None:
        config: dict[str, object] = {
            "input_roots": ["transcripts"],
            "models": {"generator": "fake-model"},
            "validators": {"required_headings": [], "require_completion_marker": True},
            "output_root": "outputs",
            "existing_roots": ["outputs"],
            "ecc_mirror": False,
        }
        config.update(overrides)
        (self.root / batch.CONFIG_NAME).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    def add_lesson(self, number: int, title: str, words: int = 400, parts: int = 1) -> list[Path]:
        paths: list[Path] = []
        for part in range(1, parts + 1):
            suffix = f" - Part {part}" if parts > 1 else ""
            path = self.root / "transcripts" / f"{number:02d}. {title}{suffix}.txt"
            path.write_text(transcript_text(title, words), encoding="utf-8")
            paths.append(path)
        return paths

    def add_pdf(self, number: int, title: str) -> Path:
        directory = self.root / "excel and pdf files" / "Course Assets"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"Video {number} {title}.pdf"
        path.write_bytes(b"%PDF-1.4\n% test fixture; extraction is mocked where required\n")
        return path

    def add_workbook(self, number: int, title: str) -> Path:
        import openpyxl

        directory = self.root / "excel and pdf files" / "Course Assets"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"Video {number} {title}.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Model"
        sheet["A1"] = "Input"
        sheet["B1"] = "Calculated output"
        sheet["A2"] = 10
        sheet["B2"] = "=A2*2"
        sheet.freeze_panes = "A2"
        workbook.save(path)
        workbook.close()
        return path

    def seed_calibration(self, plan: dict[str, object]) -> None:
        store = batch.Store(self.root)
        report = {
            "schema_version": 1,
            "plan_id": plan["id"],
            "mapping_hash": plan["mapping_hash"],
            "status": "completed",
            "p90_invocation_seconds": 0.05,
            "p90_invocation_tokens": 30,
            "models": plan["config"]["models"],
            "model_reasoning_effort": plan["config"]["model_reasoning_effort"],
            "model_verbosity": plan["config"]["model_verbosity"],
            "codex_version": batch.codex_version(),
        }
        path = batch.calibration_path(store, str(plan["id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        batch.atomic_write_json(path, report)

    def approval_args(self, **overrides: object) -> argparse.Namespace:
        values: dict[str, object] = {
            "deadline_hours": 0.2,
            "timeout_minutes": 0.02,
            "max_invocations": 30,
            "max_tokens": 10000,
            "transient_retries": 2,
            "generator_model": None,
            "reasoning_effort": None,
            "verbosity": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def approved(self, **approval_overrides: object) -> tuple[batch.Store, dict[str, object], dict[str, object]]:
        plan = batch.create_plan(self.root)
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.seed_calibration(plan)
        store = batch.Store(self.root)
        approval = batch.approve_plan(store, plan, self.approval_args(**approval_overrides))
        return store, plan, approval

    def execute(self, **approval_overrides: object) -> tuple[batch.Store, dict[str, object], str]:
        store, plan, approval = self.approved(**approval_overrides)
        run_id = batch.create_approved_run(store, approval)
        batch.run_supervisor(store, run_id)
        return store, plan, run_id

    def fake_state(self) -> dict[str, object]:
        return json.loads((self.root / "fake-state.json").read_text(encoding="utf-8"))


class PlanningTests(BatchTestCase):
    def test_list_units_prints_exact_generate_all_ids(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta", parts=2)
        with mock.patch("builtins.print") as printer:
            exit_code = batch.main(["list-units", "--root", str(self.root)])
        self.assertEqual(exit_code, 0)
        rendered = "\n".join(" ".join(str(arg) for arg in call.args) for call in printer.call_args_list)
        self.assertIn("UNIT ID\tKIND\tSTATUS\tTITLE\tSOURCE FILES", rendered)
        self.assertIn("01-alpha\ttranscript\tmissing\t01. Alpha\t1", rendered)
        self.assertIn("02-beta\ttranscript\tmissing\t02. Beta\t2", rendered)

    def test_calibrate_accepts_documented_plan_option(self) -> None:
        args = batch.build_parser().parse_args(["calibrate", "--plan", "plan-example", "--root", str(self.root)])
        self.assertEqual(args.plan_option, "plan-example")

    def test_recover_source_attribution_candidate_uses_preserved_full_draft(self) -> None:
        self.add_lesson(1, "Alpha")
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(
            store, approval, selected_unit_ids=["01-alpha"]
        )
        value = (
            "# Alpha\n\nAccording to the source, this concept matters.\n\n"
            "```d2\ndirection: right\na -> b\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        path = (
            batch.run_directory(store, run_id)
            / "units"
            / "01-alpha"
            / "repairable-source-attribution.md"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

        recovered = batch.recover_source_attribution_candidate(
            store, run_id, "01-alpha"
        )

        self.assertEqual(recovered, value)

    def test_batched_source_attribution_repair_changes_only_flagged_lines(self) -> None:
        value = (
            "# Guide\n\nAccording to the source, alpha matters.\n\n"
            "This middle paragraph must remain byte-identical.\n\n"
            "The transcript says beta matters.\n"
        ).encode()
        targets = batch.source_attribution_repair_targets(value)
        replacement = json.dumps(
            {
                "replacements": [
                    {"index": 1, "replacement": "Alpha matters."},
                    {"index": 2, "replacement": "Beta matters."},
                ]
            }
        ).encode()

        valid, _, detail = batch.validate_source_attribution_batch_repair_bytes(
            replacement, targets
        )
        repaired = batch.apply_source_attribution_batch_repair(value, replacement)

        self.assertTrue(valid, detail)
        self.assertEqual(
            repaired,
            (
                "# Guide\n\nAlpha matters.\n\n"
                "This middle paragraph must remain byte-identical.\n\n"
                "Beta matters.\n"
            ).encode(),
        )

    def test_default_invocation_budget_includes_deterministic_repairs(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        _, _, approval = self.approved(max_invocations=None)

        self.assertEqual(approval["contract"]["max_invocations"], 16)

    def test_no_config_infers_one_existing_study_chapters_folder(self) -> None:
        (self.root / batch.CONFIG_NAME).unlink()
        self.add_lesson(1, "Alpha")
        outputs = self.root / "study chapters"
        outputs.mkdir()
        target = outputs / "01. Alpha - Study Chapter.md"
        target.write_text("old curated guide", encoding="utf-8")

        plan = batch.create_plan(self.root)

        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.assertEqual(plan["config"]["output_root"], "study chapters")
        self.assertEqual(plan["config"]["existing_roots"], ["study chapters"])
        self.assertEqual(plan["units"][0]["target"], "study chapters/01. Alpha - Study Chapter.md")

    def test_grouping_exclusions_prompt_precedence_and_curated_target(self) -> None:
        self.add_lesson(1, "Alpha", parts=2)
        (self.root / "transcripts" / "notes.pdf").write_bytes(b"pdf")
        prompt = self.root / "special.md"
        prompt.write_text("Per-unit prompt", encoding="utf-8")
        outputs = self.root / "outputs"
        outputs.mkdir()
        predecessor = outputs / "01. Alpha - Study Chapter.md"
        predecessor.write_text("old curated guide", encoding="utf-8")
        self.write_config(
            prompts={"root": None, "per_unit": {"01-alpha": "special.md"}},
            approved_unit_flags=[],
        )
        plan = batch.create_plan(self.root)
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.assertEqual(len(plan["units"]), 1)
        unit = plan["units"][0]
        self.assertEqual(len(unit["sources"]), 2)
        self.assertEqual(unit["prompt_text"], "Per-unit prompt")
        self.assertEqual(unit["target"], "outputs/01. Alpha - Study Chapter.md")
        self.assertTrue(any(item["path"].endswith("notes.pdf") for item in plan["exclusions"]))

    def test_transcript_chapter_with_spreadsheet_in_lesson_title_is_a_predecessor(self) -> None:
        self.add_lesson(43, "Next Steps with Spreadsheet Class")
        outputs = self.root / "outputs"
        outputs.mkdir()
        predecessor = outputs / "43. Next Steps with Spreadsheet Class - Study Chapter.md"
        predecessor.write_text("old transcript chapter", encoding="utf-8")
        plan = batch.create_plan(self.root)
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.assertEqual(plan["units"][0]["target"], "outputs/43. Next Steps with Spreadsheet Class - Study Chapter.md")

    def test_unique_lesson_number_preserves_a_curated_expanded_title(self) -> None:
        self.add_lesson(6, "Implied Volatility 1")
        outputs = self.root / "outputs"
        outputs.mkdir()
        predecessor = outputs / "6. Implied Volatility 1 - VIX and Dynamic Portfolio Risk - Study Chapter.md"
        predecessor.write_text("old transcript chapter", encoding="utf-8")

        plan = batch.create_plan(self.root)

        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.assertEqual(plan["units"][0]["target"], predecessor.relative_to(self.root).as_posix())

    def test_module_roman_parts_group_and_unparsed_filename_blocks(self) -> None:
        for roman in ("I", "II"):
            path = self.root / "transcripts" / f"Module 2 - Lesson 4 - Part {roman}.txt"
            path.write_text(transcript_text("module", 200), encoding="utf-8")
        odd = self.root / "transcripts" / "misc.txt"
        odd.write_text("too short", encoding="utf-8")
        plan = batch.create_plan(self.root)
        self.assertEqual(len(plan["units"]), 2)
        self.assertTrue(any("misc requires explicit approval" in blocker for blocker in plan["blockers"]))
        grouped = next(unit for unit in plan["units"] if unit["id"].startswith("module-2"))
        self.assertEqual(len(grouped["sources"]), 2)

    def test_short_transcript_and_short_candidate_have_no_length_blocker(self) -> None:
        self.add_lesson(1, "Alpha", words=5)
        plan = batch.create_plan(self.root)
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.assertEqual(plan["units"][0]["flags"], [])
        valid, category, detail = batch.validate_candidate_bytes(
            (
                "Complete.\n\n```d2\nsource -> mastery\n```\n\n"
                f"{batch.COMPLETION_MARKER}\n"
            ).encode(),
            plan["config"]["validators"],
        )
        self.assertTrue(valid, detail)
        self.assertEqual(category, "success")

    def test_pdf_and_spreadsheet_assets_are_first_class_units_with_curated_targets(self) -> None:
        pdf_transcript = self.add_lesson(2, "Statistics")[0]
        pdf_source = self.add_pdf(2, "Basic Statistics Guide")
        workbook_transcript = self.add_lesson(3, "Workbook Class")[0]
        workbook_source = self.add_workbook(3, "Returns Model")
        outputs = self.root / "outputs"
        outputs.mkdir()
        pdf_target = outputs / "2PDF. Introduction to Statistics - Study Companion.md"
        workbook_target = outputs / "3WB. Returns Model - Spreadsheet Study and Build Manual.md"
        pdf_target.write_text("old PDF companion", encoding="utf-8")
        workbook_target.write_text("old workbook manual", encoding="utf-8")
        batch.register_asset_unit(
            self.root,
            unit_id="statistics-pdf",
            kind="pdf",
            title="Introduction to Statistics",
            sources=[str(pdf_source)],
            transcripts=[str(pdf_transcript)],
            output=str(pdf_target),
            prompt=None,
        )
        batch.register_asset_unit(
            self.root,
            unit_id="returns-workbook",
            kind="spreadsheet",
            title="Returns Model",
            sources=[str(workbook_source)],
            transcripts=[str(workbook_transcript)],
            output=str(workbook_target),
            prompt=None,
        )

        plan = batch.create_plan(self.root)

        self.assertEqual(plan["status"], "ready", plan["blockers"])
        pdf_unit = next(unit for unit in plan["units"] if unit["kind"] == "pdf")
        workbook_unit = next(unit for unit in plan["units"] if unit["kind"] == "spreadsheet")
        self.assertEqual(pdf_unit["target"], pdf_target.relative_to(self.root).as_posix())
        self.assertEqual(workbook_unit["target"], workbook_target.relative_to(self.root).as_posix())
        self.assertEqual(len(pdf_unit["asset_sources"]), 1)
        self.assertEqual(len(pdf_unit["transcript_sources"]), 1)
        self.assertEqual(len(workbook_unit["asset_sources"]), 1)
        self.assertEqual(len(workbook_unit["transcript_sources"]), 1)

    def test_unconfigured_assets_are_listed_without_filename_based_unit_inference(self) -> None:
        self.add_lesson(1, "Alpha")
        pdf = self.add_pdf(44, "Arbitrary Reference")
        workbook = self.add_workbook(91, "Unrelated Model")

        plan = batch.create_plan(self.root)

        self.assertEqual({unit["kind"] for unit in plan["units"]}, {"transcript"})
        with mock.patch("builtins.print") as printer:
            exit_code = batch.main(["list-assets", "--root", str(self.root)])
        self.assertEqual(exit_code, 0)
        rendered = "\n".join(" ".join(str(arg) for arg in call.args) for call in printer.call_args_list)
        self.assertIn(f"pdf\t{pdf.relative_to(self.root).as_posix()}", rendered)
        self.assertIn(f"spreadsheet\t{workbook.relative_to(self.root).as_posix()}", rendered)

    def test_workbook_snapshot_contains_formulas_and_spreadsheet_d2_contract(self) -> None:
        transcript = self.add_lesson(3, "Workbook Class")[0]
        workbook = self.add_workbook(3, "Returns Model")
        batch.register_asset_unit(
            self.root,
            unit_id="returns-workbook",
            kind="spreadsheet",
            title="Returns Model",
            sources=[str(workbook)],
            transcripts=[str(transcript)],
            output="outputs/returns-workbook.md",
            prompt=None,
        )
        plan = batch.create_plan(self.root)
        unit = next(unit for unit in plan["units"] if unit["kind"] == "spreadsheet")
        with tempfile.TemporaryDirectory(prefix="study-guide-stage-test-") as temporary:
            stage = Path(temporary)
            batch.copy_stage_inputs(self.root, unit, stage)
            payload = batch.direct_stage_prompt(unit, stage, "D2 diagram 1 is invalid")
        self.assertIn("=A2*2", payload)
        self.assertIn("Formula archetypes", payload)
        self.assertIn("D2 dependency diagram", payload)
        self.assertIn("Never emit Mermaid", payload)
        self.assertIn("REQUIRED CORRECTION FROM THE PREVIOUS ATTEMPT", payload)
        self.assertIn("D2 diagram 1 is invalid", payload)

    def test_pdf_stage_contract_requires_direct_exposition_and_equation_walkthroughs(self) -> None:
        transcript = self.add_lesson(2, "Statistics")[0]
        source = self.add_pdf(2, "Basic Statistics Guide")
        batch.register_asset_unit(
            self.root,
            unit_id="statistics-pdf",
            kind="pdf",
            title="Introduction to Statistics",
            sources=[str(source)],
            transcripts=[str(transcript)],
            output="outputs/statistics.md",
            prompt=None,
        )
        unit = next(unit for unit in batch.create_plan(self.root)["units"] if unit["kind"] == "pdf")

        instruction = batch.stage_instruction(unit)

        self.assertIn("Write the teaching directly", instruction)
        self.assertIn("Constituent breakdown", instruction)
        self.assertIn("Evaluate the operations", instruction)
        self.assertIn("render it as one Markdown table", instruction)

    def test_d2_validation_rejects_mermaid_missing_and_invalid_diagrams(self) -> None:
        validators = batch.DEFAULT_CONFIG["validators"]
        missing = f"# Guide\n\nNo diagram.\n\n{batch.COMPLETION_MARKER}\n".encode()
        valid, _, detail = batch.validate_candidate_bytes(missing, validators)
        self.assertFalse(valid)
        self.assertIn("lacks a fenced D2", detail)

        mermaid = (
            "# Guide\n\n```mermaid\na-->b\n```\n\n```d2\na -> b\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        valid, _, detail = batch.validate_candidate_bytes(mermaid, validators)
        self.assertFalse(valid)
        self.assertIn("contains Mermaid", detail)

        invalid = (
            "# Guide\n\n```d2\na: {\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        valid, _, detail = batch.validate_candidate_bytes(invalid, validators)
        self.assertFalse(valid)
        self.assertIn("D2 diagram 1 is invalid", detail)

    def test_d2_layout_validation_rejects_a_long_single_lane(self) -> None:
        tall = (
            "# Guide\n\n```d2\n"
            "a: \"Stage A\"\nb: \"Stage B\"\nc: \"Stage C\"\nd: \"Stage D\"\n"
            "e: \"Stage E\"\nf: \"Stage F\"\ng: \"Stage G\"\nh: \"Stage H\"\n"
            "a -> b -> c -> d -> e -> f -> g -> h\n"
            "```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()

        valid, category, detail = batch.validate_candidate_bytes(
            tall, batch.DEFAULT_CONFIG["validators"]
        )

        self.assertFalse(valid)
        self.assertEqual(category, "diagram_layout")
        self.assertIn("too tall", detail)

    def test_validation_rejects_source_attribution_phrases(self) -> None:
        candidate = (
            "# Guide\n\nThe PDF states the formula.\n\n"
            "```d2\ninput -> result\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()

        valid, category, detail = batch.validate_candidate_bytes(
            candidate, batch.DEFAULT_CONFIG["validators"]
        )

        self.assertFalse(valid)
        self.assertEqual(category, "source_attribution")
        self.assertIn("The PDF", detail)

    def test_source_attribution_repair_changes_only_the_target_line(self) -> None:
        original = (
            "# Guide\n\nKeep this paragraph byte-for-byte — including Unicode.\n\n"
            "The source explains that ATRP normalizes range by price.\n\n"
            "```d2\ninput -> result\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        replacement = b"ATRP normalizes range by price.\n"

        target = batch.source_attribution_repair_target(original)
        valid, category, _ = batch.validate_source_attribution_repair_bytes(
            replacement, target["line"]
        )
        self.assertTrue(valid)
        self.assertEqual(category, "success")

        repaired = batch.apply_source_attribution_repair(original, replacement)
        old_text = original.decode()
        new_text = repaired.decode()
        self.assertEqual(old_text[:target["start"]], new_text[:target["start"]])
        self.assertEqual(
            old_text[target["end"]:],
            new_text[target["start"] + len(replacement.decode().rstrip()):],
        )
        valid, category, _ = batch.validate_candidate_bytes(
            repaired, batch.DEFAULT_CONFIG["validators"]
        )
        self.assertTrue(valid)
        self.assertEqual(category, "success")

    def test_diagram_repair_changes_only_the_targeted_d2_source(self) -> None:
        original = (
            "# Guide\n\nKeep this prose byte-for-byte — including Unicode.\n\n"
            "```d2\nconcept: {\n  shape: Not a real D2 shape\n}\n```\n\n"
            "## Review\n\nKeep this too.\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        valid, category, detail = batch.validate_candidate_bytes(
            original, batch.DEFAULT_CONFIG["validators"]
        )
        self.assertFalse(valid)
        self.assertEqual(category, "diagram_invalid")
        repaired_source = "concept: Repaired concept\nconcept -> mastery\nmastery: Mastery"
        repaired = batch.apply_diagram_repair(original, category, detail, repaired_source)

        old_text = original.decode()
        new_text = repaired.decode()
        old_match = batch.D2_FENCE.search(old_text)
        new_match = batch.D2_FENCE.search(new_text)
        self.assertIsNotNone(old_match)
        self.assertIsNotNone(new_match)
        assert old_match is not None and new_match is not None
        self.assertEqual(
            old_text[:old_match.start(1)].encode(), new_text[:new_match.start(1)].encode()
        )
        self.assertEqual(
            old_text[old_match.end(1):].encode(), new_text[new_match.end(1):].encode()
        )
        valid, category, _ = batch.validate_candidate_bytes(
            repaired, batch.DEFAULT_CONFIG["validators"]
        )
        self.assertTrue(valid)
        self.assertEqual(category, "success")

    def test_numbered_letter_parts_with_different_leading_numbers_group(self) -> None:
        first = self.root / "transcripts" / "16. Portfolio Foundations 1a.txt"
        second = self.root / "transcripts" / "17. Portfolio Foundations 1b.txt"
        first.write_text(transcript_text("portfolio", 200), encoding="utf-8")
        second.write_text(transcript_text("portfolio", 200), encoding="utf-8")
        plan = batch.create_plan(self.root)
        self.assertEqual(len(plan["units"]), 1)
        self.assertEqual(len(plan["units"][0]["sources"]), 2)

    def test_unconfigured_prompt_files_are_ignored_while_predecessors_and_collisions_block(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        (self.root / "prompt-transcript-to-study-guide.md").write_text("one", encoding="utf-8")
        (self.root / "transcript-study-guide-prompt.md").write_text("two", encoding="utf-8")
        outputs = self.root / "outputs"
        outputs.mkdir()
        (outputs / "01. Alpha - Study Guide.md").write_text("old one", encoding="utf-8")
        (outputs / "01. Alpha - Study Chapter.md").write_text("old two", encoding="utf-8")
        ambiguous = batch.create_plan(self.root)
        ambiguous_joined = "\n".join(ambiguous["blockers"])
        self.assertNotIn("ambiguous recognized prompts", ambiguous_joined)
        self.assertIn("ambiguous predecessors", ambiguous_joined)
        self.write_config(
            unit_overrides={
                "01-alpha": {"output": "outputs/shared.md"},
                "02-beta": {"output": "outputs/shared.md"},
            }
        )
        plan = batch.create_plan(self.root)
        joined = "\n".join(plan["blockers"])
        self.assertNotIn("ambiguous recognized prompts", joined)
        self.assertIn("target collision", joined)


class TurnkeyTests(BatchTestCase):
    def test_repair_sections_regenerates_only_selected_spans_and_promotes(self) -> None:
        self.add_lesson(1, "Alpha")
        outputs = self.root / "outputs"
        outputs.mkdir()
        target = outputs / "01. Alpha - Study Guide.md"
        original = (
            "# Lesson Study Guide\n\n"
            "## Overview\n\nKeep this prose byte-for-byte — including Unicode.\n\n"
            "```d2\n"
            "material: \"Course material\"\nconcepts: \"Key concepts\"\n"
            "practice: \"Guided practice\"\nmastery: \"Demonstrated mastery\"\n"
            "material -> concepts -> practice -> mastery\n"
            "```\n\n"
            "## Review Questions\n\nOld repetitive questions remain here.\n\n"
            "---\n\n## Glossary\n\n**Alpha:** A test definition.\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        )
        target.write_text(original, encoding="utf-8")
        args = batch.build_parser().parse_args(
            [
                "repair-sections", "--root", str(self.root), "--unit", "01-alpha",
                "--diagram", "1", "--section", "Review Questions", "--quiet",
            ]
        )

        result = batch.repair_sections(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["canonical_files_changed"])
        self.assertIsNotNone(result["promotion_id"])
        installed = target.read_text(encoding="utf-8")
        self.assertIn('direction: right', installed)
        self.assertIn("The targeted section was regenerated", installed)
        old_spans = batch.targeted_repair_spans(original, [1], ["Review Questions"])
        new_spans = batch.targeted_repair_spans(installed, [1], ["Review Questions"])
        self.assertEqual(original[:old_spans[0]["start"]], installed[:new_spans[0]["start"]])
        self.assertEqual(
            original[old_spans[0]["end"]:old_spans[1]["start"]],
            installed[new_spans[0]["end"]:new_spans[1]["start"]],
        )
        self.assertEqual(original[old_spans[1]["end"]:], installed[new_spans[1]["end"]:])
        self.assertEqual(self.fake_state()["stages"]["section_repair"], 1)

    def test_generate_all_can_run_and_install_one_pdf_unit(self) -> None:
        transcript = self.add_lesson(2, "Statistics")[0]
        source = self.add_pdf(2, "Basic Statistics Guide")
        outputs = self.root / "outputs"
        outputs.mkdir()
        target = outputs / "2PDF. Introduction to Statistics - Study Companion.md"
        target.write_text("old companion", encoding="utf-8")
        batch.register_asset_unit(
            self.root,
            unit_id="statistics-pdf",
            kind="pdf",
            title="Introduction to Statistics",
            sources=[str(source)],
            transcripts=[str(transcript)],
            output=str(target),
            prompt=None,
        )
        plan = batch.create_plan(self.root)
        pdf_unit = next(unit for unit in plan["units"] if unit["kind"] == "pdf")
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--unit", pdf_unit["id"]]
        )

        with mock.patch.object(batch, "extract_pdf_text", return_value="# Extracted PDF\n\nStatistics source"):
            with mock.patch("builtins.print"):
                result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertEqual([Path(path).resolve() for path in result["output_paths"]], [target.resolve()])
        installed = target.read_text(encoding="utf-8")
        self.assertIn("```d2", installed)
        self.assertIn(batch.COMPLETION_MARKER, installed)

    def test_generate_all_accepts_model_reasoning_and_verbosity_overrides(self) -> None:
        self.add_lesson(1, "Alpha")
        args = batch.build_parser().parse_args(
            [
                "generate-all",
                "--root", str(self.root),
                "--model", "override-model",
                "--reasoning-effort", "xhigh",
                "--verbosity", "medium",
            ]
        )
        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        for call in self.fake_state()["calls"]:
            argv = call["argv"]
            self.assertEqual(argv[argv.index("--model") + 1], "override-model")
            self.assertIn('model_reasoning_effort="xhigh"', argv)
            self.assertIn('model_verbosity="medium"', argv)

    def test_generate_all_installs_canonical_files_by_default(self) -> None:
        self.add_lesson(1, "Alpha")
        outputs = self.root / "outputs"
        outputs.mkdir()
        target = outputs / "01. Alpha - Study Guide.md"
        target.write_text("old canonical", encoding="utf-8")

        args = batch.build_parser().parse_args(["generate-all", "--root", str(self.root)])
        self.assertEqual(args.command, "generate-all")
        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root)

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["canonical_files_changed"])
        self.assertIn(batch.COMPLETION_MARKER, target.read_text(encoding="utf-8"))
        self.assertEqual([Path(path).resolve() for path in result["output_paths"]], [target.resolve()])
        self.assertIsNotNone(result["promotion_id"])
        candidate = Path(result["candidates_path"]) / "01-alpha" / "candidate.md"
        self.assertFalse(candidate.exists())
        self.assertEqual(self.fake_state()["total"], 1)
        self.assertIsNone(result["calibration_run_id"])
        store = batch.Store(self.root)
        kinds = [row["kind"] for row in store.rows("SELECT kind FROM runs ORDER BY created_at")]
        self.assertEqual(kinds, ["batch"])

    def test_generate_all_calibrate_first_reuses_matching_completed_calibration(self) -> None:
        self.add_lesson(1, "Alpha")
        plan = batch.create_plan(self.root)
        self.seed_calibration(plan)
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--calibrate-first"]
        )

        with mock.patch.object(batch, "execute_calibration", side_effect=AssertionError("must reuse")):
            with mock.patch("builtins.print"):
                result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.fake_state()["total"], 1)

    def test_generate_all_stops_before_model_calls_when_plan_is_blocked(self) -> None:
        path = self.root / "transcripts" / "misc.txt"
        path.write_text("too short", encoding="utf-8")

        with mock.patch("builtins.print"):
            with self.assertRaisesRegex(batch.BatchError, "needs configuration"):
                batch.generate_all(self.root)

        self.assertFalse((self.root / "fake-state.json").exists())

    def test_generate_all_unit_runs_only_the_selected_lesson(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--unit", "01-alpha"]
        )

        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.fake_state()["total"], 1)
        self.assertEqual(len(result["output_paths"]), 1)
        self.assertIn(batch.COMPLETION_MARKER, Path(result["output_paths"][0]).read_text(encoding="utf-8"))
        store = batch.Store(self.root)
        run_units = store.rows("SELECT unit_id FROM units WHERE run_id = ?", (result["run_id"],))
        self.assertEqual([row["unit_id"] for row in run_units], ["01-alpha"])

    def test_generate_all_repeated_unit_runs_selected_lessons_in_one_batch(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        self.add_lesson(3, "Gamma")
        args = batch.build_parser().parse_args(
            [
                "generate-all",
                "--root",
                str(self.root),
                "--unit",
                "01-alpha",
                "--unit",
                "03-gamma",
            ]
        )

        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        # Both selected units share one CSV dispatcher wave.
        self.assertEqual(self.fake_state()["total"], 1)
        self.assertEqual(len(result["output_paths"]), 2)
        store = batch.Store(self.root)
        run_units = store.rows(
            "SELECT unit_id FROM units WHERE run_id = ? ORDER BY ordinal",
            (result["run_id"],),
        )
        self.assertEqual([row["unit_id"] for row in run_units], ["01-alpha", "03-gamma"])

    def test_generate_all_missing_only_skips_existing_targets(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        self.write_config(
            unit_overrides={
                "01-alpha": {"output": "outputs/alpha.md"},
                "02-beta": {"output": "outputs/beta.md"},
            }
        )
        (self.root / "outputs").mkdir()
        (self.root / "outputs" / "alpha.md").write_text("already present", encoding="utf-8")
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--missing-only"]
        )

        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.fake_state()["total"], 1)
        self.assertEqual(
            [Path(path).resolve() for path in result["output_paths"]],
            [(self.root / "outputs" / "beta.md").resolve()],
        )
        self.assertIn(batch.COMPLETION_MARKER, (self.root / "outputs" / "beta.md").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "outputs" / "alpha.md").read_text(encoding="utf-8"), "already present")

    def test_generate_all_candidates_only_retains_hidden_candidate(self) -> None:
        self.add_lesson(1, "Alpha")
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--candidates-only"]
        )

        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertFalse(result["canonical_files_changed"])
        self.assertIsNone(result["promotion_id"])
        candidate = Path(result["candidates_path"]) / "01-alpha" / "candidate.md"
        self.assertTrue(candidate.is_file())

    def test_five_unit_candidates_only_batch_fans_out_four_plus_one(self) -> None:
        for number in range(1, 6):
            self.add_lesson(number, f"Synthetic {number}")
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--candidates-only"]
        )

        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["canonical_files_changed"])
        self.assertEqual([wave["size"] for wave in self.fake_state()["waves"]], [4, 1])
        candidates = list(Path(result["candidates_path"]).glob("*/candidate.md"))
        self.assertEqual(len(candidates), 5)
        self.assertFalse((self.root / "outputs").exists())

    def test_generate_all_missing_only_makes_no_calls_when_all_targets_exist(self) -> None:
        self.add_lesson(1, "Alpha")
        self.write_config(unit_overrides={"01-alpha": {"output": "outputs/alpha.md"}})
        (self.root / "outputs").mkdir()
        (self.root / "outputs" / "alpha.md").write_text("already present", encoding="utf-8")
        args = batch.build_parser().parse_args(
            ["generate-all", "--root", str(self.root), "--missing-only"]
        )

        with mock.patch("builtins.print"):
            result = batch.generate_all(self.root, args)

        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["run_id"])
        self.assertIn("no model calls", result["detail"])
        self.assertFalse((self.root / "fake-state.json").exists())


class ExecutionTests(BatchTestCase):
    def test_real_path_calibration_approval_success_isolation_promotion_and_rollback(self) -> None:
        self.add_lesson(1, "Alpha")
        outputs = self.root / "outputs"
        outputs.mkdir()
        target = outputs / "01. Alpha - Study Guide.md"
        target.write_text("old canonical", encoding="utf-8")
        plan = batch.create_plan(self.root)
        store = batch.Store(self.root)
        report = batch.execute_calibration(
            store,
            plan,
            argparse.Namespace(deadline_hours=0.2, timeout_minutes=0.02, max_tokens=10000),
        )
        self.assertEqual(report["status"], "completed")
        self.assertEqual(target.read_text(encoding="utf-8"), "old canonical")
        approval = batch.approve_plan(store, plan, self.approval_args())
        run_id = batch.create_approved_run(store, approval)
        self.assertEqual(batch.run_supervisor(store, run_id), "completed")
        self.assertEqual(target.read_text(encoding="utf-8"), "old canonical")
        calls = self.fake_state()["calls"]
        self.assertEqual(len({call["cwd"] for call in calls}), len(calls))
        for call in calls:
            argv = call["argv"]
            self.assertIn("--json", argv)
            self.assertNotIn("--ignore-user-config", argv)
            self.assertNotIn("--sandbox", argv)
            self.assertIn('model_reasoning_effort="xhigh"', argv)
            self.assertIn('model_verbosity="high"', argv)
            self.assertIn("--ignore-rules", argv)
            self.assertIn("--skip-git-repo-check", argv)
            self.assertNotIn("--add-dir", argv)
            self.assertIn("features.enable_fanout=true", argv)
            self.assertIn("features.multi_agent_v2.hide_spawn_agent_metadata=false", argv)
            self.assertIn('features.multi_agent_v2.tool_namespace="agents"', argv)
            self.assertIn("agents.max_depth=2", argv)
            self.assertIn("agents.max_threads=6", argv)
            self.assertIn('default_permissions=":danger-full-access"', argv)
            self.assertTrue(any(arg.startswith("sqlite_home=") for arg in argv), argv)
            self.assertTrue(
                any(arg.startswith("skills.config=") and "study-guide-batch" in arg for arg in argv),
                argv,
            )
            self.assertEqual(call["inherited_markers"], [])
            self.assertNotIn("--output-schema", argv)
        unit = store.row("SELECT * FROM units WHERE run_id = ?", (run_id,))
        self.assertEqual(unit["state"], "approved")
        self.assertTrue(Path(unit["candidate_path"]).is_file())
        promotion_id = batch.promote_run(store, run_id)
        self.assertIn(batch.COMPLETION_MARKER, target.read_text(encoding="utf-8"))
        batch.rollback_promotion(store, promotion_id)
        self.assertEqual(target.read_text(encoding="utf-8"), "old canonical")
        self.assertTrue(Path(unit["candidate_path"]).is_file())

    def test_bounded_retries_for_malformed_and_missing_outputs(self) -> None:
        scenarios = {
            "malformed_jsonl": ("generation", 2),
            "missing_candidate": ("generation", 2),
            "truncated": ("generation", 2),
            "transient": ("generation", 2),
        }
        for scenario, (stage, calls) in scenarios.items():
            with self.subTest(scenario=scenario):
                child = self.root / scenario
                child.mkdir()
                old_root = self.root
                self.root = child
                (self.root / "transcripts").mkdir()
                os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
                os.environ["FAKE_CODEX_SCENARIO"] = scenario
                self.write_config()
                self.add_lesson(1, "Alpha")
                store, _, run_id = self.execute()
                self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
                attempts = store.rows(
                    "SELECT stage FROM attempts WHERE run_id = ? ORDER BY id", (run_id,)
                )
                self.assertEqual([row["stage"] for row in attempts], [stage] * calls)
                self.root = old_root
                os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
                os.environ["FAKE_CODEX_SCENARIO"] = "success"

    def test_invalid_d2_repairs_only_diagram_without_regenerating_guide(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "invalid_d2"
        store, _, run_id = self.execute()
        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
        state = self.fake_state()
        self.assertEqual(state["stages"]["generation"], 1)
        self.assertEqual(state["stages"]["diagram_repair"], 1)
        attempt_stages = [
            row["stage"]
            for row in store.rows("SELECT stage FROM attempts WHERE run_id = ? ORDER BY id", (run_id,))
        ]
        self.assertEqual(attempt_stages, ["generation", "diagram_repair"])

    def test_diagram_layout_repair_retries_an_opposite_overcorrection(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "layout_retry"

        store, _, run_id = self.execute()

        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
        state = self.fake_state()
        self.assertEqual(state["stages"]["generation"], 1)
        self.assertEqual(state["stages"]["diagram_repair"], 2)

    def test_timeout_kills_descendant_and_policy_activity_fails(self) -> None:
        self.add_lesson(1, "Alpha")
        pid_file = self.root / "descendant.pid"
        heartbeat_file = self.root / "descendant-heartbeat.txt"
        os.environ["FAKE_CODEX_SCENARIO"] = "timeout"
        os.environ["FAKE_CODEX_DESCENDANT_PID"] = str(pid_file)
        os.environ["FAKE_CODEX_DESCENDANT_HEARTBEAT"] = str(heartbeat_file)
        store, _, run_id = self.execute(timeout_minutes=0.005, transient_retries=0)
        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "failed")
        self.assertTrue(pid_file.is_file())
        self.assertTrue(heartbeat_file.is_file())
        heartbeat = heartbeat_file.read_text(encoding="utf-8")
        time.sleep(0.3)
        self.assertEqual(heartbeat_file.read_text(encoding="utf-8"), heartbeat)

        policy_root = self.root / "policy"
        policy_root.mkdir()
        self.root = policy_root
        (self.root / "transcripts").mkdir()
        os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
        os.environ["FAKE_CODEX_SCENARIO"] = "mcp"
        self.write_config()
        self.add_lesson(1, "Alpha")
        store, _, run_id = self.execute()
        unit = store.row("SELECT * FROM units WHERE run_id = ?", (run_id,))
        self.assertEqual(unit["state"], "failed")
        self.assertIn("unexpected MCP", unit["detail"])

    def test_auth_and_environment_checkpoint_without_extra_stages(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "auth"
        store, _, run_id = self.execute()
        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertIn("authentication", run["stop_reason"])

        environment_root = self.root / "environment"
        environment_root.mkdir()
        self.root = environment_root
        (self.root / "transcripts").mkdir()
        os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
        os.environ["FAKE_CODEX_SCENARIO"] = "environment"
        self.write_config()
        self.add_lesson(1, "Alpha")
        store, _, run_id = self.execute()
        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertIn("host environment", run["stop_reason"])

    def test_json_only_usage_limit_event_checkpoints_as_quota(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "quota_json_only"

        store, _, run_id = self.execute()

        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertIn("quota", run["stop_reason"])

    def test_invocation_budget_and_parallel_contract(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        store, plan, approval = self.approved(max_invocations=1, max_tokens=10000)
        run_id = batch.create_approved_run(store, approval)
        batch.run_supervisor(store, run_id)
        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertEqual(run["invocations_started"], 1)

        contract = batch.make_contract(
            plan,
            workers=2,
            deadline_hours=1,
            timeout_minutes=1,
            max_invocations=10,
            max_tokens=10000,
            transient_retries=0,
        )
        self.assertEqual(contract["workers"], 2)
        with self.assertRaisesRegex(batch.BatchError, "max-concurrency"):
            batch.make_contract(
                plan,
                workers=7,
                deadline_hours=1,
                timeout_minutes=1,
                max_invocations=10,
                max_tokens=10000,
                transient_retries=0,
            )
        parsed = batch.build_parser().parse_args(["generate-all", "--max-concurrency", "2"])
        self.assertEqual(parsed.max_concurrency, 2)
        with self.assertRaises(SystemExit):
            batch.build_parser().parse_args(["generate-all", "--workers", "2"])

    def test_resume_retries_an_interrupted_generation_only(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "auth"
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)
        batch.run_supervisor(store, run_id)
        before = self.fake_state()
        self.assertEqual(before["total"], 1)
        self.assertNotIn("generation", before["stages"])
        self.assertEqual(store.row("SELECT state FROM units WHERE run_id = ?", (run_id,))["state"], "generating")
        os.environ["FAKE_CODEX_SCENARIO"] = "success"
        self.assertEqual(batch.resume_run(store, run_id), "completed")
        after = self.fake_state()
        self.assertEqual(after["stages"]["generation"], 1)
        self.assertEqual(after["total"], 2)
        self.assertEqual(set(after["stages"]), {"generation"})
        self.assertEqual(batch.resume_run(store, run_id), "completed")
        self.assertEqual(self.fake_state(), after)

    def test_stale_lease_recovery_and_hard_wall_deadline(self) -> None:
        self.add_lesson(1, "Alpha")
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)
        with store.transaction() as connection:
            connection.execute("UPDATE runs SET status = 'stopped' WHERE id = ?", (run_id,))
            connection.execute(
                "UPDATE units SET state = 'generating', lease_owner = 'dead-worker', "
                "lease_until = '2000-01-01T00:00:00+00:00' WHERE run_id = ?",
                (run_id,),
            )
        self.assertEqual(batch.resume_run(store, run_id), "completed")
        self.assertEqual(self.fake_state()["stages"]["generation"], 1)

        deadline_root = self.root / "deadline"
        deadline_root.mkdir()
        self.root = deadline_root
        (self.root / "transcripts").mkdir()
        os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
        os.environ["FAKE_CODEX_DELAY"] = "2"
        self.write_config()
        self.add_lesson(1, "Alpha")
        store, _, run_id = self.execute(deadline_hours=0.0001, timeout_minutes=0.05)
        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertIn("hard wall-clock deadline", run["stop_reason"])

    def test_detached_supervisor_can_be_stopped(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_DELAY"] = "3"
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)
        with mock.patch.object(batch.shutil, "which", return_value=None):
            pid = batch.detach_supervisor(store, run_id)
        self.assertGreater(pid, 0)
        deadline = time.time() + 5
        while time.time() < deadline:
            status = store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"]
            if status == "running":
                break
            time.sleep(0.05)
        self.assertEqual(status, "running")
        batch.stop_run(store, run_id)
        deadline = time.time() + 8
        while time.time() < deadline:
            status = store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"]
            if status == "stopped":
                break
            time.sleep(0.05)
        self.assertEqual(status, "stopped")
        # The signal handler checkpoints the run before the detached process has
        # finished its final status exports. Wait for the tracked child to be
        # reaped so temporary-directory cleanup cannot race those last writes.
        deadline = time.time() + 5
        while time.time() < deadline:
            with batch.DETACHED_LOCK:
                still_tracked = any(process.pid == pid for process in batch.DETACHED_PROCESSES)
            if not still_tracked:
                break
            time.sleep(0.05)
        self.assertFalse(still_tracked)
        self.assertTrue((batch.run_directory(store, run_id) / "supervisor.log").is_file())

    def test_source_prompt_model_and_codex_changes_invalidate(self) -> None:
        source = self.add_lesson(1, "Alpha")[0]
        prompt = self.root / "prompt.md"
        prompt.write_text("root prompt", encoding="utf-8")
        self.write_config(prompts={"root": "prompt.md", "per_unit": {}})
        store, plan, approval = self.approved()
        source.write_text(source.read_text(encoding="utf-8") + " changed", encoding="utf-8")
        with self.assertRaises(batch.StaleInput):
            batch.create_approved_run(store, approval)
        source.write_text(transcript_text("Alpha", 400), encoding="utf-8")
        prompt.write_text("changed prompt", encoding="utf-8")
        with self.assertRaises(batch.StaleInput):
            batch.create_approved_run(store, approval)
        prompt.write_text("root prompt", encoding="utf-8")
        os.environ["FAKE_CODEX_VERSION"] = "codex-cli fake-2.0"
        with self.assertRaises(batch.StaleInput):
            batch.create_approved_run(store, approval)
        os.environ["FAKE_CODEX_VERSION"] = "codex-cli fake-1.0"
        original_id = plan["id"]
        config = json.loads((self.root / batch.CONFIG_NAME).read_text(encoding="utf-8"))
        config["models"]["generator"] = "different-model"
        (self.root / batch.CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")
        self.assertNotEqual(batch.create_plan(self.root)["id"], original_id)

    def test_nine_units_fan_out_as_four_four_one_at_depth_two(self) -> None:
        for number in range(1, 10):
            self.add_lesson(number, f"Lesson {number}")

        store, _, run_id = self.execute()

        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
        state = self.fake_state()
        self.assertEqual([wave["size"] for wave in state["waves"]], [4, 4, 1])
        self.assertTrue(all(wave["multi_agent_enabled"] for wave in state["waves"]))
        self.assertTrue(all(wave["fanout_enabled"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_spawn_metadata_visible"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_agents_namespace"] for wave in state["waves"]))
        self.assertTrue(all(wave["max_depth_two"] for wave in state["waves"]))
        self.assertTrue(all(wave["user_config_enabled"] for wave in state["waves"]))
        self.assertTrue(all(wave["legacy_sandbox_absent"] for wave in state["waves"]))
        self.assertTrue(all(wave["nested_sandbox_disabled"] for wave in state["waves"]))
        self.assertEqual(state["workers_total"], 9)

    def test_missing_reports_and_malformed_results_retry_without_legacy_fallback(self) -> None:
        for scenario, first_category in (
            ("missing_report", "missing_report"),
            ("malformed_result", "malformed_csv"),
        ):
            with self.subTest(scenario=scenario):
                child = self.root / scenario
                child.mkdir()
                old_root = self.root
                self.root = child
                (self.root / "transcripts").mkdir()
                os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
                os.environ["FAKE_CODEX_SCENARIO"] = scenario
                self.write_config()
                self.add_lesson(1, "Alpha")
                store, _, run_id = self.execute()
                categories = [
                    row["category"]
                    for row in store.rows(
                        "SELECT category FROM attempts WHERE run_id = ? ORDER BY id", (run_id,)
                    )
                ]
                self.assertEqual(categories, [first_category, "success"])
                self.assertEqual(self.fake_state()["total"], 2)
                self.root = old_root
                os.environ["FAKE_CODEX_STATE"] = str(self.root / "fake-state.json")
                os.environ["FAKE_CODEX_SCENARIO"] = "success"

    def test_csv_capability_unavailable_fails_clearly_without_fallback(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "capability_unavailable"

        store, _, run_id = self.execute()

        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertIn("CSV subagent capability unavailable", run["stop_reason"])
        self.assertEqual(self.fake_state()["total"], 1)
        self.assertEqual(self.fake_state()["workers_total"], 0)

    def test_resume_never_regenerates_units_approved_before_quota_checkpoint(self) -> None:
        for number in range(1, 6):
            self.add_lesson(number, f"Lesson {number}")
        os.environ["FAKE_CODEX_QUOTA_AFTER"] = "4"
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)

        batch.run_supervisor(store, run_id)

        approved_before = {
            row["unit_id"]
            for row in store.rows(
                "SELECT unit_id FROM units WHERE run_id = ? AND state = 'approved'", (run_id,)
            )
        }
        self.assertEqual(len(approved_before), 4)
        os.environ.pop("FAKE_CODEX_QUOTA_AFTER")
        self.assertEqual(batch.resume_run(store, run_id), "completed")
        calls = [row["unit_id"] for row in self.fake_state()["worker_calls"]]
        for unit_id in approved_before:
            self.assertEqual(calls.count(unit_id), 1)


class PurgeTests(BatchTestCase):
    def create_completed_run(self) -> tuple[batch.Store, dict[str, object], str]:
        self.add_lesson(1, "Alpha")
        return self.execute()

    def test_guarded_purge_success_removes_only_the_run_lifecycle(self) -> None:
        store, plan, run_id = self.create_completed_run()
        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        assert run is not None
        approval_id = run["approval_id"]
        candidate = Path(
            store.row("SELECT candidate_path FROM units WHERE run_id = ?", (run_id,))[
                "candidate_path"
            ]
        )
        self.assertTrue(candidate.is_file())

        result = batch.purge_run(store, run_id)

        self.assertEqual(result["units_deleted"], 1)
        self.assertEqual(result["attempts_deleted"], 1)
        self.assertIsNone(store.row("SELECT id FROM runs WHERE id = ?", (run_id,)))
        self.assertIsNone(store.row("SELECT id FROM approvals WHERE id = ?", (approval_id,)))
        self.assertIsNone(store.row("SELECT id FROM plans WHERE id = ?", (plan["id"],)))
        self.assertFalse(candidate.exists())
        self.assertFalse(batch.run_directory(store, run_id).exists())

    def test_guarded_purge_refuses_a_live_supervisor(self) -> None:
        self.add_lesson(1, "Alpha")
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)
        with store.transaction() as connection:
            connection.execute(
                "UPDATE runs SET supervisor_pid = ? WHERE id = ?", (os.getpid(), run_id)
            )

        with self.assertRaisesRegex(batch.BatchError, "still live"):
            batch.purge_run(store, run_id)

    def test_guarded_purge_refuses_a_shared_plan(self) -> None:
        self.add_lesson(1, "Alpha")
        store, plan, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)
        with store.transaction() as connection:
            connection.execute(
                "INSERT INTO approvals(id, plan_id, created_at, mapping_hash, contract_json, path) "
                "VALUES('approval-shared', ?, ?, ?, '{}', 'unused')",
                (plan["id"], batch.now_iso(), plan["mapping_hash"]),
            )

        with self.assertRaisesRegex(batch.BatchError, "plan .* is shared"):
            batch.purge_run(store, run_id)

    def test_guarded_purge_refuses_a_promotion(self) -> None:
        store, _, run_id = self.create_completed_run()
        promotion_id = batch.promote_run(store, run_id)

        with self.assertRaisesRegex(batch.BatchError, promotion_id):
            batch.purge_run(store, run_id)

    def test_purge_transaction_failure_restores_rows_and_staged_directories(self) -> None:
        store, _, run_id = self.create_completed_run()
        run_dir = batch.run_directory(store, run_id)
        candidate_dir = self.root / ".study-guide-batch" / "candidates" / run_id
        before_attempts = len(
            store.rows("SELECT id FROM attempts WHERE run_id = ?", (run_id,))
        )
        os.environ["STUDY_GUIDE_BATCH_TEST_PURGE_FAIL"] = "1"
        try:
            with self.assertRaisesRegex(batch.BatchError, "staged paths were restored"):
                batch.purge_run(store, run_id)
        finally:
            os.environ.pop("STUDY_GUIDE_BATCH_TEST_PURGE_FAIL")

        self.assertIsNotNone(store.row("SELECT id FROM runs WHERE id = ?", (run_id,)))
        self.assertEqual(
            len(store.rows("SELECT id FROM attempts WHERE run_id = ?", (run_id,))),
            before_attempts,
        )
        self.assertTrue(run_dir.is_dir())
        self.assertTrue(candidate_dir.is_dir())


class PromotionAndIntegrationTests(BatchTestCase):
    def test_approved_only_promotion_installs_only_checkpointed_candidates(self) -> None:
        self.add_lesson(1, "Alpha")
        self.add_lesson(2, "Beta")
        store, plan, run_id = self.execute()
        with store.transaction() as connection:
            connection.execute(
                "UPDATE runs SET status = 'checkpointed', stop_reason = ?, supervisor_pid = NULL "
                "WHERE id = ?",
                ("maximum invocation budget exhausted", run_id),
            )
            connection.execute(
                "UPDATE units SET state = 'generating' WHERE run_id = ? AND unit_id = ?",
                (run_id, "02-beta"),
            )

        promotion_id = batch.promote_run(store, run_id, approved_only=True)

        plan_units = {unit["id"]: unit for unit in plan["units"]}
        alpha = self.root / plan_units["01-alpha"]["target"]
        beta = self.root / plan_units["02-beta"]["target"]
        self.assertIn(batch.COMPLETION_MARKER, alpha.read_text(encoding="utf-8"))
        self.assertFalse(beta.exists())
        promoted = store.rows(
            "SELECT unit_id FROM promotion_items WHERE promotion_id = ?",
            (promotion_id,),
        )
        self.assertEqual([row["unit_id"] for row in promoted], ["01-alpha"])

    def test_rollback_refuses_a_corrupt_archive(self) -> None:
        self.add_lesson(1, "Alpha")
        outputs = self.root / "outputs"
        outputs.mkdir()
        target = outputs / "01. Alpha - Study Guide.md"
        target.write_text("old canonical", encoding="utf-8")
        store, _, run_id = self.execute()
        promotion_id = batch.promote_run(store, run_id)
        item = store.row("SELECT archive_path FROM promotion_items WHERE promotion_id = ?", (promotion_id,))
        archive = Path(item["archive_path"])
        archive.write_text("corrupt archive", encoding="utf-8")
        with self.assertRaises(batch.StaleInput):
            batch.rollback_promotion(store, promotion_id)

    def test_interrupted_promotion_restores_and_pending_journal_resumes(self) -> None:
        self.add_lesson(1, "Alpha")
        outputs = self.root / "outputs"
        outputs.mkdir()
        target = outputs / "01. Alpha - Study Guide.md"
        target.write_text("old canonical", encoding="utf-8")
        store, plan, run_id = self.execute()
        os.environ["STUDY_GUIDE_BATCH_TEST_PROMOTION_FAIL_AT"] = "after-install"
        with self.assertRaises(batch.BatchError):
            batch.promote_run(store, run_id)
        self.assertEqual(target.read_text(encoding="utf-8"), "old canonical")
        candidate = Path(store.row("SELECT candidate_path FROM units WHERE run_id = ?", (run_id,))["candidate_path"])
        self.assertTrue(candidate.is_file())
        os.environ.pop("STUDY_GUIDE_BATCH_TEST_PROMOTION_FAIL_AT")

        promotion_id = f"promotion-pending-{int(time.time())}"
        archive_dir = self.root / ".study-guide-batch" / "archive" / promotion_id
        archive = archive_dir / "outputs" / target.name
        archive.parent.mkdir(parents=True)
        os.replace(target, archive)
        unit = store.row("SELECT * FROM units WHERE run_id = ?", (run_id,))
        with store.transaction() as connection:
            connection.execute(
                "INSERT INTO promotions(id, run_id, status, created_at, archive_dir) VALUES(?, ?, 'installing', ?, ?)",
                (promotion_id, run_id, batch.now_iso(), str(archive_dir)),
            )
            connection.execute(
                "INSERT INTO promotion_items(promotion_id, unit_id, ordinal, target_path, archive_path, candidate_path, target_existed, state) "
                "VALUES(?, ?, 1, ?, ?, ?, 1, 'archived')",
                (promotion_id, unit["unit_id"], str(target), str(archive), unit["candidate_path"]),
            )
        self.assertEqual(batch.promote_run(store, run_id), promotion_id)
        self.assertIn(batch.COMPLETION_MARKER, target.read_text(encoding="utf-8"))
        batch.rollback_promotion(store, promotion_id)
        self.assertEqual(target.read_text(encoding="utf-8"), "old canonical")

    def test_ecc_failure_is_nonblocking_warning(self) -> None:
        self.add_lesson(1, "Alpha")
        self.write_config(ecc_mirror=True)
        store, _, approval = self.approved()
        run_id = batch.create_approved_run(store, approval)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        ecc = bin_dir / "ecc"
        ecc.write_text("#!/bin/sh\necho mirror-failed >&2\nexit 7\n", encoding="utf-8")
        ecc.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}):
            batch.mirror_ecc(store, run_id)
        events = (batch.run_directory(store, run_id) / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"source": "ecc"', events)
        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "ready")


if __name__ == "__main__":
    unittest.main(verbosity=2)
