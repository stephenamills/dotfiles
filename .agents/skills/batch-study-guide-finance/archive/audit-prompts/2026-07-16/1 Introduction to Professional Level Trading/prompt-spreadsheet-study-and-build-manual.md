# Workbook-and-Transcript Study-and-Build Manual Prompt

Transform either one unique primary Microsoft Excel workbook (`.xlsx`, `.xlsm`, or `.xls`) or one explicitly designated, coherent workbook family, together with one or more explicitly corresponding lesson transcripts, into one comprehensive Markdown study-and-build manual. The manual must both explain the supplied workbook and teach the learner to reproduce its intentional, functional worksheet design from a new blank workbook in the current Microsoft 365 version of Excel for Mac.

There is no word-count target, ratio, minimum, maximum, ceiling, or other length constraint for the finished artifact or any substantive section. Use as much depth as complete, source-grounded instruction and reconstruction require; presentation guidance must never be used to omit supported detail.

Multiple copies of a workbook may be supplied when the course distributes the same file with more than one lesson. Treat byte-identical copies as one unique workbook, record every original path, and use the explicitly corresponding transcripts together to explain the workbook's full instructional role. Do not combine nonidentical workbooks merely because their filenames match.

A workbook family is permitted only when all supplied nonidentical workbooks implement the same lesson-level method across different assets, datasets, timeframes, or summary views. Treat the family as one instructional system. Programmatically inspect every supplied workbook, but teach a complete canonical reconstruction plus every meaningful architectural variation rather than repeating copy-equivalent datasets. The family must be explicitly designated in the task; never infer it from similar filenames.

One or more optional prerequisite chapters or manuals may also be supplied. Use them only to avoid re-teaching established foundations, identify dependencies, create cross-references, and preserve established workbook conventions. Do not use them as substitutes for the primary workbook or corresponding transcripts, and do not import substantive claims from unrelated files or previous conversations.

## Required Inputs and Outputs

The task must identify:

- one unique primary `.xlsx`, `.xlsm`, or `.xls` workbook, with every byte-identical source location identified, or one explicitly designated coherent workbook family;
- one or more explicitly corresponding transcripts, listed in lesson order;
- zero or more explicitly designated prerequisite chapters or manuals;
- one Markdown output path for the finished study-and-build manual; and
- Markdown paths under `study chapters/audits` for the workbook-source audit, transcript-source audit, and generation audit.

Never modify any source workbook copy, transcript, prerequisite chapter, or prerequisite manual. Never overwrite an existing output unless the task explicitly authorizes it.

If output paths are supplied, write the complete artifacts to those exact paths and return only a concise completion report listing the paths and all material or blocking generation discrepancies. Do not print the manual in chat. If no paths are supplied, return only the finished manual and clearly separated audit appendices in Markdown.

## Mandatory Source Preflight

Before drafting or creating any output file:

1. Confirm that exactly one unique primary workbook or one explicitly designated coherent workbook family and at least one explicitly corresponding transcript are present and readable.
2. Compute a SHA-256 hash for every supplied workbook path. Collapse only byte-identical copies into one source instance and record every original path. For nonidentical files, verify that the task explicitly designates a coherent workbook family; do not silently select, merge, or discard them. If same-named copies differ and no coherent family has been explicitly designated, stop and require an explicit choice. Record hashes, duplicate-path evidence, style-record counts, and inspection-tooling details only in the audit files; never place them in the manual body, which may state only learner-relevant boundary facts such as which lessons distribute the workbook and which features are absent.
3. Identify the workbook's actual file format from its contents rather than trusting its filename extension. A file named `.xls` may contain an OOXML workbook package and must be handled according to its contents.
4. Confirm that all transcripts belong to lessons that explicitly use, teach, update, or troubleshoot the primary workbook. Preserve their stated lesson order and do not merge unrelated transcripts.
5. Confirm that every designated prerequisite chapter or manual exists and is readable.
6. Confirm that the workbook contains at least one inspectable worksheet and that formulas, values, styles, and relationships can be extracted with the available spreadsheet tooling.
7. Confirm that the output destinations do not already exist unless overwriting was explicitly authorized.

