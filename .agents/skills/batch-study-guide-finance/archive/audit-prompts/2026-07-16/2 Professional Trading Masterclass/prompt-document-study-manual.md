# Document-and-Transcript Study Manual Prompt

Transform exactly one primary Microsoft Word document (`.docx`) and one or more explicitly corresponding transcripts from the same lesson into one comprehensive Markdown document-study manual for *Professional Trading Masterclass*.

There is no word-count target, ratio, minimum, maximum, ceiling, or other length constraint for the finished artifact or any substantive section. Use as much depth as complete, source-grounded instruction requires; presentation guidance must never be used to omit supported detail.

The manual must teach the learner how to understand, complete, review, and use the supplied document as part of the course workflow. It must **not** teach the learner how to recreate, format, or rebuild the Word document. This is a document-study task, not a Word build guide.

## Required Inputs and Outputs

The task must identify:

- one primary `.docx` document;
- one or more explicitly corresponding transcripts from the same lesson, listed in part order;
- zero or more explicitly designated prerequisite study chapters or manuals;
- one Markdown output path for the finished document-study manual; and
- Markdown paths under `study chapters/audits` for the document-source audit, transcript-source audit, and manual-generation audit.

Never modify, resave, convert, normalize, repair, or overwrite the source document, transcripts, prerequisite materials, or existing outputs unless the task explicitly authorizes overwriting an output.

If output paths are supplied, write the complete artifacts to those paths and return only a concise completion report listing the paths and all unresolved material or blocking discrepancies. Do not print the manual in chat. If no output paths are supplied, return only the finished manual followed by clearly separated audit appendices in Markdown.

## Mandatory Source Preflight

Before drafting or writing any output:

1. Confirm that exactly one primary `.docx` document is present and readable.
2. Confirm that every transcript belongs to the same lesson and order multipart transcripts by their explicit part numbers.
3. When one transcript part continues a sentence or example from the preceding part, join the seam without duplication or omission.
4. Confirm that every designated prerequisite chapter or manual exists and is readable.
5. Confirm that the document package can be inspected structurally and contains at least one readable paragraph, table, field, or other instructional component.
6. Confirm that all output destinations do not already exist unless overwriting was explicitly authorized.

If the document or every corresponding transcript is missing, unreadable, mismatched, encrypted, corrupted, or unsupported by the available tooling, stop before generation. Report the exact blocker and do not invent a template from narration, substitute a different file, or produce a partial manual.

## Mandatory File Naming and Location

Store the manual in the root `study chapters` folder and all audits in `study chapters/audits`. Do not create a lesson-specific subfolder.

Use these exact patterns:

- Document-study manual: `<lesson-number>DOC. <Topic> - Document Study Manual.md`
- Document-source audit: `document-<lesson-number>-audit-<topic-slug>.md`
- Transcript-source audit: `transcript-<lesson-number>-audit-<topic-slug>.md`
- Manual-generation audit: `document-manual-<lesson-number>-audit-<topic-slug>.md`
- Reusable prompt: `prompt-document-study-manual.md`

Use a readable title-case topic for the manual. Form `<topic-slug>` from the shortest unambiguous topic using lowercase ASCII letters, numbers, and hyphens only. Remove punctuation, collapse spaces to single hyphens, and use no leading or trailing hyphen.

If a supplied output path violates this convention, use the convention-compliant path and report the normalized location. Never rename or relocate a source file.

## Source Authority and Fidelity

Use the Word document and corresponding transcripts as the sole substantive sources.

Apply this precedence:

1. The Word document governs exact headings, labels, tables, fields, placeholders, example entries, section order, visible instructions, and document structure.
2. The transcripts collectively govern the purpose of each section, the evidence that belongs in it, the operating workflow, decision logic, and instructional intent.
3. When the sources conflict, describe the document exactly as it exists, explain only the meaning supported by the transcripts, and record the conflict in the appropriate audits.

Do not browse, add current market data, invent tickers, prices, estimates, catalysts, trade structures, or examples, or silently replace the supplied course process with preferred professional practice. Optional prerequisite materials may establish dependencies and cross-references but may not override the primary sources or introduce new substantive claims.

Correct obvious speech-recognition and punctuation errors only when the intended meaning is clear from the document or nearby transcript context. Record material corrections and unresolved ambiguities in the transcript-source audit.

