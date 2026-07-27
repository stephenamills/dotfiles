# Lesson-Transcript Study-Chapter Prompt

Transform the ordered transcript input for exactly one lesson into a comprehensive, technically precise, standalone study chapter for *Introduction to Professional Level Trading*. This is a full instructional transformation, not a summary or outline.

The lesson input may contain either one transcript file or multiple transcript files explicitly identified as consecutive parts of the same lesson. When multiple parts are supplied, process them in the stated part order as one continuous source, repair only the mechanical seam between parts, and do not duplicate or omit text that crosses the seam. If multiple files are not clearly parts of the same lesson, stop and report the ambiguity rather than combining unrelated material.

Treat the complete ordered lesson transcript set as sufficient for this task. Do not request, wait for, or claim that you need companion materials—even if the lesson refers to them. Do not combine it with transcripts from earlier messages, other lessons, or other runs.

Complete the finished chapter in one generation. Do not discuss response limits, estimate the prospective word count, propose multiple parts or consecutive responses, or ask the user to continue. There is no word-count target, ratio, ceiling, maximum, or other length constraint. Depth and complete source-grounded coverage take priority. Consolidate only genuine repetition; never omit a distinct concept, qualification, warning, example, calculation, procedure, or chain of reasoning to shorten the output.

If the task supplies an output path, write the complete finished chapter as a Markdown file at the resolved convention-compliant path. Do not print or duplicate the chapter in the chat response; return only a concise completion confirmation containing the output path. Never modify any source transcript or overwrite an existing output file unless the task explicitly authorizes overwriting it.

If the task does not supply an output path, return only the finished chapter directly in Markdown. In either mode, do not mention the course presenter, instructor, speaker, recording, attachment, source type, or the process used to create the chapter, except within the narrowly defined accuracy notes below. Present the instructional material directly.

## Mandatory File Naming and Location

When writing to the filesystem, store the chapter in the root `study chapters` folder using this exact pattern:

- `<lesson-number>. <Topic> - Study Chapter.md`

Use the lesson number shared by all transcript parts and a concise, readable topic in title case. Remove transcript-only suffixes such as `part 1` and `part 2` from the combined lesson title. Store the central generation-discrepancy audit at `study chapters/audits/study-chapters-generation-discrepancies.md`.

If a supplied output path violates this convention, use the convention-compliant path and report the normalized path in the completion confirmation. Never rename or relocate a source transcript.

## Source Fidelity and Internal Accuracy

Use the ordered lesson transcript set as the sole source of substantive information. Do not browse, conduct external research, fact-check against outside sources, add general domain knowledge, introduce unsupported examples, or silently change substantive conclusions.

As a narrow terminology exception, you may introduce a standard technical term that is absent from the transcript only when the term names a concept already fully established by the transcript, introduces no new mechanics or substantive claim, and materially improves clarity. Define every such term where it first appears and include it in the glossary. Do not use this exception to import additional domain knowledge.

Correct obvious speech-recognition, punctuation, spelling, and terminology errors when the intended meaning is clear from nearby context—for example, a malformed strategy name or a number contradicted by repeated surrounding figures. Reconstruct fragmented or disordered spoken sentences when their intended meaning can be recovered confidently.

Perform an internal accuracy check using only:

- the lesson transcript set's own surrounding context and repeated statements; and
- elementary arithmetic applied to inputs explicitly stated in the lesson transcript set.

Handle possible errors as follows:

1. **High-confidence ASR error.** Use this classification only for malformed wording or a malformed number contradicted by nearby context. Correct the material in the main instructional text. Immediately after the first materially affected passage, add `**Accuracy note — probable ASR error:**` and briefly explain which surrounding details establish the correction.
2. **High-confidence source-logic, arithmetic, or notation error.** Use this classification when a coherent statement conflicts with its own inputs, arithmetic, units, symbols, or ratio notation. Teach the corrected result or relationship in the main text. Immediately afterward, add `**Accuracy note — source-logic or notation error:**` and explain the inconsistency.
3. **Unresolved ambiguity.** Express only what the transcript supports confidently. Add `**Accuracy note — unresolved ambiguity:**` explaining the competing readings without inventing a resolution.

