# Cline Adapter

Use Cline slash workflow commands or custom instructions that call the same canonical workflow names.

Keep command bodies thin:

- Resolve the current repo to a memory project.
- Read the project and work-item entrypoints.
- Use qmd for targeted supporting context.
- Summarize or update memory according to the requested workflow.

When using Cline workflow hooks or custom event behavior, keep side effects explicit. Prefer prompting the agent to update memory over silently modifying memory-bank files.