If the primary workbook or every corresponding transcript is missing, unreadable, mismatched, encrypted, corrupted, or unsupported by the available tooling, stop before generation. Report the exact blocking condition and do not invent a workbook from narration, substitute a different file, or produce a partial manual.

### Legacy `.xls` Inspection Fallback

When the available inspection tooling cannot fully read a genuine legacy BIFF `.xls` file, create a temporary inspection copy only after hashing the source. Open the source read-only in Microsoft Excel and save a converted `.xlsx` copy in a temporary working directory, or use an equivalently faithful format-aware converter. Never overwrite, rename, resave, or alter the original `.xls` file.

Use the temporary copy only to expose formulas, styles, worksheet structures, and renderable content that cannot otherwise be inspected. Compare sheet names, dimensions, representative values, and visible output against the original using a second available reader or preview mechanism. Hash the original again after inspection and confirm it is unchanged. Record the conversion method, validation checks, and any fidelity limitation in the workbook-source audit. If a faithful inspection copy cannot be produced, stop and report a blocker rather than guessing.

## Mandatory File-Naming and Location Convention

Store the study-and-build manual and reusable prompts in the root `study chapters` folder. Store every workbook-source, transcript-source, and manual-generation audit in the shared `study chapters/audits` folder. Do not create lesson-specific subfolders.

Use these exact filename patterns:

- Study-and-build manual: `<lesson-number>WB. <Topic> - Spreadsheet Study and Build Manual.md`
- Workbook-source audit: `spreadsheet-<lesson-number>-audit-<topic-slug>.md`
- Transcript-source audit: `transcript-<lesson-number>-audit-<topic-slug>.md`
- Manual-generation audit: `spreadsheet-manual-<lesson-number>-audit-<topic-slug>.md`
- Reusable prompts: `prompt-<purpose>.md`

Keep the manual topic in readable title case. Form each audit `<topic-slug>` from the shortest unambiguous topic name using lowercase ASCII letters, numbers, and hyphens only. Remove punctuation, replace spaces with single hyphens, and do not include leading or trailing hyphens.

When one byte-identical workbook accompanies multiple lessons, use the earliest lesson that introduces or distributes that workbook as `<lesson-number>`. The lesson number and `WB` prefix are reserved for the primary learning manual so it sorts beside the corresponding numbered study chapter. Never prefix audit files with the lesson number. Their descriptive prefixes and shared `audits` folder keep ancillary evidence away from primary learning assets. Prompt filenames must begin with `prompt-` so prompts sort together.

If a supplied output path violates this convention, put the manual in the root `study chapters` folder or the audit in `study chapters/audits`, using the convention-compliant filename, and report the normalized path in the completion confirmation. Never rename or relocate an existing source file.

## Source Authority and Fidelity

Use the workbook and corresponding transcripts as the sole substantive sources for course, trading, financial, and workbook-specific claims. Do not add live market data, invent prices or tickers, import general trading instruction, or silently substitute preferred professional practice for the supplied course material.

Official Microsoft documentation may be consulted only to verify current Microsoft 365 Excel-for-Mac interface paths, file-format behavior, or formula-auditing mechanics. Do not use it to add spreadsheet features absent from the source or to introduce trading or financial claims. Cite or identify any official documentation that materially affects an instruction, and keep the source workbook authoritative for the design being reconstructed.

Apply this deterministic source precedence:

1. The workbook governs exact cells, formulas, values, sheet architecture, intentional formatting, validation, and visible functional behavior.
2. The corresponding transcripts collectively govern purpose, interpretation, operating workflow, decision logic, and instructional intent.
3. When the sources conflict, teach the workbook implementation for reconstruction, explain only the meaning supported by the transcript, and record the conflict in the appropriate source audits. Never silently reconcile them.

Reconstruct **functional exactness**, not file corruption. Preserve every intentional visible and functional element, but do not teach the learner to recreate unused broken names, accidental formatting far beyond the instructional range, stale metadata, or inert artifacts. Record those items in the workbook-source audit.

Do not “improve,” modernize, simplify, restyle, or correct the workbook in the reconstruction instructions. A suggested correction may appear only in an audit entry for later authorization.

## Mandatory Workbook Inspection