An incorrect unit or percent sign on an otherwise coherent ratio is a notation error, not evidence of an ASR error. A harmless difference in rounding or truncation is not an error.

Label every accuracy note with exactly one of the three classifications above — `probable ASR error`, `source-logic or notation error`, or `unresolved ambiguity`. Never invent additional note categories. Never use a note, or any other device, to correct, hedge, or contextualize the source against outside domain knowledge: external accuracy is out of scope, and only inconsistencies internal to the lesson transcript set qualify for notes. If the transcript teaches a claim confidently and consistently, teach it as the lesson's claim without editorial qualification.

Do not label a passage erroneous merely because its wording is informal or unfamiliar. Do not identify a particular ASR engine unless that metadata is supplied with the task. When the same systematic error repeats, explain it once at its first material occurrence, then apply the correction consistently without repeating the note anywhere else in the chapter.

An accuracy note is the only permitted reason to refer briefly to faulty wording or logic. Keep each note concise and place it beside the affected instruction rather than collecting notes in a separate section.

Before drafting, silently divide every transcript part into logical sections and build one ordered lesson-level coverage map. Inventory every substantive item, including, when present:

- concepts and definitions;
- distinctions and comparisons;
- causal reasoning and intermediate logic;
- rules, principles, qualifications, exceptions, and warnings;
- strategy mechanics and portfolio implications;
- examples, scenarios, analogies, and counterexamples;
- every material number, percentage, ratio, price, valuation multiple, growth rate, market-capitalization figure, date, time horizon, quantity, formula, and calculation;
- procedures, interpretations, and decision rules; and
- entry, execution, adjustment, risk-management, and exit guidance.

Use the coverage map while drafting and silently verify it afterward. The finished chapter must cover every inventoried item. Give the middle and final thirds of the transcript the same care and depth as the beginning.

Do not measure, target, cap, or compare the chapter's word count with the source. Expand every substantive topic to the depth needed for mastery, including qualifications, mechanics, worked examples, calculations, decision rules, and connections among ideas. Avoid filler and genuine duplication, but never compress supported material to satisfy a length preference.

Remove greetings, verbal filler, promotional language, false starts, and genuine duplication. Do not remove repeated material when repetition adds a qualification, contrast, new implication, procedural step, warning, or useful emphasis.

## Organization and Style

Write in a polished, authoritative textbook style. Explain why each conclusion follows from the underlying mechanics rather than merely stating the conclusion.

Preserve the transcript's logical progression unless reorganizing closely related material makes the explanation substantially clearer. When reorganizing, preserve all relationships, qualifications, and sequence-dependent reasoning.

Use this exact Markdown heading hierarchy:

- Use exactly one `#` heading, reserved for the chapter title.
- Immediately after the title, use `## Chapter Summary` for the opening summary.
- Use `##` headings for the Mastery Map, every major instructional section, Practice Bridge, Conceptual Questions and Answers, Calculation Questions and Answers, and Glossary.
- Use `###` headings for subsections, worked-example components, Practice Bridge components, exercises, and individual questions.
- Use `####` only when genuine nesting below a `###` subsection is necessary.
- Never use another `#` heading and never skip a heading level.
- Place a horizontal rule (`---` on its own line) immediately before every `##` heading except `## Chapter Summary`.

Begin with a concise summary of the chapter's principal lessons under `## Chapter Summary`. Immediately afterward, include the `## Mastery Map`, followed by the instructional chapter. Use paragraphs for explanation and lists or tables only when they materially improve clarity.

The Mastery Map must prioritize the transcript's learning objectives rather than summarize the entire chapter. Include:

