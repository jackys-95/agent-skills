# Gemini Adapter

Use TOML command files for Gemini CLI command wrappers.

Path:

```text
.gemini/commands/memory/resume.toml
```

Command:

```text
/memory:resume
```

Example:

```toml
description = "Resume a qmd-backed task memory bank work item."
prompt = """
Resume memory-bank work for: {{args}}

1. Read the project README and active context.
2. Read the work item README and active context if a work id is provided.
3. Use qmd for targeted supporting context.
4. Summarize objective, current state, next action, and missing context.
"""
```

Keep Gemini commands as prompt wrappers around the shared workflow. Add harness-specific event behavior only when Gemini exposes a stable mechanism for it.