Before drafting, inspect the workbook programmatically and visually. Silently build a source map containing:

- worksheet names, order, visibility, and instructional purpose;
- intentional used ranges and accidental used-range expansion;
- tables, named ranges, external links, comments, notes, drawings, charts, images, protection, hidden rows or columns, freeze panes, filters, print settings, and merged cells;
- VBA projects or macro presence, workbook and worksheet events, form or ActiveX controls, buttons, data connections, queries, refresh behavior, pivot caches, slicers, and custom Ribbon elements when present;
- row heights, column widths, fonts, fills, borders, alignments, number formats, and gridline state;
- data-validation rules and their applied ranges;
- conditional-formatting rules and their applied ranges;
- every nonblank constant and its data type;
- every formula cell, cached result, dependency, and formula family;
- repeated block structures and intentional exceptions;
- formula errors, broken references, circular references, inconsistent formulas, and suspicious hardcodes;
- formulas or formatting whose behavior differs from the narration; and
- the calculation flow from source inputs through intermediate calculations to rankings, summaries, controls, and decision outputs.

Render and visually inspect every worksheet. Inspect targeted ranges at readable scale whenever a whole-sheet render is too large. Do not infer formatting solely from extracted values.

For a large workbook family, render every distinct layout archetype, every summary sheet, every detected formula or formatting outlier, and representative sheets from each workbook; programmatically inspect all remaining copy-equivalent sheets. Identify the canonical reconstruction target before drafting, select the asset, timeframe set, and summary workflow most directly used by the transcript, explain that selection in the manual, and document all meaningful variants without requiring reconstruction of repetitive datasets.

If instructional functionality depends on VBA or workbook events, state that the reconstruction must be saved as `.xlsm` before adding code. Document the exact modules, procedures, event triggers, control assignments, and security implications only when they can be extracted and verified from the source. If macro-bearing content is inert, unavailable, password-protected, or unrelated to the lesson, do not invent code; record the limitation in the workbook-source audit and keep it outside the reconstruction.

Before drafting, divide every corresponding transcript into logical sections and inventory every substantive item, including Excel actions, cells, ranges, formulas, numerical examples, workbook interpretations, procedures, warnings, qualifications, and decision chains. Give every transcript—and the middle and final thirds of each transcript—the same attention as the beginning.

## Workbook Classification

Classify every relevant cell or range as one of:

- label or structural text;
- hardcoded user input;
- copied or externally sourced value;
- formula-derived calculation;
- subtotal or summary output;
- discretionary judgment or planning entry;
- validation or control cell;
- instructional note; or
- inert/noninstructional artifact.

Make these categories visually and verbally explicit in the manual. Never describe a hardcoded judgment value as formula-derived, or a formula output as a user input.

## Manual Organization

Use exactly one `#` heading for the title. Use `##` for every major section, `###` for subsections, and `####` only for genuine deeper nesting. Place `---` immediately before every major `##` section except the first major section. Do not skip heading levels.

Organize the manual in this order, omitting only genuinely unsupported subsections:

1. **Purpose and How to Use This Manual**
2. **Mastery Map**
3. **Source Boundaries and Workbook Conventions**
4. **Workbook Architecture and Dependency Map**
5. **Sheet-by-Sheet Study Guide**
6. **Complete Column and Input/Output Dictionary**
7. **Formula-Archetype Catalog**
8. **Compact Cell-Exhaustive Reconstruction Appendix**
9. **Visible-Style and Range Map**
10. **Build-Completeness Matrix**
11. **Operating Workflow and Decision Process**
12. **Excel for Mac Foundations Used in This Workbook**
13. **Build It from Scratch in Excel for Mac**
14. **Verification Checkpoints and Expected Results**
15. **Excel Troubleshooting and Debugging**
16. **Progressive Practice Exercises**
17. **Mastery Questions and Answers**
18. **Source Notes and Known Limitations**
19. **Glossary and Compact Reference Appendices**

The study-guide layer explains the completed workbook. The build layer teaches its reconstruction. Cross-reference between them instead of duplicating full explanations.

## Mastery Map

Prioritize three to seven concepts. Identify:

- workbook mechanics to understand;
- formulas or reference patterns to reproduce;
- operating procedures to perform;
- Excel skills to master; and
- consequential errors to avoid.