- the genuinely highest-priority concepts to master first;
- facts, definitions, formulas, or rules to know from memory;
- causal mechanics to understand rather than merely memorize;
- calculations or procedures to reproduce; and
- consequential mistakes and misunderstandings to avoid.

Include only items supported by the transcript. Omit any Mastery Map category for which the transcript provides no substantive material. Keep each item brief and point the reader toward the corresponding chapter instruction rather than repeating its full explanation. The Mastery Map supplements the instructional body and must never replace, compress, or count toward its required coverage.

Use bold sparingly as an instructional signal. Bold only the shortest self-contained phrase that expresses a major rule, warning, distinction, trade decision, or consequential example result. A complete sentence may be bold only when it is a brief, exceptionally important warning or conclusion.

Use instructional bold highlights where they materially improve learning, without imposing a quota. Never bold whole paragraphs, consecutive sentences, routine definitions, setup details, headings, mathematical blocks, or the same idea more than once. Within a worked example, bold the principal conclusion or decision consequence—not every input, intermediate result, and output. Bold accuracy-note labels and glossary headwords only as required by their structural format; do not treat them as instructional highlights.

Do not refer to information as having been “said,” “shown,” or “discussed.” Present it directly as instructional material.

Do not compress substantive examples into vague summaries. Reproduce their relevant assumptions, inputs, reasoning, calculations, outcomes, and lessons.

Preserve every worked trade, risk-management sequence, and portfolio simulation as a connected sequence. Explain, when present:

- the starting conditions and portfolio state;
- the choices or possible outcomes under consideration;
- the relevant figures and calculations;
- the selected action and its timing;
- alternatives that were rejected, deferred, or left unchanged;
- why the selected action follows from the stated principles; and
- the resulting effect on risk, capital, exposure, realized or unrealized profit and loss, portfolio balance, trade-idea inventory, and the equity curve.

Do not reduce a connected simulation to a short conclusion or list of actions. Preserve how multiple positions and decisions interact. Clearly distinguish an action taken now, a conditional future action, a target, a hypothetical illustration, and a decision to take no action.

## Trade-Idea, Instrument, and Position Coverage

For every trade idea, instrument, position, or portfolio construction discussed, explain each of the following when the information is present:

- strategic purpose and directional thesis;
- the quantitative identification and qualitative evidence supporting it;
- the instrument, long or short direction, sizing context, and intended time horizon;
- valuation, growth, operating, sector, macroeconomic, catalyst, timing, or trade-structure inputs;
- expected behavior, upside and downside paths, risk, capital requirements, and portfolio implications;
- effects of time, liquidity, volatility, changing expectations, and invalidating evidence;
- advantages, disadvantages, warnings, and failure modes;
- suitable and unsuitable market conditions;
- entry, execution, management, adjustment, and exit considerations; and
- how and why the idea or position differs from related alternatives.

When an options structure is actually present, also preserve its long and short legs, option type, strike and expiration relationships, contract ratio, debit or credit, payoff behavior, breakeven, maximum loss, maximum profit or uncapped exposure, time decay, volatility, margin, and assignment risk to the extent supplied by the lesson.

Do not manufacture any characteristic that the transcript does not provide.

## Quantitative Fidelity

Preserve each quantitative concept in the form used by the transcript unless an internal accuracy note requires correction. Do not treat mathematically related measures as interchangeable.

In particular:

- Return on investment (ROI) is a percentage.
- Reward-to-risk is a dimensionless ratio and must be written as a ratio in plain prose, such as 0.2549:1 or 2.67:1, never as 0.2549% or 2.67%.
- When the transcript supplies both ROI and reward-to-risk, retain both separately even when one can be derived from the other.
- If the transcript incorrectly appends a percent sign to reward-to-risk, correct the notation, add one accuracy note at the first occurrence, and use ratio notation consistently thereafter.
- Preserve the transcript's stated precision when a difference is merely harmless rounding or truncation. For example, retain stated values such as 2.07:1, 2.67:1, or 5.91 rather than silently replacing them with values produced by a different rounding convention.
- Within display math, use `\approx` to signal that a preserved value is approximate; in prose, write "approximately". Do not add an accuracy note for an immaterial rounding difference. Correct and flag a numerical difference only when it materially changes the relationship, decision, or conclusion.
- Preserve all stated units and, when applicable, share or contract multipliers.
- Do not infer missing numerical inputs. If the transcript supplies a result but insufficient information to reconstruct it, report the stated result without inventing intermediate values.

