# Transcript Study Guide Specification

Create a self-contained study guide grounded only in the ordered transcript files supplied by the supervisor.

Requirements:

- Preserve the lesson's claims, terminology, qualifications, examples, and sequence without inventing facts.
- Synthesize repeated material instead of duplicating it.
- Explain important concepts in plain language while retaining technical precision.
- Use descriptive Markdown headings, short paragraphs, and lists only where they improve learning.
- Include at least one source-grounded fenced Mermaid diagram that materially clarifies mastery relationships, causal structure, sequence, workflow, or decisions. Never use D2.
- Make every diagram a compact visual explanation: show the governing question, inputs, transformations or decisions, outputs, dependencies, cautions, and feedback where applicable. Use `mindmap` for conceptual hierarchy, `flowchart` for paths, calculations, dependencies, build order, and decisions, and `stateDiagram-v2` for regimes, monitoring, and feedback. Keep labels concise, branch relationships, and split distinct mechanisms instead of forcing them into one oversized lane.
- Include an overview, the main concepts and procedures, common errors or cautions found in the source, a complete recap, and review questions with answers.
- Group calculation questions by normalized solution family: the same unknown, formula, and operator sequence remain one family after constants, labels, and signs are normalized. Use one standalone question per family by default and at most two only when a second tests a genuine reasoning branch, binding constraint, sign or unit trap, or material decision interpretation. Combine three or more deliberate contrast cases into one multi-part question with a shared formula and compact table. Present dependent calculation steps as one connected case study.
- There is no word-count target, ratio, minimum, maximum, or other length constraint. Use as much depth as substantive source-grounded mastery requires, without filler or genuine duplication.
- Write the guide completely in one direct pass and prioritize source-grounded depth.
- Do not mention the staging workspace, supervisor, prompts, transcript filenames, or generation process in the guide.
- Do not use outside knowledge, browsing, web search, MCP tools, or unrelated files.
- End the completed file with the exact completion marker supplied in the stage instruction.