The Mastery Map is a priority guide, not a chapter summary.

## Architecture and Dependency Maps

Describe each sheet’s role and how information flows between sheets and within repeated rows, records, tables, analytical blocks, or templates. Include compact Markdown tables and Mermaid diagrams only when they materially clarify dependencies.

For each sheet, identify:

- intentional working range;
- input regions;
- calculation regions;
- summary outputs;
- repeated blocks;
- discretionary planning areas;
- dependencies on other sheets or external sources; and
- features deliberately deferred to later modules.

## Complete Column and Input/Output Dictionary

Document every instructional column and material off-table area. For each field state:

- header and address;
- classification;
- accepted data type and units;
- whether it is typed, copied, selected, or calculated;
- source or precedent;
- downstream dependents;
- number format and intentional visual treatment;
- validation or conditional formatting;
- blank behavior;
- common mistakes; and
- the business or instructional meaning supported by the transcript.

Do not omit columns merely because they repeat across sheets.

## Formula-Archetype Catalog

Do not mechanically list hundreds of copy-equivalent formulas. Identify every distinct formula archetype and every intentional exception.

For each archetype provide:

- descriptive name;
- exact source formula in literal Excel syntax;
- anchor cell;
- complete applicable cell or range map;
- inputs and outputs;
- dependency direction;
- meaning of each function and operator;
- relative, absolute, and mixed-reference behavior;
- how the formula changes when filled or copied;
- sign convention;
- blank, text, zero, and error behavior;
- representative substitution using workbook values;
- expected result from the workbook;
- edge cases and likely failure modes;
- how to inspect it with **Formulas > Trace Precedents**, **Trace Dependents**, and **Evaluate Formula** in Excel for Mac when applicable; and
- any workbook/transcript conflict, referenced by audit entry ID.

If a formula differs unexpectedly inside an otherwise repeated family, treat it as a separate archetype until the source audit establishes whether it is intentional.

## Compact Cell-Exhaustive Reconstruction Appendix

Provide enough cell-level information to recreate every intentional workbook cell without repeatedly listing copy-equivalent content.

The appendix must account for:

- every populated constant and its exact cell or compact rectangular range;
- every formula cell through an archetype range map or explicit exception entry;
- every intentional blank placeholder whose blank state affects formulas, layout, copying, validation, or later user entry;
- every repeated block's prototype, exact copy destinations, and all deviations from the prototype;
- hidden but instructional cells and ranges;
- discretionary judgment inputs and planning notes;
- subtotal, summary, check, and control cells; and
- intentionally unused cells inside an otherwise active repeated block when their blank state matters.

Use compact matrices, contiguous-range tables, prototype blocks, and exception lists. Do not enumerate thousands of identical cells individually. A learner following the appendix together with the build instructions must not need to inspect the source workbook to discover omitted constants, placeholder states, or formula exceptions.

## Visible-Style and Range Map

Document every distinct visible or functional style role and its complete applied range map, including:

- titles, section headers, column headers, inputs, linked values, formulas, subtotals, totals, checks, notes, and spacer/divider regions;
- fonts, emphasis, fills, borders, alignment, wrapping, and number formats;
- column widths, row heights, hidden rows or columns, merged cells, freeze panes, gridlines, and zoom when instructionally relevant;
- data-validation rules and exact applied ranges;
- conditional-formatting rules, exact applied ranges, and rule precedence when precedence changes the visible result; and
- table, filter, protection, print, or navigation settings that affect use.

Describe visible and functional outcomes rather than internal style IDs. Internal style-record numbers, duplicate differential-format records, and other implementation metadata need not be reproduced when a smaller role-based specification yields the same visible and functional behavior. Record inert or accidental style artifacts in the workbook-source audit instead of teaching them.

## Build-Completeness Matrix

Before the operating-workflow section, include a compact traceability matrix with one row per source component or repeated family. Map each:

- worksheet and intentional range;
- input or constant block;
- formula archetype and exception;
- visible-style role;
- validation or conditional-formatting rule;
- summary, check, or discretionary planning area; and
- substantive transcript workflow

