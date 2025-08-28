#!/usr/bin/env node
/**
 * JSON Normalizer - Extracts valid JSON from various wrapped formats
 * 
 * Handles:
 * - Markdown code fences (```json...```)
 * - Leading/trailing text
 * - Debug output after JSON
 * - Claude's metadata envelope (when using --output-format json)
 * 
 * Usage:
 *   cat file.json | node normalize-json.js
 *   node normalize-json.js file.json
 */

const fs = require('fs');
const process = require('process');

function extractJSON(input) {
  // 1. First try: Check if it's already valid JSON (including Claude envelope)
  try {
    const parsed = JSON.parse(input);
    
    // Claude's --output-format json envelope
    if (parsed.type === 'result' && parsed.result) {
      if (typeof parsed.result === 'string') {
        // First try parsing the whole result as JSON
        try {
          return JSON.parse(parsed.result);
        } catch {
          // Result contains text + JSON, extract the JSON part
          const resultStr = parsed.result;
          const jsonMatch = resultStr.match(/\{[\s\S]*\}$/);
          if (jsonMatch) {
            try {
              return JSON.parse(jsonMatch[0]);
            } catch {
              // Couldn't parse extracted JSON
            }
          }
          // Result isn't JSON, might be an error message
          if (parsed.is_error) {
            throw new Error(`Claude error: ${parsed.result}`);
          }
          // Fall through to try other extraction methods
        }
      } else if (typeof parsed.result === 'object') {
        return parsed.result;
      }
    }
    
    // Check if it's already a valid review JSON
    if (parsed.tool && parsed.model && parsed.findings) {
      return parsed;
    }
    
    // Plain JSON object
    if (typeof parsed === 'object') {
      return parsed;
    }
  } catch {
    // Not valid JSON, continue with extraction
  }
  
  // 2. Handle Codex 0.25.0 JSONL format (--json flag outputs events)
  const lines = input.trim().split('\n');
  if (lines.length > 1 && lines[0].trim().startsWith('{')) {
    // Try to parse as JSONL
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (!line) continue;
      try {
        const event = JSON.parse(line);
        // Look for model output events
        if (event.type === 'model_output' || event.type === 'final_result') {
          if (event.output) {
            try {
              return JSON.parse(event.output);
            } catch {
              // Output might be embedded in content
              const match = event.output.match(/\{[\s\S]*\}/);
              if (match) return JSON.parse(match[0]);
            }
          }
          if (event.content) {
            // Extract JSON from content
            const match = event.content.match(/\{[\s\S]*\}/);
            if (match) return JSON.parse(match[0]);
          }
        }
        // Also check for direct JSON in event
        if (event.tool && event.model && event.findings) {
          return event;
        }
      } catch {
        // Not a valid JSON line, continue
      }
    }
  }
  
  // 3. Handle Codex 0.22.0 verbose format (fallback for older versions)
  let processedInput = input;
  processedInput = processedInput.replace(/^Reading prompt from stdin\.\.\.\n/m, '');
  
  const codexMarker = /\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\] codex\n/;
  const codexMatch = processedInput.match(codexMarker);
  if (codexMatch) {
    const markerIndex = processedInput.indexOf(codexMatch[0]);
    if (markerIndex >= 0) {
      processedInput = processedInput.substring(markerIndex + codexMatch[0].length);
      processedInput = processedInput.replace(/\n\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\] tokens used: \d+\s*$/, '');
    }
  } else {
    // No marker found, use the processed input as is
    processedInput = input;
  }

  // 4. Remove markdown code fences (Gemini/general fallback)
  let cleaned = processedInput;
  
  // Look for ```json or ``` patterns
  const jsonFenceMatch = cleaned.match(/```json\s*\n?([\s\S]*?)\n?```/i);
  const plainFenceMatch = cleaned.match(/```\s*\n?([\s\S]*?)\n?```/);
  
  if (jsonFenceMatch) {
    cleaned = jsonFenceMatch[1];
  } else if (plainFenceMatch) {
    cleaned = plainFenceMatch[1];
  }
  
  // 5. Extract first balanced JSON object
  const firstBrace = cleaned.indexOf('{');
  const firstBracket = cleaned.indexOf('[');
  let startIdx = -1;
  let endChar = '';
  
  if (firstBrace >= 0 && (firstBracket < 0 || firstBrace < firstBracket)) {
    startIdx = firstBrace;
    endChar = '}';
  } else if (firstBracket >= 0) {
    startIdx = firstBracket;
    endChar = ']';
  }
  
  if (startIdx < 0) {
    throw new Error('No JSON object or array found in input');
  }
  
  // Find matching closing brace/bracket
  let depth = 0;
  let inString = false;
  let escaped = false;
  let endIdx = -1;
  
  for (let i = startIdx; i < cleaned.length; i++) {
    const char = cleaned[i];
    
    if (escaped) {
      escaped = false;
      continue;
    }
    
    if (char === '\\') {
      escaped = true;
      continue;
    }
    
    if (char === '"') {
      inString = !inString;
      continue;
    }
    
    if (inString) continue;
    
    if (char === '{' || char === '[') {
      depth++;
    } else if (char === '}' || char === ']') {
      depth--;
      if (depth === 0 && char === endChar) {
        endIdx = i;
        break;
      }
    }
  }
  
  if (endIdx < 0) {
    throw new Error('No matching closing brace/bracket found');
  }
  
  const extracted = cleaned.slice(startIdx, endIdx + 1);
  
  // Validate extracted JSON
  try {
    return JSON.parse(extracted);
  } catch (e) {
    throw new Error(`Extracted text is not valid JSON: ${e.message}`);
  }
}

// Main
async function main() {
  let input;
  
  if (process.argv.length > 2) {
    // Read from file
    try {
      input = fs.readFileSync(process.argv[2], 'utf8');
    } catch (e) {
      console.error(`Error reading file: ${e.message}`);
      process.exit(1);
    }
  } else {
    // Read from stdin
    input = '';
    for await (const chunk of process.stdin) {
      input += chunk;
    }
  }
  
  if (!input.trim()) {
    console.error('No input provided');
    process.exit(1);
  }
  
  try {
    const json = extractJSON(input);
    console.log(JSON.stringify(json, null, 2));
    process.exit(0);
  } catch (e) {
    console.error(`Failed to extract JSON: ${e.message}`);
    // Output the original input for debugging
    if (process.env.DEBUG_NORMALIZE) {
      console.error('Original input:', input.slice(0, 500));
    }
    process.exit(1);
  }
}

if (require.main === module) {
  main().catch(err => {
    console.error(`Unexpected error: ${err.message}`);
    process.exit(1);
  });
}