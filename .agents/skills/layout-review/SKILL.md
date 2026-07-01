---
name: layout-review
description: Review typography and layout quality for UI screens, web pages, screenshots, documents, slides, prototypes, and design drafts. Use when Codex needs to audit visual hierarchy, alignment, spacing, readability, responsive behavior, text overflow, Chinese/English mixed typography, or produce actionable layout findings for iteration.
---

# Layout Review

Use this skill to perform focused typography and layout audits. Prefer specific, evidence-based findings over broad design opinions.

## Workflow

1. Identify the artifact type: UI screen, web page, screenshot, document, slide, prototype, or design draft.
2. Establish context: target device, viewport size, language, audience, density, design-system constraints, and whether the artifact is meant for reading, scanning, editing, selling, or operation.
3. Inspect information hierarchy:
   - Check whether titles, subtitles, body text, labels, metadata, buttons, captions, helper text, and warnings have clear priority.
   - Flag hierarchy that relies only on color, uses excessive size jumps, or makes related content look unrelated.
4. Inspect alignment and structure:
   - Check page margins, section edges, baselines, column rhythm, icon/text alignment, repeated component placement, and form/control alignment.
   - Flag accidental offsets, uneven columns, disconnected groups, and components that break the expected grid.
5. Inspect spacing:
   - Compare outer margins, section gaps, card padding, list rhythm, paragraph spacing, control spacing, and group separation.
   - Flag cramped content, inconsistent spacing, weak grouping, excessive empty space, and nested containers that make the page feel heavy.
6. Inspect typography:
   - Check font family consistency, size scale, weight usage, line height, letter spacing, line length, punctuation, numeral treatment, and Chinese/English mixed text.
   - Flag unreadable density, awkward wrapping, poor contrast, inconsistent text treatment, and text that looks visually louder than its role.
7. Inspect overflow and edge cases:
   - Consider long titles, long names, long numbers, translated text, empty states, dense data, narrow screens, and browser zoom.
   - Flag clipping, overlap, broken wrapping, layout shift, ellipsis misuse, and controls whose text cannot fit.
8. Inspect responsive behavior when relevant:
   - Check mobile, tablet, desktop, and wide desktop behavior.
   - Verify that important content remains visible, tap targets remain usable, and text does not occlude other UI.
9. Prioritize findings:
   - Lead with issues that harm comprehension, task completion, accessibility, or visual stability.
   - Treat subjective preferences as lower priority unless tied to concrete user impact.
10. Recommend fixes:
   - For each issue, describe the location, problem, impact, and specific correction.
   - Keep recommendations minimal and compatible with the existing design system.

## Evidence

Use available evidence before giving final findings:

- For code-backed web/UI work, inspect the relevant HTML, CSS, components, and screenshots when available.
- For visual artifacts, use screenshots or images directly when available.
- For responsive claims, verify with actual viewport checks when tools are available; otherwise state the assumption.
- When the user provides project-specific standards, follow those over the default rubric.

## Iteration

Read `references/rubric.md` when the review needs more detailed scoring, Chinese typography checks, responsive heuristics, or prior learnings. Update that file when repeated review misses reveal a better rule, a clearer severity definition, or a project-specific convention worth preserving.

Keep additions concrete:

- Add observed failure patterns, not generic design theory.
- Include the condition that triggers the rule.
- Include the user impact and preferred correction.
- Avoid adding optional checks unless they improve current review accuracy.

## Output Format

Use this structure unless the user asks for another format:

```markdown
## 排版审核结论

总体结论：通过 / 需修改 / 存在明显风险

### 主要问题

1. 位置：...
   问题：...
   影响：...
   建议：...

2. 位置：...
   问题：...
   影响：...
   建议：...

### 次要问题

- ...

### 通过项

- ...
```

If there are no meaningful issues, say so directly and mention any unverified assumptions.