to the exact study-guide explanation, reconstruction step, appendix entry, and verification checkpoint that covers it. Mark no item complete merely because it appears in the source inventory; it must also be teachable and reconstructable from the manual.

## Excel for Mac Teaching Standard

Target the current Microsoft 365 version of Excel for macOS.

The first time an Excel feature appears, include:

1. **Outcome:** What the learner is creating.
2. **Excel action:** Exact Ribbon, menu, dialog, keyboard, or pointer steps.
3. **Entry:** Exact value, formula, range, format code, validation rule, or conditional-format rule.
4. **Why:** The logical purpose and why this Excel feature is appropriate.
5. **Reference behavior:** How Excel will treat references, copying, typing, dates, blanks, and formats.
6. **Verify:** A visible or numerical checkpoint.
7. **Debug:** Common Mac-specific or Excel-specific mistakes and how to diagnose them.

On repeated use, reference the earlier full procedure and state only the new range, formula, or setting.

Explain only the Excel features actually required by the source workbook. Likely topics may include worksheet management, selecting ranges, entering formulas, fill/copy behavior, relative references, tables, data validation, custom number formats, conditional formatting, freeze panes, gridlines, dates and serial values, formula auditing, and calculation settings.

Do not rely on Windows-only shortcuts or menu paths. When a shortcut varies by keyboard layout or macOS settings, give the Ribbon or menu method first.

## From-Scratch Build Sequence

The build must begin with a new blank workbook and proceed in dependency order:

1. Create and order worksheets.
2. Establish workbook conventions and intentional working ranges.
3. Configure widths, heights, panes, gridlines, and structural formatting.
4. Enter headings, labels, notes, and sample source inputs.
5. Apply correct data types, dates, number formats, dropdowns, and validation.
6. Add formulas one archetype at a time.
7. Explain reference movement before any fill or copy operation.
8. Add source-supported subtotals, averages, rankings, summaries, checks, and conditional formatting.
9. Enter all source-supplied sample data, labels, assumptions, records, and intentional placeholders.
10. Validate representative records, calculations, summaries, and control totals.
11. Perform formula-error and visual checks.

Every build step must state the exact sheet and range. Never say only “copy this down,” “format the table,” or “repeat for the other rows.” Specify the destination range, what changes, what remains constant, and how to verify it.

For large repeated regions, provide:

- one fully detailed prototype block;
- exact copy destinations;
- a reference-movement table showing representative formulas before and after copying; and
- a post-copy exception checklist; and
- a compact cell matrix and style-role map that make all constants, intentional blanks, formulas, and exceptions reconstructable without cosmetic repetition.

## Verification Checkpoints

Create checkpoints after every major dependency layer and at final completion. Each checkpoint must include:

- cells or ranges to inspect;
- expected formulas;
- expected displayed values;
- expected number formats or visual states;
- source workbook comparison target;
- likely cause if the check fails; and
- the next upstream cells to inspect.

Include at minimum:

- sheet and intentional-range inventory;
- each distinct input or imported-data class;
- one representative example of every material formula family;
- each repeated row, record, table, or analytical-block prototype and its exceptions;
- every material subtotal, average, ranking, screen, summary, control, or decision output actually present;
- every secondary or supporting worksheet;
- formula-error scan;
- blank, text, zero, error, and missing-data behavior;
- validation, conditional-formatting, filter, sort, connection, macro, or control behavior when present;
- visual comparison of every sheet; and
- checks that no accidental formatting expanded the reconstruction's used range.

## Troubleshooting

Explain workbook-specific failure modes, including when supported:

- a formula displaying as text;
- dates displaying as serial numbers;
- percentages or currency scaled incorrectly;
- incorrect positive/negative signs, percentage scaling, units, ranking direction, or sort order;
- lookup, growth, ratio, average, screen, or valuation formulas referencing the wrong row or column;
- formulas copied into labels, headers, subtotal rows, intentional placeholders, or blank spacer rows;
- relative references drifting during copy/paste;
- blank cells becoming zeros;
- stale calculation results;
- conditional formatting applied to the wrong range;
- validation arrows or allowed values missing;
- totals, averages, filters, rankings, charts, or summaries excluding newly added records or blocks;
- formula errors; and
- accidental used-range expansion.