## Mandatory Document Inspection

Before drafting, inspect the source structurally and visually. Build a source map containing:

- sections, page setup, margins, orientation, page and section breaks;
- headers, footers, page numbers, watermarks, and document properties when relevant;
- every nonblank paragraph, heading-like paragraph, label, instruction, placeholder, and example entry;
- every table, row, column, merged cell, repeated structure, and intentional blank response area;
- paragraph and character styles, fonts, colors, emphasis, spacing, indentation, borders, shading, alignment, and numbering;
- hyperlinks, bookmarks, fields, cross-references, content controls, form fields, and protected regions;
- comments, notes, tracked insertions or deletions, hidden text, and unresolved revisions;
- images, shapes, text boxes, charts, captions, and drawing anchors;
- protection, editing restrictions, macros or embedded objects when present; and
- apparent anomalies, clipping, broken layouts, duplicated text, inconsistent labels, and placeholders whose intended use is unclear.

Render the source document to page images with the approved document renderer and visually inspect every page at readable scale. Confirm page count, table continuation, text visibility, header and footer placement, and the absence of clipping or overlap. Rendering does not prove that comments or tracked-change metadata are absent, so inspect those structurally as well.

If the approved renderer is unavailable because its required rendering engine is not installed, use an available read-only preview or render mechanism when possible and perform the full structural inspection. Record the visual-inspection limitation in the document-source audit and manual. Do not claim that visual inspection passed when it did not.

Before drafting, divide every transcript into logical sections and inventory every substantive instruction, including document fields, evidence sources, calculations, quantitative examples, decision rules, workflow dependencies, warnings, qualifications, completion criteria, and review steps. Give every transcript part and its final third equal attention.

## Field Classification

Classify every instructional document field, placeholder, table area, or response region as one of:

- fixed label or structural text;
- source-supplied example value;
- externally gathered fact or evidence;
- calculated quantitative result;
- qualitative analysis or interpretation;
- discretionary judgment or decision;
- catalyst, timing, risk, or trade-structure entry;
- review, approval, or quality-control item;
- instructional note or placeholder; or
- inert or noninstructional artifact.

Make the classifications explicit in the manual. Never describe a copied fact as a calculated result, an example value as a universal rule, or a discretionary judgment as an objective field.

## Manual Organization

Use exactly one `#` heading for the title. Use `##` for every major section, `###` for subsections, and `####` only for genuine deeper nesting. Place `---` immediately before every `##` section except the first. Do not skip heading levels.

Organize the manual in this order, omitting only genuinely unsupported subsections:

1. **Purpose and How to Use This Manual**
2. **Mastery Map**
3. **Source Boundaries and Document Conventions**
4. **Document Architecture and Information Flow**
5. **Section-by-Section Study Guide**
6. **Complete Field and Evidence Dictionary**
7. **Worked Example Walkthrough**
8. **Operating Workflow and Decision Process**
9. **Completion and Quality-Control Checklist**
10. **Common Errors and Diagnostic Review**
11. **Progressive Practice Exercises**
12. **Mastery Questions and Answers**
13. **Source Notes and Known Limitations**
14. **Glossary and Compact Reference Appendices**

The study-guide layer must explain the existing document and how to use it. Cross-reference related fields rather than duplicating full explanations.

Do not include Word ribbon instructions, formatting procedures, style specifications for recreation, page-layout setup steps, table-building instructions, or a from-scratch reconstruction sequence. Visible formatting may be described only when it communicates meaning or affects how the template should be read or completed.

## Mastery Map

Prioritize three to seven concepts. Identify:

- the document's role in the larger course workflow;
- the fields and evidence categories to understand first;
- calculations or decision procedures to reproduce;
- dependencies between sections;
- review and quality-control disciplines; and
- consequential mistakes to avoid.

The Mastery Map is a priority guide, not a summary.

## Architecture and Information Flow

Explain how information moves through the document from identification and evidence gathering to analysis, decision, timing, structure, and review. Use compact Markdown tables or Mermaid diagrams only when they materially clarify dependencies.

For every section identify:

