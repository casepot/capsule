Provider overlay — Claude Code
- Mode: `--permission-mode plan` (analyze only; no edits/exec).  
- Set `tool` to `"claude-code"` and `model` to the active Claude model.  
- Do not attempt `/` slash commands; you are in headless print mode.
- Output must be ONLY the JSON per schema.
- CRITICAL: Do NOT wrap JSON in markdown code fences (no ```json).
- Output raw JSON directly, no explanatory text before or after.