Troubleshooting must teach a diagnostic sequence, not merely state “check the formula.”

## Progressive Practice and Mastery

Create source-supported exercises that progress from identification to independent reconstruction:

- identify inputs, calculations, and outputs;
- trace one formula family;
- predict reference movement before copying;
- rebuild a representative prototype row, record, table, or analytical block;
- reproduce a secondary summary;
- diagnose seeded conceptual errors described in prose without modifying the source file;
- add a source-consistent blank row, record, or template block using no invented market data; and
- explain the operating workflow from workbook inputs to decisions.

Mastery questions must cover recall, mechanics, debugging, and judgment. Place the label at the end of each question heading, such as `[Recall]`, `[Mechanics]`, `[Debugging]`, or `[Judgment]`. Put each answer immediately after its question. Use a source-driven count without padding or cosmetic variants.

## Mathematics and Formatting

Use ordinary prose formatting for currency, percentages, dates, quantities, cells, and ranges, escaping every literal dollar sign as `\$` (for example, \$1,000) so Markdown math renderers cannot mistake it for a math delimiter, including inside tables. Use backticks for Excel formulas, function names, menu commands, cell addresses, and format codes; text inside backticks is code, is never parsed as math, and is exempt from the `\$` escaping rule, so absolute references such as `=$B$2` remain exactly as Excel writes them.

When a derivation requires a mathematical expression, write it as raw display LaTeX on its own line delimited by `$$ ... $$`, with the opening and closing delimiters on the same line and a blank line between the stage label and the math line. Never enclose a mathematical expression in backticks or a fenced code block, and never use inline math (`\( ... \)` and single-dollar `$ ... $` delimiters are prohibited); raw `$$ ... $$` renders in both the VS Code Markdown preview and the Google Docs Auto-LaTeX extension. Inside display math, escape every literal ampersand, percent sign, hash, and dollar sign as `\&`, `\%`, `\#`, and `\$` (for example, `\text{R\&D}`, `10\%`) — bare `&` and `#` produce KaTeX parse errors and bare `%` silently comments out the rest of the expression — keep notation simple (`\frac{}{}`, `\text{}`, `\times`, arithmetic operators, subscripts), and avoid the `|` character inside display math placed in a Markdown table cell. Write ratios and standalone quoted numbers in plain prose. Outside backticked code, the only unescaped dollar signs in the manual must be the `$$ ... $$` delimiters.

When manually deriving a workbook result, show:

- **Relationship:** the general symbolic relationship;
- **Workbook substitution:** the case-specific cells and values; and
- **Expected result:** the workbook result with units.

Do not convert ratios into percentages or percentages into ratios. Preserve workbook precision unless the transcript explicitly teaches rounding. Do not label harmless rounding as an error.

Use bold sparingly. Bold only the shortest phrase expressing a major rule, warning, distinction, checkpoint result, or consequential Excel behavior. Never bold whole paragraphs, routine labels, every input, or full formulas.

## Source Notes and Known Limitations

Place this concise section immediately before the glossary/reference appendices. Summarize only findings that affect interpretation, reconstruction, debugging, or safe reuse. Separate active workbook limitations, transcript clarifications, intentionally excluded inert artifacts, and unresolved source limitations. Keep detailed evidence in the three audit files and link to them using relative links into the `audits` folder. Preserve useful inline warnings beside affected mechanics; this section is a compact status index, not a duplicate audit dump.

## Workbook-Source Audit

Create or append a module section in the designated workbook-source audit. Record only source-workbook findings, including:

- broken or unused names and references;
- formula errors and inconsistent formula families;
- hardcodes inside calculation regions;
- suspicious blank or zero handling;
- unit, sign, date, or format inconsistencies;
- validation, conditional-formatting, or style anomalies;
- hidden or protected content;
- external links;
- accidental used-range expansion;
- workbook/transcript conflicts affecting cell implementation; and
- uncertainty about whether an artifact is intentional.

## Transcript-Source Audit

Create or append a module section in the designated transcript-source audit. Record only transcript findings, including:

- probable ASR errors;
- incorrect arithmetic, units, formula descriptions, cell addresses, or terminology;
- narration that conflicts with the workbook;
- ambiguous Excel actions;
- unsupported or incomplete explanations; and
- references to unavailable companion material.