- exact source heading or label;
- purpose supported by the transcripts;
- required inputs and evidence sources;
- calculations or interpretations performed there;
- upstream dependencies and downstream uses;
- example values and placeholders;
- completion state and review criteria; and
- intentionally deferred or situational fields.

## Complete Field and Evidence Dictionary

Document every instructional field and material blank response area. For each field state:

- exact label and document location;
- classification;
- expected content type, units, date or time basis, and level of detail;
- whether the content is copied, calculated, summarized, interpreted, or decided;
- source or precedent;
- downstream dependents;
- blank behavior and when a blank is intentional;
- source-supplied example content;
- common mistakes and misleading substitutions;
- completion and review criteria; and
- the instructional meaning supported by the transcripts.

Do not omit a field because the source leaves it blank or because its purpose appears obvious.

## Worked Example Walkthrough

Preserve the source document's example as a connected workflow. Explain:

- the starting company, sector, date, and analytical context when supplied;
- quantitative inputs and calculations;
- qualitative evidence and expectations;
- catalysts and timing evidence;
- targets, scenarios, or ranges;
- technical, positioning, risk, or trade-structure considerations when present;
- decisions made, deferred, or intentionally left blank; and
- how each section supports the final documented idea.

Clearly distinguish source example content, calculated results, placeholders, and fields intentionally omitted from the example. Do not fill source blanks with invented information.

When arithmetic derives a result, show:

- **Relationship:** the general symbolic relationship;
- **Document substitution:** the source-specific values; and
- **Expected result:** the document result with units.

Use ordinary prose for currency, dates, percentages, and quantities, escaping every literal dollar sign as `\$` (for example, \$650 million) so Markdown math renderers cannot mistake it for a math delimiter, including inside tables. Write every mathematical expression as raw display LaTeX on its own line delimited by `$$ ... $$`, with the opening and closing delimiters on the same line and a blank line between a stage label such as **Relationship:** and its display-math line, consistent with the study-chapter convention. Never enclose a mathematical expression in backticks or a fenced code block, and never use inline math (`\( ... \)` and single-dollar `$ ... $` delimiters are prohibited); raw `$$ ... $$` renders in both the VS Code Markdown preview and the Google Docs Auto-LaTeX extension. Inside display math, escape every literal ampersand, percent sign, hash, and dollar sign as `\&`, `\%`, `\#`, and `\$` (for example, `\text{R\&D}`, `10\%`); bare `&` and `#` produce KaTeX parse errors and bare `%` silently comments out the rest of the expression. The only unescaped dollar signs in the manual must be the `$$ ... $$` delimiters.

## Operating Workflow and Quality Control

Convert the transcript-supported process into an ordered, repeatable workflow. Preserve conditional branches, dependencies, review loops, and decisions to leave a field blank or defer a conclusion.

The completion checklist must verify at minimum:

- every required document section was reviewed;
- copied facts match their stated source and date;
- calculated values can be reproduced;
- quantitative and qualitative evidence are distinguished;
- targets and scenarios state their assumptions;
- catalysts are specific and time-relevant when required;
- unsupported fields remain blank rather than being guessed;
- conclusions follow from the recorded evidence;
- risk, timing, and trade-structure entries are internally consistent when present; and
- the document is complete enough for a second reader to audit the idea.

Troubleshooting must teach a diagnostic sequence: identify the incomplete or inconsistent field, trace its source and upstream dependencies, reproduce any calculation, compare it with the source example or transcript instruction, and correct only the affected entry.

## Progressive Practice and Mastery

Create source-supported exercises that progress from reading the template to independently completing a blank copy using user-supplied information. Do not instruct the learner to rebuild the document.

Exercises may include:

- classify fixed labels, sourced facts, calculations, interpretations, and decisions;
- trace one conclusion backward to its evidence;
- reproduce a source calculation;
- identify intentionally blank fields in the example;
- diagnose a described incomplete or internally inconsistent submission;
- outline the evidence required for a new idea without inventing the evidence; and
- perform a final quality-control review.

For each exercise provide **Objective**, **Required inputs**, **Actions**, and **Completion evidence**. Use no invented market data.

Mastery questions must cover recall, mechanics, debugging, and judgment. Put `[Recall]`, `[Mechanics]`, `[Debugging]`, or `[Judgment]` at the end of each question heading and place the answer immediately after the question. Use a source-driven count without padding.

