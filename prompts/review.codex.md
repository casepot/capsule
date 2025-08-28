Provider overlay — OpenAI Codex CLI
- Running in **exec** mode for non-interactive execution.  
- Set `tool` to `"codex-cli"` and `model` to the active Codex model.  
- You CAN and SHOULD read files (using cat, head, etc.) but do NOT edit/write files.
- You CAN run read-only shell commands (ls, cat, head, grep) but do NOT modify anything.
- Output must be ONLY the JSON per schema.
- CRITICAL: Do NOT wrap JSON in markdown code fences (no ```json).
- Output raw JSON directly, no debug info or explanatory text.