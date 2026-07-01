# Layout Review Rubric

Use this rubric when a review needs stricter judgment than the main workflow. Add project-specific learnings here as real reviews expose misses.

## Severity

- Critical: Blocks reading, action, or conversion; causes overlap, clipping, hidden primary content, broken responsive layout, or misleading hierarchy.
- Major: Slows comprehension or creates visible inconsistency across important components; likely noticeable to users.
- Minor: Small polish issue with limited task impact; worth fixing when touching the area.

## Core Checks

### Hierarchy

- Primary content should be identifiable within 2 seconds.
- Related items should look grouped by proximity and alignment before relying on borders or color.
- Buttons, warnings, prices, counts, and status labels should not visually overpower the primary task unless they are the primary task.
- Repeated modules should use consistent title, metadata, body, and action treatment.

### Alignment

- Repeated components should share the same left edge, right edge, and internal padding unless the layout intentionally changes rhythm.
- Icons and text should align optically, not only mathematically; small icons often need slight vertical adjustment.
- Tables, forms, lists, and cards should preserve predictable scan lines.
- Mixed centered and left-aligned content should be flagged when it weakens scanning.

### Spacing

- Spacing should communicate grouping: tighter inside a group, looser between groups.
- Similar relationships should use similar spacing across the screen.
- Dense operational interfaces may use compact spacing, but labels, values, and controls still need clear separation.
- Empty space is a problem when it hides useful content below the fold or makes related content feel disconnected.

### Typography

- Font sizes and weights should map to roles, not decoration.
- Body text should have comfortable line height and line length for the medium.
- All-caps, bold, and high-contrast color should be limited to content that needs emphasis.
- Letter spacing should usually stay at 0 for normal UI text unless a design system explicitly says otherwise.

### Chinese And Mixed Text

- Avoid awkward breaks around Chinese punctuation, English words, numbers, units, and symbols.
- Keep numeral and unit treatment consistent, such as `12px`, `3.5%`, `¥199`, and dates.
- Avoid overly loose Chinese body text caused by excessive letter spacing.
- Check whether Latin text visually dominates adjacent Chinese text because of font, size, or weight mismatch.

### Overflow And Edge Cases

- Test or reason through longest likely labels, names, numbers, translated strings, and empty values.
- Text inside buttons, tabs, chips, table cells, and cards should not clip or overlap at common viewport widths.
- Ellipsis is acceptable only when the remaining context still lets users understand or recover the full value.
- Avoid layout shift caused by hover states, loaded images, validation messages, counters, badges, or dynamic data.

### Responsive Behavior

- Mobile should preserve task priority, not simply stack everything.
- Touch targets should remain usable and not crowd adjacent actions.
- Wide desktop should not produce unreadably long text lines or disconnected content islands.
- Important first-viewport content should remain discoverable without hiding the primary task.

## Finding Quality

Each finding should include:

- Location: the smallest useful area, component, or text snippet.
- Problem: the visible layout or typography issue.
- Impact: why it matters for reading, scanning, action, accessibility, or trust.
- Fix: the smallest concrete change likely to resolve it.

Avoid vague findings such as "make it prettier", "adjust spacing", or "optimize typography" unless paired with a precise target and correction.
