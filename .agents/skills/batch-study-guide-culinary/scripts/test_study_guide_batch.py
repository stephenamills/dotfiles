#!/usr/bin/env python3
"""Acceptance tests for the deterministic study-guide batch supervisor."""

from __future__ import annotations

import argparse
import copy
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
                "CODEX_HOME": str(self.root / "codex-home"),
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
            "max_concurrency": 4,
            "validators": {
                "required_headings": [],
                "require_completion_marker": True,
                "require_mermaid_diagram": True,
                "validate_mermaid_syntax": False,
                "validate_mermaid_render": False,
                "enforce_heading_numbering": False,
            },
            "output_root": "outputs",
            "existing_roots": ["outputs"],
            "course_maps": {
                "enabled": False,
                "output_folder": "0 Course Maps",
                "whole_course": {"enabled": False},
            },
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
    def test_readable_lesson_labels_preserve_section_and_part_order(self) -> None:
        self.assertEqual(
            batch.readable_lesson_label(
                "transcripts/03 - Sauce - 01. How to Make Roux - IV. Making Blond Roux.txt"
            ),
            "01. How to Make Roux — IV. Making Blond Roux",
        )
        self.assertEqual(
            batch.readable_lesson_label(
                "transcripts/21 - Tips - Kitchen Tools - Cutting Boards.txt"
            ),
            "Cutting Boards",
        )

    def test_topic_map_lesson_labels_do_not_repeat_the_chapter_heading(self) -> None:
        self.assertEqual(
            batch.relative_topic_lesson_label(
                "Knives - Selecting a Kitchen Knife Set",
                "01. Selecting a Kitchen Knife Set — III. Japanese Chef's Knife",
            ),
            "III. Japanese Chef's Knife",
        )
        source = (
            "## 2. Ordered Chapter Path\n\n"
            "### [Knives - Selecting a Kitchen Knife Set](<../01.md>)\n\n"
            "- 01. Selecting a Kitchen Knife Set — I. Selecting a Basic Knife Set\n"
            "- 01. Selecting a Kitchen Knife Set — II. European Chef's Knife\n\n"
            "## 3. Technique Architecture and Dependencies\n"
        )
        self.assertEqual(
            batch.shorten_topic_map_catalog_labels(source),
            (
                "## 2. Ordered Chapter Path\n\n"
                "### [Knives - Selecting a Kitchen Knife Set](<../01.md>)\n\n"
                "- I. Selecting a Basic Knife Set\n"
                "- II. European Chef's Knife\n\n"
                "## 3. Technique Architecture and Dependencies\n"
            ),
        )

    def test_source_attribution_ignores_culinary_source_and_repairs_clear_provenance(self) -> None:
        self.assertIsNone(
            batch.SOURCE_ATTRIBUTION.search(
                "Repositions the source of flavor and deepens stock control."
            )
        )
        source = (
            "According to the transcript, keep the liquid below a boil.\n"
            "The lesson states that the vegetables should remain just tender.\n"
            "The course's sequence ends with service.\n"
        ).encode()
        self.assertEqual(
            batch.deterministic_source_attribution_repair(source).decode(),
            (
                "keep the liquid below a boil.\n"
                "the vegetables should remain just tender.\n"
                "the sequence ends with service.\n"
            ),
        )
        self.assertIsNone(
            batch.SOURCE_ATTRIBUTION.search(
                batch.deterministic_source_attribution_repair(source).decode()
            )
        )

    def test_whole_course_compaction_retains_every_numbered_section(self) -> None:
        source = "# Topic Map\n\n" + "".join(
            f"## {index}. Section {index}\n\n" + (f"Detail {index}. " * 500) + "\n\n"
            for index in range(1, 14)
        )
        compacted = batch.compact_whole_course_source(source, max_chars=12_000)
        self.assertLessEqual(len(compacted), 13_000)
        for index in range(1, 14):
            self.assertIn(f"## {index}. Section {index}", compacted)
            self.assertIn(f"Detail {index}.", compacted)

    def test_lesson_catalogs_propagate_to_topic_maps_but_not_whole_course(self) -> None:
        sources = []
        for part, title in (("I", "What is Roux_"), ("II", "Types of Roux")):
            path = (
                self.root
                / "transcripts"
                / f"03 - Sauce - 01. How to Make Roux - {part}. {title}.txt"
            )
            path.write_text(transcript_text(title, 200), encoding="utf-8")
            sources.append(path.relative_to(self.root).as_posix())
        self.write_config(
            lesson_catalog={
                "enabled": True,
                "label_style": "readable",
                "topic_maps": True,
                "whole_course": False,
            },
            course_maps={
                "enabled": True,
                "output_folder": "0 Course Maps",
                "whole_course": {"enabled": False},
            },
            grouping_overrides=[
                {
                    "sources": sources,
                    "title": "Sauce - How to Make Roux",
                    "output": "outputs/03 - Sauce/01 - How to Make Roux.md",
                }
            ],
        )
        plan = batch.create_plan(self.root)
        chapter = next(unit for unit in plan["units"] if unit["kind"] == "transcript")
        topic_map = next(unit for unit in plan["units"] if unit["kind"] == "course_map")
        self.assertEqual(
            chapter["lesson_labels"],
            [
                "01. How to Make Roux — I. What is Roux",
                "01. How to Make Roux — II. Types of Roux",
            ],
        )
        self.assertEqual(
            topic_map["lesson_labels"],
            ["I. What is Roux", "II. Types of Roux"],
        )
        self.assertEqual(topic_map["lesson_catalog_groups"][0]["title"], chapter["title"])

    def test_fresh_generation_omits_predecessor_without_losing_target_fingerprint(self) -> None:
        source = self.add_lesson(1, "Alpha")[0]
        target = self.root / "outputs" / "01. Alpha.md"
        target.parent.mkdir()
        target.write_text("old canonical", encoding="utf-8")
        self.write_config(
            generation={"include_existing_target_context": False},
            grouping_overrides=[
                {
                    "sources": [source.relative_to(self.root).as_posix()],
                    "title": "01. Alpha",
                    "output": "outputs/01. Alpha.md",
                }
            ],
        )
        plan = batch.create_plan(self.root)
        unit = plan["units"][0]
        self.assertIsNotNone(unit["target_hash"])
        stage = self.root / "stage"
        stage.mkdir()
        batch.copy_stage_inputs(self.root, unit, stage)
        self.assertFalse((stage / "predecessor.md").exists())

    def test_lesson_catalog_validator_requires_exact_order_without_links(self) -> None:
        unit = {
            "kind": "transcript",
            "lesson_labels": ["I. Foundation", "II. Application"],
            "lesson_catalog_groups": [],
        }
        candidate = (
            "# Guide\n\n"
            "## 1. Overview\n\nTeaching.\n\n"
            "## 2. Original Video Lessons\n\n"
            "| Part | Video lesson | Watch for |\n|---|---|---|\n"
            "| 1 | I. Foundation | Setup. |\n"
            "| 2 | II. Application | Decision. |\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        validators = {
            **batch.DEFAULT_CONFIG["validators"],
            "require_mermaid_diagram": False,
            "validate_mermaid_syntax": False,
            "forbid_source_attribution": False,
        }
        self.assertTrue(
            batch.validate_unit_candidate_bytes(candidate, validators, unit)[0]
        )
        reordered = candidate.replace(
            b"| 1 | I. Foundation | Setup. |\n| 2 | II. Application | Decision. |",
            b"| 1 | II. Application | Decision. |\n| 2 | I. Foundation | Setup. |",
        )
        valid, category, _ = batch.validate_unit_candidate_bytes(
            reordered, validators, unit
        )
        self.assertFalse(valid)
        self.assertEqual(category, "lesson_catalog")
        duplicated = candidate.replace(
            b"| 2 | II. Application | Decision. |",
            b"| 2 | II. Application | Decision. |\n\nI. Foundation is revisited here.",
        )
        self.assertTrue(
            batch.validate_unit_candidate_bytes(duplicated, validators, unit)[0]
        )

    def test_lesson_catalog_heading_key_accepts_numbering_and_em_dashes(self) -> None:
        self.assertEqual(
            batch.lesson_catalog_heading_key("1. Knives — Tips"),
            batch.lesson_catalog_heading_key("Knives - Tips"),
        )

    def test_heading_numbering_keeps_h2_navigation_and_limits_numbered_h3_to_active_work(self) -> None:
        validators = copy.deepcopy(batch.DEFAULT_CONFIG["validators"])
        validators.update(
            {
                "require_completion_marker": False,
                "require_mermaid_diagram": False,
                "validate_mermaid_syntax": False,
                "validate_mermaid_render": False,
                "forbid_source_attribution": False,
                "enforce_heading_numbering": True,
            }
        )
        valid_guide = (
            "# Guide\n\n"
            "## 1. Market Architecture\n\n"
            "### Regime mechanics\n\nTeaching.\n\n"
            "## 2. Practice Exercises\n\n"
            "### 1. Diagnose the quote\n\nWork.\n"
            "### 2. Calculate the return\n\nWork.\n"
        ).encode()
        self.assertEqual(
            batch.validate_candidate_bytes(valid_guide, validators)[0], True
        )

        unnumbered_h2 = valid_guide.replace(b"## 1. Market Architecture", b"## Market Architecture")
        valid, category, _ = batch.validate_candidate_bytes(unnumbered_h2, validators)
        self.assertFalse(valid)
        self.assertEqual(category, "heading_numbering")

        decorative_h3 = valid_guide.replace(
            b"### Regime mechanics", b"### 1. Regime mechanics"
        )
        valid, category, _ = batch.validate_candidate_bytes(decorative_h3, validators)
        self.assertFalse(valid)
        self.assertEqual(category, "heading_numbering")

        numbered_checklist_step = valid_guide.replace(
            b"### Regime mechanics", b"### 1. Mastery Checklist Step"
        )
        self.assertTrue(
            batch.validate_candidate_bytes(numbered_checklist_step, validators)[0]
        )

    def test_heading_numbering_normalizer_strips_decorative_h3_numbers(self) -> None:
        validators = copy.deepcopy(batch.DEFAULT_CONFIG["validators"])
        validators.update(
            {
                "require_completion_marker": False,
                "require_mermaid_diagram": False,
                "validate_mermaid_syntax": False,
                "validate_mermaid_render": False,
                "forbid_source_attribution": False,
            }
        )
        source = (
            "## 1. Technique\n\n"
            "### 2. Heat management\n\n"
            "Teaching.\n\n"
            "### 3. Sizzle-and-release scenario\n\n"
            "Worked decision.\n\n"
            "## 2. Practice Exercises\n\n"
            "### 1. Diagnose the quote\n\n"
            "Work.\n"
        ).encode()
        normalized = batch.normalize_heading_numbering_bytes(source, validators)
        self.assertIn(b"### Heat management", normalized)
        self.assertIn(b"### 3. Sizzle-and-release scenario", normalized)
        self.assertIn(b"### 1. Diagnose the quote", normalized)
        self.assertTrue(batch.validate_candidate_bytes(normalized, validators)[0])

    def test_heading_numbering_normalizer_preserves_qa_and_checklist_sequences(self) -> None:
        validators = copy.deepcopy(batch.DEFAULT_CONFIG["validators"])
        source = (
            "## 1. Questions and Answers\n\n"
            "### 1. What should you observe?\n\nAnswer.\n\n"
            "## 2. Mastery Checklist\n\n"
            "### 1. Confirm mise en place\n\nCheck.\n"
        ).encode()
        self.assertEqual(
            batch.normalize_heading_numbering_bytes(source, validators), source
        )

    def test_transcript_only_config_and_cli_reject_asset_pathways(self) -> None:
        self.add_lesson(1, "Knife Skills")
        for field, value in (
            ("asset_units", []),
            ("asset_exclude_globs", []),
            ("pdf", {}),
            ("spreadsheet", {}),
            ("workbook", {}),
        ):
            with self.subTest(field=field):
                self.write_config(**{field: value})
                with self.assertRaisesRegex(batch.BatchError, "transcript-only"):
                    batch.create_plan(self.root)
        commands = batch.build_parser()._subparsers._group_actions[0].choices
        self.assertNotIn("list-assets", commands)
        self.assertNotIn("configure-asset", commands)

    def test_course_maps_are_first_class_default_topic_units(self) -> None:
        first = self.add_lesson(1, "Foundation")[0]
        second = self.add_lesson(2, "Macro")[0]
        self.write_config(
            course_maps={
                "enabled": True,
                "output_folder": "0 Course Maps",
                "whole_course": {"enabled": True},
            },
            grouping_overrides=[
                {
                    "sources": [first.relative_to(self.root).as_posix()],
                    "title": "01. Foundation",
                    "output": "outputs/1 Foundation/01. Foundation - Study Chapter.md",
                },
                {
                    "sources": [second.relative_to(self.root).as_posix()],
                    "title": "02. Macro",
                    "output": "outputs/2 Macro/02. Macro - Study Chapter.md",
                },
            ],
        )
        plan = batch.create_plan(self.root)
        maps = [unit for unit in plan["units"] if unit["kind"] == "course_map"]
        self.assertEqual(len(maps), 3)
        self.assertEqual(
            [unit["target"] for unit in maps[:2]],
            [
                "outputs/0 Course Maps/1 Foundation — Course Map.md",
                "outputs/0 Course Maps/2 Macro — Course Map.md",
            ],
        )
        self.assertEqual(maps[0]["dependencies"], ["01-foundation"])
        self.assertEqual(maps[0]["source_types"], {
            "outputs/1 Foundation/01. Foundation - Study Chapter.md": "markdown"
        })
        self.assertIn("default-topic-map-prompt.md", maps[0]["prompt_source"])
        self.assertEqual(
            maps[2]["dependencies"],
            ["course-map-1-foundation", "course-map-2-macro"],
        )
        self.assertEqual(maps[2]["sources"], [maps[0]["target"], maps[1]["target"]])
        self.seed_calibration(plan)
        store = batch.Store(self.root)
        approval = batch.approve_plan(store, plan, self.approval_args())
        run_id = batch.create_approved_run(
            store, approval, selected_unit_ids=["01-foundation"]
        )
        selected = store.rows(
            "SELECT unit_id FROM units WHERE run_id = ? ORDER BY ordinal", (run_id,)
        )
        self.assertEqual(
            [row["unit_id"] for row in selected],
            ["01-foundation", "course-map-1-foundation", "course-map-whole-course"],
        )

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
            "```mermaid\nflowchart LR\n  a --> b\n```\n\n"
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
        (self.root / "transcripts" / "notes.bin").write_bytes(b"pdf")
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
        self.assertTrue(any(item["path"].endswith("notes.bin") for item in plan["exclusions"]))

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

    def test_culinary_filename_order_preserves_roman_lesson_sequence(self) -> None:
        names = (
            "03 - Sauce - 01. How to Make Roux - IX. Recovery.txt",
            "03 - Sauce - 01. How to Make Roux - V. Brown Roux.txt",
            "03 - Sauce - 01. How to Make Roux - I. Purpose.txt",
            "03 - Sauce - 01. How to Make Roux - II. Mise en Place.txt",
        )
        for name in names:
            (self.root / "transcripts" / name).write_text(
                transcript_text("roux", 100), encoding="utf-8"
            )
        ordered = [names[2], names[3], names[1], names[0]]
        self.write_config(
            grouping_overrides=[
                {
                    "sources": [f"transcripts/{name}" for name in ordered],
                    "title": "Sauce - How to Make Roux",
                    "output": "outputs/03 - Sauce/01 - How to Make Roux.md",
                }
            ]
        )
        unit = batch.create_plan(self.root)["units"][0]
        self.assertEqual(
            [Path(source).name for source in unit["sources"]],
            ordered,
        )

    def test_short_transcript_and_short_candidate_have_no_length_blocker(self) -> None:
        self.add_lesson(1, "Alpha", words=5)
        plan = batch.create_plan(self.root)
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.assertEqual(plan["units"][0]["flags"], [])
        valid, category, detail = batch.validate_candidate_bytes(
            (
                "Complete.\n\n```mermaid\nflowchart LR\n  source --> mastery\n```\n\n"
                f"{batch.COMPLETION_MARKER}\n"
            ).encode(),
            plan["config"]["validators"],
        )
        self.assertTrue(valid, detail)
        self.assertEqual(category, "success")





    def test_mermaid_validation_rejects_missing_d2_and_invalid_diagrams(self) -> None:
        validators = {
            **batch.DEFAULT_CONFIG["validators"],
            "validate_mermaid_render": False,
        }
        missing = f"# Guide\n\nNo diagram.\n\n{batch.COMPLETION_MARKER}\n".encode()
        valid, category, detail = batch.validate_candidate_bytes(missing, validators)
        self.assertFalse(valid)
        self.assertEqual(category, "diagram_missing")
        self.assertIn("lacks a fenced Mermaid", detail)

        d2 = (
            "# Guide\n\n```d2\na -> b\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        valid, category, detail = batch.validate_candidate_bytes(d2, validators)
        self.assertFalse(valid)
        self.assertEqual(category, "diagram_d2")
        self.assertIn("prohibited fenced D2", detail)

        invalid = (
            "# Guide\n\n```mermaid\nflowchart LR\n  A -->\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        valid, category, detail = batch.validate_candidate_bytes(invalid, validators)
        self.assertFalse(valid)
        self.assertEqual(category, "diagram_invalid")
        self.assertIn("Mermaid diagram 1 is invalid", detail)

    def test_mermaid_render_validation_is_disabled_by_default(self) -> None:
        self.assertFalse(batch.DEFAULT_CONFIG["validators"]["validate_mermaid_render"])

    @unittest.skipUnless(
        os.environ.get("STUDY_GUIDE_BATCH_RUN_RENDER_TESTS") == "1",
        "set STUDY_GUIDE_BATCH_RUN_RENDER_TESTS=1 to run Chromium-backed Mermaid integration tests",
    )
    def test_mermaid_parser_and_desktop_render_gate(self) -> None:
        source = (
            "flowchart LR\n"
            '  question["What governs the decision?"] --> input["Input"]\n'
            '  input --> transform["Transform"]\n'
            '  transform --> output["Output"]\n'
            '  output -. "feedback" .-> input\n'
        )
        syntax_valid, syntax_detail = batch.validate_mermaid_syntax_blocks([source])
        render_valid, render_detail = batch.validate_mermaid_render_blocks(
            [source], batch.MERMAID_RENDER_VIEWPORTS
        )
        self.assertTrue(syntax_valid, syntax_detail)
        self.assertTrue(render_valid, render_detail)
        self.assertIn("1728x1117px", render_detail)

    def test_mermaid_h2_coverage_reports_the_exact_uncovered_section(self) -> None:
        text = (
            "# Map\n\n"
            "## Ordered Chapter Path\n\n"
            "```mermaid\nflowchart LR\n  A --> B\n```\n\n"
            "## Architecture and Dependencies\n\nNo diagram yet.\n"
        )
        valid, detail = batch.validate_mermaid_h2_coverage(
            text,
            ["Ordered Chapter Path", "Architecture and Dependencies"],
        )
        self.assertFalse(valid)
        self.assertIn("Architecture and Dependencies", detail)
        self.assertNotIn("Ordered Chapter Path,", detail)

    def test_removed_d2_validator_keys_are_rejected(self) -> None:
        self.write_config(
            validators={
                "required_headings": [],
                "require_completion_marker": True,
                "require_d2_diagram": True,
            }
        )
        with self.assertRaisesRegex(batch.BatchError, "removed validator key"):
            batch.load_config(self.root)

    def test_validation_rejects_source_attribution_phrases(self) -> None:
        candidate = (
            "# Guide\n\nThe PDF states the formula.\n\n"
            "```mermaid\nflowchart LR\n  input --> result\n```\n\n"
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
            "```mermaid\nflowchart LR\n  input --> result\n```\n\n"
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

    def test_diagram_repair_changes_only_the_targeted_mermaid_source(self) -> None:
        original = (
            "# Guide\n\nKeep this prose byte-for-byte — including Unicode.\n\n"
            "```mermaid\nflowchart LR\n  concept -->\n```\n\n"
            "## 1. Review\n\nKeep this too.\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        validators = {
            **batch.DEFAULT_CONFIG["validators"],
            "validate_mermaid_render": False,
        }
        valid, category, detail = batch.validate_candidate_bytes(
            original, validators
        )
        self.assertFalse(valid)
        self.assertEqual(category, "diagram_invalid")
        repaired_source = (
            "flowchart LR\n"
            '  question["What creates mastery?"] --> concept["Repaired concept"]\n'
            '  concept --> mastery["Mastery"]\n'
        )
        repaired = batch.apply_diagram_repair(original, category, detail, repaired_source)

        old_text = original.decode()
        new_text = repaired.decode()
        old_match = batch.MERMAID_BLOCK.search(old_text)
        new_match = batch.MERMAID_BLOCK.search(new_text)
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
            repaired, validators
        )
        self.assertTrue(valid)
        self.assertEqual(category, "success")

    def test_diagram_repair_converts_only_a_prohibited_d2_fence(self) -> None:
        original = (
            "# Guide\n\nPreserve this prose exactly.\n\n"
            "```d2\ninput -> result\n```\n\n"
            f"{batch.COMPLETION_MARKER}\n"
        ).encode()
        validators = {
            **batch.DEFAULT_CONFIG["validators"],
            "validate_mermaid_render": False,
        }
        valid, category, detail = batch.validate_candidate_bytes(original, validators)
        self.assertFalse(valid)
        self.assertEqual(category, "diagram_d2")
        repaired = batch.apply_diagram_repair(
            original,
            category,
            detail,
            'flowchart LR\n  input["Input"] --> result["Result"]',
        )
        self.assertIn(b"```mermaid", repaired)
        self.assertNotIn(b"```d2", repaired)
        self.assertEqual(
            batch.D2_FENCE.sub("", original.decode()),
            batch.MERMAID_BLOCK.sub("", repaired.decode()),
        )

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
            "```mermaid\n"
            "flowchart LR\n"
            '  material["Course material"] --> concepts["Key concepts"]\n'
            '  concepts --> practice["Guided practice"]\n'
            '  practice --> mastery["Demonstrated mastery"]\n'
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
        self.assertIn("flowchart LR", installed)
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
        # Both selected units share one V2 dispatcher wave.
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
    def test_whole_course_map_runs_after_topic_maps_and_uses_only_their_candidates(self) -> None:
        first = self.add_lesson(1, "Foundation")[0]
        second = self.add_lesson(2, "Macro")[0]
        self.write_config(
            course_maps={
                "enabled": True,
                "output_folder": "0 Course Maps",
                "whole_course": {"enabled": True},
            },
            grouping_overrides=[
                {
                    "sources": [first.relative_to(self.root).as_posix()],
                    "title": "01. Foundation",
                    "output": "outputs/1 Foundation/01. Foundation - Study Chapter.md",
                },
                {
                    "sources": [second.relative_to(self.root).as_posix()],
                    "title": "02. Macro",
                    "output": "outputs/2 Macro/02. Macro - Study Chapter.md",
                },
            ],
        )
        store, plan, run_id = self.execute(max_invocations=20, max_tokens=200000)
        self.assertEqual(batch.export_status(store, run_id)["status"], "completed")
        whole = next(unit for unit in plan["units"] if unit["id"] == "course-map-whole-course")
        topic_maps = [
            unit for unit in plan["units"]
            if unit["kind"] == "course_map" and unit["id"] != whole["id"]
        ]
        self.assertEqual(whole["sources"], [unit["target"] for unit in topic_maps])
        self.assertEqual(whole["dependencies"], [unit["id"] for unit in topic_maps])
        worker_units = [call["unit_id"] for call in self.fake_state()["worker_calls"]]
        self.assertEqual(worker_units[-1], whole["id"])
        self.assertTrue(all(worker_units.index(unit["id"]) < len(worker_units) - 1 for unit in topic_maps))
        whole_row = store.row(
            "SELECT * FROM units WHERE run_id = ? AND unit_id = ?",
            (run_id, whole["id"]),
        )
        whole_text = Path(whole_row["candidate_path"]).read_text(encoding="utf-8")
        valid, category, detail = batch.validate_unit_candidate_bytes(
            whole_text.encode(), plan["config"]["validators"], whole
        )
        self.assertTrue(valid, (category, detail))

    def test_course_map_runs_after_approved_guides_and_promotes_atomically(self) -> None:
        first = self.add_lesson(1, "Foundation")[0]
        second = self.add_lesson(2, "Regimes")[0]
        self.write_config(
            course_maps={
                "enabled": True,
                "output_folder": "0 Course Maps",
                "whole_course": {"enabled": False},
            },
            grouping_overrides=[
                {
                    "sources": [first.relative_to(self.root).as_posix()],
                    "title": "01. Foundation",
                    "output": "outputs/1 Foundation/01. Foundation - Study Chapter.md",
                },
                {
                    "sources": [second.relative_to(self.root).as_posix()],
                    "title": "02. Regimes",
                    "output": "outputs/1 Foundation/02. Regimes - Study Chapter.md",
                },
            ],
        )
        store, plan, run_id = self.execute(max_invocations=12, max_tokens=100000)
        self.assertEqual(batch.export_status(store, run_id)["status"], "completed")
        planned_map = next(unit for unit in plan["units"] if unit["kind"] == "course_map")
        rows = store.rows("SELECT * FROM units WHERE run_id = ? ORDER BY ordinal", (run_id,))
        self.assertEqual([row["state"] for row in rows], ["approved", "approved", "approved"])
        worker_units = [call["unit_id"] for call in self.fake_state()["worker_calls"]]
        self.assertEqual(worker_units[-1], planned_map["id"])
        map_row = next(row for row in rows if row["unit_id"] == planned_map["id"])
        map_text = Path(map_row["candidate_path"]).read_text(encoding="utf-8")
        valid, category, detail = batch.validate_unit_candidate_bytes(
            map_text.encode(), plan["config"]["validators"], planned_map
        )
        self.assertTrue(valid, (category, detail))
        promotion_id = batch.promote_run(store, run_id)
        promoted = store.rows(
            "SELECT target_path FROM promotion_items WHERE promotion_id = ? ORDER BY ordinal",
            (promotion_id,),
        )
        self.assertEqual(len(promoted), 3)
        self.assertTrue((self.root / planned_map["target"]).is_file())

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
            v2_config = next(arg for arg in argv if arg.startswith("features.multi_agent_v2={"))
            self.assertIn("--enable", argv)
            self.assertEqual(argv[argv.index("--enable") + 1], "multi_agent_v2")
            self.assertIn("max_concurrent_threads_per_session=2", v2_config)
            self.assertIn("hide_spawn_agent_metadata=false", v2_config)
            self.assertIn('tool_namespace="agents"', v2_config)
            self.assertIn("expose_spawn_agent_model_overrides=false", v2_config)
            self.assertIn("non_code_mode_only=false", v2_config)
            self.assertNotIn("features.enable_fanout=true", argv)
            self.assertFalse(any(argument.startswith("agents.max_") for argument in argv))
            self.assertIn('default_permissions=":danger-full-access"', argv)
            self.assertTrue(any(arg.startswith("sqlite_home=") for arg in argv), argv)
            self.assertTrue(
                any(
                    arg.startswith("skills.config=")
                    and "batch-study-guide-culinary" in arg
                    for arg in argv
                ),
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

    def test_prohibited_d2_repairs_only_diagram_without_regenerating_guide(self) -> None:
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

    def test_invalid_mermaid_repair_retries_a_malformed_first_repair(self) -> None:
        self.write_config(
            validators={
                "required_headings": [],
                "require_completion_marker": True,
                "require_mermaid_diagram": True,
                "validate_mermaid_syntax": True,
                "validate_mermaid_render": False,
                "enforce_heading_numbering": False,
            }
        )
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "mermaid_retry"

        store, _, run_id = self.execute()

        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
        state = self.fake_state()
        self.assertEqual(state["stages"]["generation"], 1)
        self.assertEqual(state["stages"]["diagram_repair"], 2)

    def test_global_deadline_kills_descendant_and_policy_activity_fails(self) -> None:
        self.add_lesson(1, "Alpha")
        pid_file = self.root / "descendant.pid"
        heartbeat_file = self.root / "descendant-heartbeat.txt"
        os.environ["FAKE_CODEX_SCENARIO"] = "timeout"
        os.environ["FAKE_CODEX_DESCENDANT_PID"] = str(pid_file)
        os.environ["FAKE_CODEX_DESCENDANT_HEARTBEAT"] = str(heartbeat_file)
        store, _, run_id = self.execute(
            deadline_hours=0.001, timeout_minutes=0.005, transient_retries=0
        )
        self.assertEqual(
            store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"],
            "checkpointed",
        )
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
        self.write_config(max_concurrency=3)
        store, plan, approval = self.approved(max_invocations=1, max_tokens=10000)
        self.assertEqual(approval["contract"]["workers"], 3)
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
                workers=33,
                deadline_hours=1,
                timeout_minutes=1,
                max_invocations=10,
                max_tokens=10000,
                transient_retries=0,
            )
        parsed = batch.build_parser().parse_args(["generate-all", "--max-concurrency", "2"])
        self.assertEqual(parsed.max_concurrency, 2)
        self.assertIsNone(batch.build_parser().parse_args(["generate-all"]).max_concurrency)
        self.write_config(max_concurrency=33)
        with self.assertRaisesRegex(batch.BatchError, "max_concurrency"):
            batch.load_config(self.root)
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

    def test_nine_units_dispatch_as_four_four_one_v2_waves(self) -> None:
        for number in range(1, 10):
            self.add_lesson(number, f"Lesson {number}")

        store, _, run_id = self.execute()

        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
        state = self.fake_state()
        self.assertEqual([wave["size"] for wave in state["waves"]], [4, 4, 1])
        self.assertTrue(all(wave["v2_enabled"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_thread_limit"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_spawn_metadata_visible"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_agents_namespace"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_no_model_overrides"] for wave in state["waves"]))
        self.assertTrue(all(wave["v2_direct_tool_access"] for wave in state["waves"]))
        self.assertTrue(all(wave["legacy_fanout_absent"] for wave in state["waves"]))
        self.assertTrue(all(wave["legacy_agent_limits_absent"] for wave in state["waves"]))
        self.assertTrue(all(wave["user_config_enabled"] for wave in state["waves"]))
        self.assertTrue(all(wave["legacy_sandbox_absent"] for wave in state["waves"]))
        self.assertTrue(all(wave["nested_sandbox_disabled"] for wave in state["waves"]))
        self.assertEqual(state["workers_total"], 9)

    def test_legacy_user_agent_cap_uses_isolated_config(self) -> None:
        self.add_lesson(1, "Alpha")

        with mock.patch.object(batch, "legacy_agent_max_threads_configured", return_value=True):
            store, _, run_id = self.execute()

        self.assertEqual(store.row("SELECT status FROM runs WHERE id = ?", (run_id,))["status"], "completed")
        self.assertTrue(all("--ignore-user-config" in call["argv"] for call in self.fake_state()["calls"]))

    def test_missing_and_malformed_artifacts_retry_without_legacy_fallback(self) -> None:
        for scenario, first_category in (
            ("missing_candidate", "missing_candidate"),
            ("malformed_artifact", "malformed_artifact"),
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

    def test_v2_capability_unavailable_fails_clearly_without_fallback(self) -> None:
        self.add_lesson(1, "Alpha")
        os.environ["FAKE_CODEX_SCENARIO"] = "capability_unavailable"

        store, _, run_id = self.execute()

        run = store.row("SELECT * FROM runs WHERE id = ?", (run_id,))
        self.assertEqual(run["status"], "checkpointed")
        self.assertIn("Multi Agent V2 capability unavailable", run["stop_reason"])
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
