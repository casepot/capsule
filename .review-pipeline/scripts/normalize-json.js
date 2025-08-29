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

import fs from 'fs';
import process from 'process';

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
          // Result isn't JSON, return a normalized report built from the envelope
          const summary = String(resultStr).trim();
          const now = new Date().toISOString();
          // Best-effort defaults for required fields
          return {
            tool: 'claude-code',
            model: 'sonnet',
            timestamp: now,
            pr: {
              repo: 'unknown',
              number: 0,
              head_sha: '',
              branch: 'unknown',
              link: 'https://github.com/'
            },
            summary: summary.length >= 50 ? summary : (summary + ' '.repeat(50 - summary.length)),
            assumptions: [],
            findings: [],
            tests: { executed: false, command: null, exit_code: null, summary: 'Tests not executed' },
            exit_criteria: { ready_for_pr: true, reasons: [] }
          };
        }
      } else if (typeof parsed.result === 'object') {
        return parsed.result;
      }
    }
    
    // Check if it's already a valid review JSON
    if (parsed.tool && parsed.model && parsed.findings) {
      return parsed;
    }
    
    // Don't return arbitrary plain objects (like envelopes). Force extraction below.
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

function normalizeReport(data, tool) {
  // Ensure required fields
  if (!data.tool && tool) data.tool = tool;
  if (!data.timestamp) data.timestamp = new Date().toISOString();
  if (!data.assumptions) data.assumptions = [];
  if (!data.findings) data.findings = [];
  if (!data.metrics) data.metrics = {};
  if (!data.evidence) data.evidence = [];
  if (!data.tests) data.tests = {
    executed: false,
    command: null,
    exit_code: null,
    summary: 'Tests not executed'
  };
  if (!data.exit_criteria) data.exit_criteria = {
    ready_for_pr: false,
    reasons: []
  };

  // Ensure summary exists and is a string (truncate if too long)
  if (!data.summary) {
    data.summary = 'No summary provided';
  } else if (data.summary.length > 500) {
    data.summary = data.summary.substring(0, 497) + '...';
  }

  // Fix evidence arrays - convert objects to strings
  if (data.evidence && Array.isArray(data.evidence)) {
    data.evidence = data.evidence.map(e => {
      if (typeof e === 'object' && e !== null) {
        // Convert evidence object to string
        if (e.file || e.source) {
          const file = e.file || e.source;
          const lines = e.lines || '';
          return lines ? `${file}:${lines}` : file;
        }
        return JSON.stringify(e);
      }
      return String(e);
    });
  }

  // Fix assumptions evidence
  if (data.assumptions && Array.isArray(data.assumptions)) {
    data.assumptions = data.assumptions.map(a => {
      if (a.evidence && Array.isArray(a.evidence)) {
        a.evidence = a.evidence.map(e => {
          if (typeof e === 'object' && e !== null) {
            if (e.file || e.source) {
              const file = e.file || e.source;
              const lines = e.lines || '';
              return lines ? `${file}:${lines}` : file;
            }
            return JSON.stringify(e);
          }
          return String(e);
        });
      }
      // Ensure falsification_step is string or undefined
      if (a.falsification_step === null) {
        delete a.falsification_step;  // Remove null values
      } else if (a.falsification_step !== undefined) {
        a.falsification_step = String(a.falsification_step);
      }
      return a;
    });
  }

  // Fix findings
  if (data.findings && Array.isArray(data.findings)) {
    data.findings = data.findings.map(f => {
      // Fix category - normalize variations
      if (f.category) {
        const cat = f.category.toLowerCase();
        if (cat.includes('design') || cat.includes('architecture')) {
          f.category = 'architecture';
        } else if (cat.includes('doc') && !cat.includes('docs')) {
          f.category = 'docs';
        } else if (cat === 'docs/style' || cat === 'documentation') {
          f.category = 'docs';
        } else if (cat.includes('style') && !cat.includes('docs')) {
          f.category = 'style';
        } else if (cat.includes('maintain')) {
          f.category = 'maintainability';
        } else if (cat.includes('correct')) {
          f.category = 'correctness';
        } else if (cat.includes('test')) {
          f.category = 'testing';
        } else if (cat.includes('security')) {
          f.category = 'security';
        } else if (cat.includes('performance') || cat.includes('perf')) {
          f.category = 'performance';
        } else if (!['security', 'correctness', 'performance', 'testing', 'architecture', 'style', 'maintainability', 'docs'].includes(f.category)) {
          f.category = 'style'; // Default fallback
        }
      }

      // Fix severity - normalize variations
      if (f.severity) {
        const sev = f.severity.toLowerCase();
        if (sev === 'critical' || sev === 'blocker') {
          f.severity = 'critical';
        } else if (sev === 'high' || sev === 'major') {
          f.severity = 'high';
        } else if (sev === 'medium' || sev === 'moderate') {
          f.severity = 'medium';
        } else if (sev === 'low' || sev === 'minor' || sev === 'trivial') {
          f.severity = 'low';
        } else if (!['critical', 'high', 'medium', 'low'].includes(f.severity)) {
          f.severity = 'low'; // Default fallback
        }
      }

      // Fix evidence array
      if (f.evidence && Array.isArray(f.evidence)) {
        f.evidence = f.evidence.map(e => {
          if (typeof e === 'object' && e !== null) {
            if (e.file || e.source) {
              const file = e.file || e.source;
              const lines = e.lines || '';
              return lines ? `${file}:${lines}` : file;
            }
            return JSON.stringify(e);
          }
          return String(e);
        });
      }
      return f;
    });
  }

  // Fix tests.coverage - ensure it's number or null
  if (data.tests && data.tests.coverage !== undefined) {
    if (typeof data.tests.coverage === 'string') {
      if (data.tests.coverage.toLowerCase() === 'not reported' || 
          data.tests.coverage === '') {
        data.tests.coverage = null;
      } else {
        const parsed = parseFloat(data.tests.coverage);
        data.tests.coverage = isNaN(parsed) ? null : parsed;
      }
    } else if (typeof data.tests.coverage === 'object') {
      // Coverage might be an empty object
      data.tests.coverage = null;
    } else if (typeof data.tests.coverage !== 'number') {
      data.tests.coverage = null;
    }
  }

  return data;
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
    let json = extractJSON(input);
    
    // Apply normalization if this looks like a review report
    if (json.findings || json.assumptions || json.tests) {
      // Try to detect tool from filename or content
      let tool = json.tool;
      if (!tool && process.argv[2]) {
        const filename = process.argv[2].toLowerCase();
        if (filename.includes('claude')) tool = 'claude-code';
        else if (filename.includes('codex')) tool = 'codex-cli';
        else if (filename.includes('gemini')) tool = 'gemini-cli';
      }
      json = normalizeReport(json, tool);
    }
    
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

// Check if script is run directly (ES module equivalent)
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(err => {
    console.error(`Unexpected error: ${err.message}`);
    process.exit(1);
  });
}
