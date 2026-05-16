# Zed Adapter

For Zed external agents, prefer the external agent's native command system:

- Claude Agent: Claude skills/custom commands.
- Gemini CLI: Gemini TOML commands.
- Codex: Codex skills/commands where available.

For Zed Text Threads, slash commands can add context but are not agentic. Use them for prompt/context insertion rather than memory-bank mutation.

If Zed exposes hooks or events for external agents, use them as prompts to run explicit memory-bank workflows. Avoid automatic writes unless the user has enabled that behavior for the workspace.
