# PDF-and-Transcript Study Companion Prompt

Transform exactly one primary PDF and one or more explicitly corresponding lesson transcripts into one comprehensive Markdown study manual for *Introduction to Professional Level Trading*.

There is no word-count target, ratio, minimum, maximum, ceiling, or other length constraint for the finished artifact or any substantive section. Use as much depth as complete, source-grounded instruction requires; presentation guidance must never be used to omit supported detail.

The manual must teach the learner how to understand, interpret, complete, review, and use the supplied PDF as part of the course workflow. It must not invent a reconstruction procedure unless the PDF and transcript explicitly teach one.

## Required inputs and outputs

Identify exactly one primary PDF, the ordered corresponding transcript set, optional prerequisite manuals, one Markdown manual output, and separate PDF-source, transcript-source, and generation-audit paths under `study chapters/audits`.

Use these output conventions:

- Study companion: `<lesson-number>PDF. <Topic> - Study Companion.md`
- PDF-source audit: `pdf-<lesson-number>-audit-<topic-slug>.md`
- Transcript-source audit: `transcript-<lesson-number>-audit-<topic-slug>.md`
- Generation audit: `pdf-companion-<lesson-number>-generation-audit-<topic-slug>.md`

Never modify source PDFs, transcripts, prerequisites, or existing outputs unless overwriting is explicitly authorized. If a required source is missing, unreadable, encrypted, corrupted, mismatched, or unsupported, stop before drafting and record the exact blocker.

## Source authority and inspection

Use the PDF as the authority for exact visible headings, labels, tables, figures, page order, captions, annotations, and document structure. Use the transcripts for purpose, interpretation, workflow, decision logic, and instructional intent. Record conflicts in the appropriate audits rather than silently reconciling them.

Inspect the PDF structurally and visually before drafting. Record page count, metadata when relevant, text extraction quality, headings, tables, figures, charts, formulas, footnotes, hyperlinks, annotations, bookmarks, repeated headers or footers, and apparent clipping or missing content. Render and inspect every page when the available tooling permits it. If visual inspection is limited, state that limitation in the PDF-source audit and manual; do not claim it passed.

Divide every transcript into logical sections and inventory all substantive concepts, definitions, distinctions, causal reasoning, examples, calculations, procedures, warnings, qualifications, and review criteria. Give the middle and final thirds equal attention.

Use only the PDF, corresponding transcripts, and explicitly designated prerequisites. Do not browse, add current market data, invent tickers, prices, calculations, examples, or preferred professional practice.

## Manual requirements

Write a standalone, authoritative study manual with exactly one H1 and H2–H4 headings without skipped levels. Explain what each relevant PDF section contains, what it means, how it fits the course workflow, how to interpret its tables or figures, and what decisions or actions it supports when those points are established by the sources.

Preserve every material example, number, unit, formula, qualification, warning, and sequence. Separate quoted PDF facts from transcript explanations. Do not turn a historical example into a current recommendation.

Include, when supported:

- Chapter Summary.
- Mastery Map.
- Source Boundaries and PDF Architecture.
- Page-by-page or section-by-section study guide.
- Interpretation of tables, charts, figures, and formulas.
- Source-driven practice exercises with objective, required inputs, actions, and completion evidence.
- Conceptual and calculation questions with answers.
- Glossary.

Use the same quantitative and Markdown discipline as the transcript study-chapter prompt: preserve stated precision, keep ROI percentages separate from reward-to-risk ratios, show Formula → Substitution → Final result for newly derived arithmetic, use raw `$$ ... $$` display math only, escape literal dollar signs as `\$`, and do not invent missing inputs.

## Final audit

After drafting, audit the manual against every page and the ordered transcript set. Correct source-resolvable omissions or formatting errors. Record only unresolved source limitations, irreducible ambiguities, or tooling failures in the three designated audits. Do not approve a missing, truncated, corrupted, wrong-source, or otherwise unusable manual.

When output paths are supplied, write the artifacts to those paths and return only a concise completion report listing them and any material or blocking discrepancies.

## Audit entry schema

Assign every audit entry a stable ID such as `PDF-6-001`, `TR-6-001`, or `PDFGEN-6-001`. Record:

- **Severity:** Minor, Material, or Blocking.
- **Source:** PDF, transcript, or generated companion.
- **Location:** Exact page, table, figure, transcript passage, or companion heading/line.
- **Observed evidence:** What the source or output contains.
- **Expected or conflicting evidence:** The prompt requirement or other-source evidence.
- **Impact:** Why it matters for interpretation, completion, review, or safe reuse.
- **Confidence:** High, medium, or low.
- **Suggested targeted correction:** The smallest correction that could resolve it.
- **Disposition:** Retained unchanged, provisional, informational only, or blocked.
- **Resolution status:** Integrated, Closed — no change required, Open — source limitation, or Blocked.
- **Addressed in:** Exact companion heading or `—` when unresolved.

Source audits are log-only and must never modify the PDF or transcripts. Correct draft-generation discrepancies before finalization whenever the sources support a safe correction. Do not regenerate the entire companion when a narrow edit is sufficient. Record only unresolved findings in the final generation audit.