## Mathematics and Currency Formatting

Ordinary currency amounts, dates, prices, quantities, multiples, and percentages in prose are not mathematical expressions. Write them in ordinary prose, escaping every literal dollar sign as `\$` so Markdown math renderers cannot mistake it for a math delimiter, for example: \$6.80, January 17, 100 shares, a \$100 price, 10.3 times sales, and 25.5%. Apply the same escaping inside tables. The only unescaped dollar signs anywhere in the chapter must be the `$$ ... $$` delimiters of display math.

An equation, arithmetic operation, inequality, formula, substitution, or derived numerical relationship is a mathematical expression. Write every such expression as raw display LaTeX delimited by `$$ ... $$`, placed on its own line with the opening and closing delimiters on the same line. Never enclose a mathematical expression in backticks or a fenced code block: raw `$$ ... $$` remains visible and copyable in the Markdown source while rendering correctly in both the VS Code Markdown preview and the Google Docs Auto-LaTeX extension, whereas backticks turn it into an unrendered code span.

Use display math in this exact form, on its own line with a blank line above and below:

$$ \text{Total Cost} = \text{Quantity} \times \text{Unit Price} $$

Do not use inline math in any form. Never use `\( ... \)` delimiters or single-dollar `$ ... $` delimiters; neither renders reliably across the target renderers. Write ratios such as 2.67:1, standalone quoted numbers, and units as plain prose, and promote a relationship to its own display-math line only when it genuinely requires mathematical notation.

Inside display math, escape every literal ampersand, percent sign, hash, and dollar sign as `\&`, `\%`, `\#`, and `\$` — for example, `\text{R\&D}`, `\text{D\&A}`, `10\%`. Bare `&`, `%`, and `#` are LaTeX control characters: `&` and `#` produce KaTeX parse errors, and `%` silently comments out the rest of the expression. Every finished expression must render in KaTeX without errors. Avoid the `|` character inside display math placed in a Markdown table cell.

Keep notation simple. Prefer `\frac{}{}`, `\max()`, `\min()`, `\text{}`, `\times`, arithmetic operators, parentheses, subscripts, and superscripts. Avoid aligned equations, cases, arrays, custom macros, and advanced spacing commands.

Whenever arithmetic is performed to derive a result in the instructional body, Practice Bridge, or calculation questions, show all three stages. Place each stage label on its own line, followed by a blank line and the display-math line:

Formula:

$$ \text{Total Cost} = \text{Quantity} \times \text{Unit Price} $$

Substitution:

$$ \text{Total Cost} = 4 \times 25 $$

Final result:

$$ \text{Total Cost} = 100 $$

The Formula line must state the general symbolic relationship. Do not place case-specific quantities, prices, dates, time horizons, company metrics, or valuation inputs in the Formula line. Replace the symbolic inputs with all case-specific values in the Substitution line. Structural mathematical constants, such as `100\%` when converting a decimal return to a percentage, may remain in the Formula line.

This three-stage requirement includes, when calculated, profit or loss, revenue or earnings growth, valuation multiples, inferred market capitalization, price targets, percentage changes, ROI, reward-to-risk, payoff multiples, implied exposure, portfolio-return percentages, per-dollar profit, and comparisons between companies or positions.

Do not repeat the three stages for:

- a number merely quoted as an input from the transcript;
- a previously derived result reused without new arithmetic; or
- a qualitative statement that performs no calculation.

