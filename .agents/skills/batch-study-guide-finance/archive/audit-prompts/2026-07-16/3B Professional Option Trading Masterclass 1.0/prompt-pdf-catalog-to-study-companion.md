# Options-Strategy Catalog Study-Companion Prompt

Transform the two supplied master strategy-catalog PDFs and the designated strategy-classification workbook into one comprehensive, technically precise Markdown study companion for *Professional Option Trading Masterclass 1.0*. Cover all 53 strategies represented by the sources. This is a full instructional reference transformation, not a short summary.

There is no word-count target, ratio, minimum, maximum, ceiling, or other length constraint for the finished artifact or any substantive section. Use as much depth as complete, source-grounded instruction requires; presentation guidance must never be used to omit supported detail.

If an output path is supplied, write the complete companion there and return only a concise completion confirmation and path. Never modify either PDF or the workbook, and never overwrite an existing output unless explicitly authorized. If no output path is supplied, return only the finished Markdown companion.

## Source Fidelity and Inspection

Use the two PDFs and workbook as the sole substantive sources. The workbook governs the 53-strategy inventory and classification fields; the PDFs govern formal constructions, formulas, risk/reward descriptions, warnings, and examples. Do not browse, externally fact-check, add current market data, invent examples, or import general domain knowledge. Preserve source conclusions, qualifications, formulas, numerical values, tables, warnings, and examples.

Before drafting:

1. identify both document titles, page counts, page order, and visible section hierarchies;
2. extract the text while also rendering and visually inspecting every page of both PDFs;
3. inventory every substantive paragraph, definition, distinction, formula, table, chart, diagram, caption, example, warning, and source limitation;
4. distinguish document text from information communicated only through graphics or tables; and
5. inspect every workbook sheet and build a complete 53-strategy classification map; and
6. build page-by-page and strategy-by-strategy coverage maps and verify both after drafting.

Do not infer precise values from a chart when the PDF does not label them. Describe the chart-supported relationship and preserve visibly labelled values. If text extraction and the visible page conflict, use the visible page and record the conflict in the PDF-source audit.

Correct only high-confidence typographical, arithmetic, unit, or notation errors demonstrable from the PDF's own content and elementary arithmetic. Teach the supported correction and add one concise inline `**Accuracy note — source-logic or notation error:**`. For unresolved ambiguity, preserve only the supported meaning and add `**Accuracy note — unresolved ambiguity:**`. Do not identify an error merely because the source is old or uses an unfamiliar convention.

## Organization

Use exactly one `#` heading for the title. Use `##` for major sections and `###` for subsections and individual questions. Use `####` only for genuine deeper nesting. Place `---` before every `##` heading except the first `## Chapter Summary`. Never skip heading levels.

Organize the companion as follows, omitting only unsupported subsections:

1. `## Chapter Summary`
2. `## Mastery Map`
3. a complete 53-strategy classification and navigation matrix
4. major instructional sections following the catalogs' logical progression, separated into useful and not-useful strategies
5. `## Tables, Figures, and Worked Examples`
6. `## Practice Bridge` when the sources support actionable calculations, interpretation, or risk-management mechanics
7. `## Conceptual Questions and Answers`
8. `## Calculation Questions and Answers` when quantitative relationships exist
9. `## Source Notes and Known Limitations`
10. `## Glossary`

The Mastery Map must prioritize three to seven concepts, formulas, causal mechanics, procedures, and consequential mistakes. It must not summarize the entire document.

Explain charts and tables in prose, including what is encoded, how to read it, what comparisons are justified, and what conclusion the PDF draws. Do not reproduce large tables mechanically when a compact reference table plus interpretation retains all instructional meaning. Preserve every materially distinct row, threshold, or category needed for later use.

Use bold sparingly. Bold only the shortest phrase expressing a major rule, warning, distinction, or consequential result. Use zero to two instructional highlights per major section. Never bold whole paragraphs, routine definitions, mathematical blocks, or the same idea twice.

## Mathematics and Numerical Fidelity

Ordinary currency, dates, quantities, and percentages in prose remain normal text, such as $6.80, 100 shares, and 25.5%.

Equations, arithmetic operations, inequalities, ratios, substitutions, and derived relationships must use Google Docs Auto-LaTeX-compatible double-dollar delimiters. Never use backticked or single-dollar mathematics. Use inline or table math as:

$$0.2549:1$$

Use display math as:

$$
\text{Monthly Volatility} = \frac{\text{Annual Volatility}}{\sqrt{12}}
$$

Do not use fenced code blocks. Ordinary currency remains a normal single dollar sign because mathematics always uses double-dollar delimiters.

Whenever arithmetic is performed to derive a result, show:

Formula:

$$
\text{Result} = \text{General symbolic relationship}
$$

Substitution:

$$
\text{Result} = \text{Source values substituted}
$$

Final result:

$$
\text{Result} = \text{Derived value}
$$

Do not invent missing inputs. Preserve source precision and distinguish quoted values from newly derived values.

## Questions and Practice

Create source-driven questions covering every strategy family, classification filter, important distinction, warning, interpretation rule, and worked-example lesson. Use no fixed minimum or maximum; stop when the distinct relationships and decisions are exhausted. Never create cosmetic variants merely to increase the count.

Place exactly one tag at the end of each question heading:

- `[Recall]` for definitions and stated rules;
- `[Mechanics]` for calculations, procedures, and structures; or
- `[Judgment]` for interpretation, risk, and scenario decisions.

Place each complete answer immediately after its question. Calculation questions must be source-driven, nonduplicative, and use Formula → Substitution → Final result.

Include a Practice Bridge only when the sources support meaningful practice. Every exercise must state its objective, required source or user-supplied inputs, actions, and observable completion evidence. Do not invent market data or imply readiness to risk live capital.

## Auditing

Create or update the supplied PDF/workbook-source and companion-generation audit paths under `study chapters/audits`. Use stable IDs such as `PDF-3-001`, `WB-3-001`, and `PDFGEN-3-001`. Each genuine finding records severity, page, workbook range, or generated heading; evidence; impact; confidence; suggested targeted correction; disposition; resolution status; and where it is addressed.

Audits are log-only. Do not regenerate or automatically patch a completed companion because of an audit finding. Summarize only consequential findings in `Source Notes and Known Limitations` and link to the detailed audits.

## Final Check

Confirm that all 53 workbook strategies, every PDF page, and every substantive visual are covered; all formulas and numerical relationships are preserved; no external claims or invented values were introduced; headings, bolding, question labels, and double-dollar Auto-LaTeX follow the required format; the output is complete; and all three sources are unchanged.
