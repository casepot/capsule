Provider overlay — Gemini CLI
- Logged in via **OAuth** (`gemini`), with **no** `GEMINI_API_KEY`.  
- Use non-interactive `-p` execution; output must be **only** the JSON per schema.  
- Set `tool` to `"gemini-cli"` and `model` to the active Gemini model.
- CRITICAL: Do NOT wrap JSON in markdown code fences (no ```json or ```).
- Output raw JSON directly, starting with { and ending with }.
- No explanatory text before or after the JSON.