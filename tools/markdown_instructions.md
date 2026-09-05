Generate a Markdown (.md) knowledge/memory file with a Python script. {{SUCCESS_DELIVERY_RULE}}

CANNOT embed charts or images. Call `learn` (`python_script`, `file_name`).

## Purpose

You are writing a **knowledge memory** — a concise, well-structured record of what you learned about
a specific topic or experience. Use these files to capture knowledge that goes beyond your base
training, so you can recall and reuse it later.

## Title pattern (required)

Start every memory with a title in this exact form, where `X` is the topic or subject:

```markdown
# What I know about X
```

## Structure (required)

- Use an `## H2` heading for the summary, then `### H3` subheadings for the details.
- Always separate "what works" from "what to avoid": the good/neutral side first, then the
  problems. This keeps the memory actionable.
- Write plain, direct body text — short sentences, no filler. Each subheading should describe the
  strongest takeaway so a reader can scan it quickly.

### Recommended skeleton

```markdown
# What I know about <topic>

## Summary
Short, direct paragraph stating the key point.

### What stands out (positive / neutral)
- Confirmed facts or behavior that works well.
- Any nuance worth remembering.
- Reusable patterns, options, or decisions.

### What to avoid / what not to do
- Pitfalls, mistakes, or bad outcomes observed.
- Do NOT do: concrete anti-patterns.
- Edge cases or conditions that produce failures.

## Details
Additional notes, examples, or context. Optional.
```

## Markdown elements to use (more is better)

Use whatever Markdown makes it clear and scannable:

- `#` / `##` / `###` headings: `## Summary`, `### What stands out (positive / neutral)`,
  `### What to avoid / what not to do`.
- **Bold** `**...**` or *italic* `*...*` for emphasis on key terms.
- `- ` bullet lists and `1. ` ordered lists for steps or sequence.
- Inline code `` `...` `` and fenced ``` ``` blocks for commands, scripts, or snippets.
- `> ` blockquotes for a single important callout.
- `|` tables to compare options, versions, or outcomes.
- Horizontal rules `---` to separate major sections.

Use Markdown naturally — but always keep `MD_BUFFER = md_buffer`, and keep the writing clear,
direct, and in English.

## Example

```python
MD_BUFFER = md_buffer                # keep this line exactly
content = (
    "# What I know about streaming agents\n\n"
    "## Summary\n"
    "Streaming agents emit tokens incrementally, which improves perceived latency.\n\n"
    "### What stands out (positive / neutral)\n"
    "- Incremental output feels faster even when total time is the same.\n"
    "- `async def` handlers stay off the event loop only if they truly `await`.\n\n"
    "### What to avoid / what not to do\n"
    "- Do NOT block the event loop with synchronous I/O inside an `async def`.\n"
    "- Avoid assuming `assistant_response` is structured — it is plain text.\n"
)
MD_BUFFER.write(content.encode("utf-8"))
```

## Rules

- Keep `MD_BUFFER = md_buffer` exactly.
- Write bytes: `.encode("utf-8")`.
- Use the `# What I know about X` title pattern.
- Always include the "What stands out" and "What to avoid / what not to do" sections.
- Write in English, plain and direct.