Use “probable ASR error” only when nearby context or workbook evidence strongly supports a malformed transcription. Use “source-logic or notation error” for coherent but internally incorrect arithmetic, units, symbols, formulas, or cell references. Use “unresolved ambiguity” when evidence cannot establish one interpretation.

## Draft Audit, Targeted Correction, and Final Audit

After writing the draft manual, audit it against the primary workbook, every corresponding transcript, and every instruction in this prompt. Correct every genuine generation discrepancy that can be resolved from the sources without changing the workbook's intentional design or introducing unsupported content. Use the smallest targeted edit; do not rewrite unaffected sections.

After corrections, perform a final read-only audit. Record only findings that remain unresolved because of a source limitation, irreducible ambiguity, unsupported legacy feature, or blocking tooling failure. The manual is not final merely because a first draft exists.

Verify that:

- every sheet, intentional range, column, off-table area, feature, formula archetype, and substantive transcript workflow maps to a manual section and build step;
- every populated constant and every consequential intentional blank is represented in the compact cell-exhaustive appendix;
- every visible or functional style role has an exact applied range map;
- the build-completeness matrix contains no uncovered or merely inventoried source component;
- exact formulas and cell maps match the workbook;
- formula explanations match Excel behavior;
- workbook/transcript conflicts are disclosed and cross-referenced;
- Excel for Mac steps are executable and introduced fully once;
- every major build stage has source-tied checkpoints;
- no unsupported trading mechanics, data, formulas, or Excel features were invented;
- repeated instructions are cross-referenced rather than bloated;
- the beginning, middle, and final thirds of every corresponding transcript are covered;
- every source worksheet received visual inspection; and
- the output is complete and not truncated.

## Audit Entry Schema

Assign every audit entry a stable ID such as `WB-26-001`, `TR-26-001`, or `GEN-26-001`. Record:

- **Severity:** Minor, Material, or Blocking.
- **Source:** Workbook, transcript, or generated manual.
- **Location:** Exact sheet/cell/range, transcript line or passage, or manual heading/line.
- **Observed evidence:** What the source or output contains.
- **Expected or conflicting evidence:** The prompt requirement or other-source evidence.
- **Impact:** Why it matters for understanding, reconstruction, or workbook operation.
- **Confidence:** High, medium, or low.
- **Suggested targeted correction:** The smallest later correction that could resolve it.
- **Disposition:** Retained unchanged, excluded as inert, provisional, or blocked.
- **Resolution status:** Integrated, Closed — no change required, Informational only, Open — source limitation, or Superseded — audit error.
- **Addressed in:** Exact manual heading or `—` when unresolved.

Source audits are log-only and must never modify a workbook or transcript. Generation discrepancies found in the draft must be corrected before finalization whenever the sources support a safe correction. Do not regenerate the entire manual when a narrow edit is sufficient. Mention unresolved material and blocking generation discrepancies in the completion report; unresolved minor discrepancies may remain only in the audit file.

## Final Silent Checklist

Before completion, silently confirm:

1. exactly one unique primary workbook or one explicitly designated coherent workbook family and all explicitly corresponding transcripts were used, all duplicate workbook paths and hashes were recorded, and every workbook's actual format was identified from its contents;
2. the source files were not modified;
3. every worksheet was programmatically and visually inspected;
4. workbook cells govern reconstruction and transcript narration governs intent;
5. every instructional column, formula archetype, populated constant, consequential intentional blank, and repeated-block exception is documented;
6. the build begins from a blank workbook and is executable in Excel for Mac;
7. functional exactness is preserved through a complete cell appendix and visible-style map without teaching inert corruption;
8. inputs, formulas, outputs, and judgment entries are distinguished;
9. verification checkpoints use source workbook values;
10. all three audit files were created or updated under `study chapters/audits` without silently correcting sources;
11. the manual was not altered after the final read-only audit; and
12. all prerequisite chapters or manuals were used only for established foundations, cross-references, and dependencies; and
13. the Source Notes and Known Limitations section concisely indexes practical findings and links to the audits; and
14. the output files are complete.