If a sentence introduces a new derived numerical claim—even a short claim in prose, such as converting a dollar profit into a portfolio percentage—it must receive the three-stage treatment at that point.

## Practice Bridge

After the instructional body and before the questions and answers, include a “Practice Bridge” only when the transcript supports actionable trade, spreadsheet, portfolio, execution, or risk-management mechanics. Omit the entire section when the transcript does not support meaningful practice. Do not insert an empty section or a statement that no practice is available.

The Practice Bridge must remain platform-neutral and contain:

### Mechanics Checklist

Convert the transcript-supported mechanics into a concise sequence of actions. Include, when supported, what to identify, calculate, compare, decide, monitor, adjust, record, or exit. Preserve conditional branches and decisions to take no action. Do not add broker-interface navigation, software-specific controls, or procedures absent from the transcript.

### Paper-Practice Exercises

Create source-driven exercises that can be completed without risking capital. Use transcript-supplied examples and figures when available. Do not invent tickers, prices, financial estimates, catalysts, time horizons, market conditions, portfolio states, instruments, or trade setups.

For each exercise, provide:

- **Objective:** the skill being practiced;
- **Required inputs:** transcript-supplied inputs and any user-supplied data fields needed;
- **Actions:** the ordered steps to perform; and
- **Completion evidence:** the observable calculation, worksheet entry, decision record, position specification, or other artifact that demonstrates completion.

If current or user-supplied data is necessary, identify the exact fields required without supplying fictional values, pausing the chapter, or requesting another asset. Do not present a historical transcript example as a current trade recommendation.

### Before Paper Practice

List the transcript-supported concepts, calculations, procedures, warnings, and decision rules the reader must be able to explain or reproduce before attempting the exercises. Make this a chapter-level learning gate only. Never state or imply that completing one chapter establishes readiness to trade live capital.

Keep the Practice Bridge concise and avoid repeating explanations already provided in the instructional body. It is a transfer aid, not a second summary and not a substitute for the instructional chapter.

## Conceptual Questions and Answers

After the instructional body and any applicable Practice Bridge, create a “Conceptual Questions and Answers” section. Create one substantive question for each distinct learning objective, major distinction, decision rule, warning, and worked-example lesson. Include at least one question from every major chapter section.

Create as many conceptual questions as distinct, source-supported learning objectives require. Do not impose a minimum, maximum, target, or preferred count, and never add, split, or cosmetically rephrase questions merely to increase their number.

Label every question with exactly one of the following tags:

- `[Recall]` for definitions, facts, and stated rules;
- `[Mechanics]` for procedures, structures, calculations, and operational sequences; or
- `[Judgment]` for risk assessment, strategy selection, portfolio decisions, scenario diagnosis, and application.

Place the tag at the end of the question heading, for example: `### 1. What does this term mean? [Recall]` Never place a tag before the question.

Collectively test definitions, distinctions, comparisons, causal reasoning, strategy selection, portfolio decisions, risks, qualifications, exceptions, scenario diagnosis, and application of principles. Include both direct-recall questions and original synthesis or application questions. Prioritize Mechanics and Judgment questions when the transcript supports them, but impose no category quotas. Questions need not mirror the transcript's wording.

Place each complete answer immediately after its question. Every answer must be derivable from the chapter and transcript. Do not require outside knowledge or unsupported assumptions. Do not duplicate reasoning or create trivial restatements.

## Calculation Questions and Answers

Next, create a separate “Calculation Questions and Answers” section when the transcript establishes quantitative relationships that can support calculation questions.

Create one calculation question for every distinct quantitative relationship established by the transcript. A relationship is distinct only when it tests a different formula, payoff direction, constraint, interpretation, or decision consequence. Merely changing the numbers does not make a relationship distinct.

You may add hypothetical numerical variations only when each variation tests a genuinely different direction, constraint, interpretation, or decision. Clearly label each as hypothetical. Use only formulas, mechanics, units, multipliers, and relationships established by the supplied source material. Do not introduce new financial concepts, models, or assumptions.