## Source Notes and Known Limitations

Place this concise section immediately before the glossary. Summarize only findings that affect interpretation, completion, review, or safe reuse. Separate document limitations, transcript clarifications, intentionally blank or deferred fields, visual-inspection limitations, excluded inert artifacts, and unresolved source ambiguities. Link to the three audit files using relative paths into `audits`. File hashes and inspection-tooling details belong only in the audit files; never place them in the manual body.

## Document-Source Audit

Record only source-document findings, including:

- inconsistent, duplicated, or ambiguous labels;
- unclear or consequential blank placeholders;
- example values that conflict across sections;
- broken fields, links, bookmarks, or references;
- tracked changes, comments, hidden text, or unresolved revisions;
- table, layout, clipping, protection, or rendering anomalies;
- embedded objects or unsupported document features;
- document/transcript conflicts; and
- uncertainty about whether an artifact is intentional.

## Transcript-Source Audit

Record only transcript findings, including:

- probable speech-recognition errors;
- incorrect arithmetic, units, formula descriptions, terminology, or document-field references;
- narration that conflicts with the document;
- ambiguous completion instructions;
- unsupported or incomplete explanations; and
- references to unavailable companion material.

Use `probable ASR error` only when nearby context or document evidence strongly supports a malformed transcription. Use `source-logic or notation error` for coherent but internally incorrect arithmetic, units, symbols, formulas, or field references. Use `unresolved ambiguity` when the evidence cannot establish one interpretation.

## Draft Audit, Targeted Correction, and Final Audit

After writing the draft manual, audit it against the source document, every corresponding transcript, and every instruction in this prompt. Correct every genuine generation discrepancy that the sources can resolve. Use the smallest targeted edit and do not rewrite unaffected sections.

Then perform a final read-only audit. Confirm that:

- every instructional section, field, placeholder, example entry, and substantive transcript workflow maps to the manual;
- all transcript parts, including their final thirds, receive complete coverage of their substantive material;
- classifications distinguish sourced facts, calculations, interpretations, and decisions;
- the worked example remains connected and source-faithful;
- every source blank remains blank unless the source explicitly supplies content;
- calculations and units match the sources;
- no Word reconstruction instructions appear;
- visual and structural document findings are disclosed;
- practice and questions remain source-supported; and
- the output is complete and not truncated.

Record only unresolved findings in the manual-generation audit. Do not approve a manual with a correctable material or blocking discrepancy.

## Audit Entry Schema

Assign stable IDs such as `DOC-33-001`, `TR-33-001`, or `GEN-33-001`. Record:

- **Severity:** Minor, Material, or Blocking.
- **Source:** Document, transcript, or generated manual.
- **Location:** Exact document section/table/field, transcript line or passage, or manual heading/line.
- **Observed evidence:** What the source or output contains.
- **Expected or conflicting evidence:** The prompt requirement or other-source evidence.
- **Impact:** Why it matters for understanding, completion, review, or safe use.
- **Confidence:** High, medium, or low.
- **Suggested targeted correction:** The smallest correction that could resolve it.
- **Disposition:** Retained unchanged, excluded as inert, provisional, retained due to source limitation, or blocked.
- **Resolution status:** Integrated, Closed - no change required, Informational only, Open - source limitation, or Superseded - audit error.
- **Addressed in:** Exact manual heading or `—` when unresolved.

Source audits are log-only and must never alter the document or transcripts. Correct draft-generation discrepancies before finalization whenever the sources support a safe correction. Do not regenerate the entire manual when a narrow edit is sufficient.

## Final Silent Checklist

Before completion, silently confirm:

1. exactly one primary document and only its same-lesson transcripts were used;
2. multipart transcript seams were joined without duplication or omission;
3. no source file was modified;
4. every page was visually inspected or the exact rendering limitation was disclosed;
5. comments, tracked changes, fields, content controls, and protection were checked structurally;
6. every instructional field and consequential blank was documented;
7. the manual teaches understanding, completion, and review—not Word reconstruction;
8. example content is distinguished from universal instruction;
9. every calculation is reproducible from source values;
10. unsupported data was not invented;
11. all three audits were created under `study chapters/audits`;
12. correctable generation defects were fixed before the final audit; and
13. the final output is complete and not truncated.