Use no fixed minimum or target count. Stop when all distinct quantitative relationships have been tested. Never pad the section to increase its length.

Place each complete answer immediately after its question. For every calculation answer, follow the required Formula → Substitution → Final result structure and explain the result's meaning when the transcript supports an interpretation.

## Glossary

End with a “Glossary” section. Include every technical or course-specific term needed to understand the chapter independently, including any technical term introduced in an accuracy note. Do not pad the glossary to reach an arbitrary count. Define terms according to their use in the transcript and chapter. Exclude company names, ordinary vocabulary, and terms not used in the chapter. Arrange entries alphabetically and keep every definition precise and self-contained without introducing unrelated information.

## Final Quality Check

Before returning the chapter, silently verify that:

1. every substantive item from the transcript appears in the chapter;
2. all examples and numerical details are retained accurately;
3. every high-confidence internal inconsistency is corrected, classified under exactly one of the three permitted note labels, and receives the required first-occurrence accuracy note, with no invented note categories and no external-knowledge corrections anywhere;
4. each repeated systematic error is explained only once;
5. uncertain passages are not silently resolved or embellished;
6. connected simulations retain their conditions, alternatives, calculations, decisions, reasoning, and consequences;
7. middle and later material receive the same depth as early material;
8. the Mastery Map contains genuinely prioritized concepts and does not duplicate or replace the instructional body;
9. the instructional body completely covers the supplied source material without measuring or constraining its length;
10. the Practice Bridge appears only when supported by actionable transcript mechanics;
11. every practice exercise specifies an objective, required inputs, actions, and observable completion evidence;
12. practice material remains platform-neutral, uses no invented market data or trade setup, and makes no live-trading-readiness claim;
13. no file outside the explicitly designated same-lesson transcript set was requested or treated as necessary;
14. no external research, outside claims, unsupported assumptions, or invented details were added beyond the narrow standard-terminology exception;
15. every added standard technical term names an established transcript concept, is defined where introduced, and appears in the glossary;
16. ROI percentages and reward-to-risk ratios remain separate and correctly formatted;
17. harmless source rounding and truncation are preserved without unnecessary accuracy notes;
18. every Formula line is symbolic, every case-specific input appears in Substitution, and every newly derived result follows the required three-stage format;
19. every mathematical expression is a raw `$$ ... $$` display line, no mathematical expression is enclosed in backticks or code fences, `\(` appears nowhere, every literal dollar sign in prose and tables is escaped as `\$`, no unescaped `$` exists outside `$$ ... $$` delimiters, and no unescaped `&`, `%`, or `#` exists inside any math span;
20. the output uses exactly one H1, follows the required H2–H4 hierarchy without skipped levels, and places horizontal rules before the required H2 sections;
21. every conceptual question has exactly one valid Recall, Mechanics, or Judgment tag at the end of its heading;
22. conceptual questions cover every major section and distinct learning objective without quota-driven padding or cosmetic repetition;
23. calculation questions cover each distinct quantitative relationship without quota-driven padding or cosmetic variations;
24. hypothetical calculations use only transcript-established mechanics;
25. bold highlighting is sparse, selective, and limited to genuinely important instructional signals;
26. the glossary is materially complete, unpadded, and alphabetical; and
27. the response contains no prefatory discussion, upload request, response-limit warning, or continuation plan.

Let substantive coverage and technical intricacy determine the chapter's depth without any length constraint. Prioritize completeness, explanation, and teachability while avoiding filler and genuine repetition.

## Independent Supervisor Audit

Do not perform a separate draft audit, self-audit, correction loop, final audit, word-count check, proportionality check, or audit-file update during generation. Return the complete chapter after one direct drafting pass. The batch supervisor launches an independent auditor in a fresh model turn and requests one focused correction only when that auditor identifies concrete source-grounded defects.
