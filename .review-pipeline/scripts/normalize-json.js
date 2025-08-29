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

// Helper: safely JSON.parse
function tryParseJSON(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// Helper: extract a JSON value from arbitrary text
function extractJSONFromText(text) {
  // 1) try whole text
  const whole = tryParseJSON(text);
  if (whole && typeof whole === 'object') return whole;

  // 2) fenced blocks (prefer ```json ... ```)
  const fenceJson = text.match(/```json\s*[\r\n]+([\s\S]*?)```/i);
  if (fenceJson) {
    const p = tryParseJSON(fenceJson[1]);
    if (p && typeof p === 'object') return p;
  }
  const fenceAny = text.match(/```\s*[\r\n]+([\s\S]*?)```/);
  if (fenceAny) {
    const p = tryParseJSON(fenceAny[1]);
    if (p && typeof p === 'object') return p;
  }

  // 3) first balanced JSON object/array in text
  const firstBrace = text.indexOf('{');
  const firstBracket = text.indexOf('[');
  let startIdx = -1; let endChar = '';
  if (firstBrace >= 0 && (firstBracket < 0 || firstBrace < firstBracket)) {
    startIdx = firstBrace; endChar = '}';
  } else if (firstBracket >= 0) {
    startIdx = firstBracket; endChar = ']';
  }
  if (startIdx >= 0) {
    let depth = 0, inString = false, escaped = false, endIdx = -1;
    for (let i = startIdx; i < text.length; i++) {
      const ch = text[i];
      if (escaped) { escaped = false; continue; }
      if (ch === '\\') { escaped = true; continue; }
      if (ch === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (ch === '{' || ch === '[') depth++;
      else if (ch === '}' || ch === ']') { depth--; if (depth === 0 && ch === endChar) { endIdx = i; break; } }
    }
    if (endIdx > startIdx) {
      const slice = text.slice(startIdx, endIdx + 1);
      const p = tryParseJSON(slice);
      if (p && typeof p === 'object') return p;
    }
  }

  throw new Error('No JSON found in text');
}

function extractJSON(input) {
  // 1. First try: Check if it's already valid JSON (including Claude envelope)
  try {
    const parsed = JSON.parse(input);

    // Handle Claude error responses
    if (parsed && parsed.type === 'result' && parsed.subtype === 'error_during_execution') {
      const now = new Date().toISOString();
      return {
        tool: process.env.TOOL || 'claude-code',
        model: process.env.MODEL || 'opus',
        timestamp: now,
        pr: extractPRInfo(),
        summary: 'Claude encountered an error during execution and could not complete the review',
        assumptions: [],
        findings: [],
        metrics: {
          duration_ms: parsed.duration_ms || 0,
          cost_usd: parsed.total_cost_usd || 0
        },
        evidence: [],
        tests: { executed: false, command: null, exit_code: null, summary: 'Tests not executed' },
        exit_criteria: { 
          ready_for_pr: false, 
          reasons: ['Claude error during execution - review could not be completed']
        },
        error: 'claude_execution_error'
      };
    }
    
    // Claude's --output-format json envelope
    if (parsed && parsed.type === 'result' && parsed.result !== undefined) {
      if (typeof parsed.result === 'string') {
        const resultStr = parsed.result;
        // First try to parse as direct JSON (if it's an escaped JSON string)
        try {
          const directParse = JSON.parse(resultStr);
          if (directParse && typeof directParse === 'object') {
            return directParse;
          }
        } catch {
          // Not direct JSON, try to extract from text/markdown
        }
        // Try to parse JSON from the string (fenced or balanced)
        try {
          return extractJSONFromText(resultStr);
        } catch {
          // Unstructured result: build conservative, transparent report
          const now = new Date().toISOString();
          return {
            tool: 'claude-code',
            model: parsed.model || 'sonnet',
            timestamp: now,
            pr: {
              repo: 'unknown', number: 0, head_sha: '', branch: 'unknown', link: 'https://github.com/'
            },
            summary: String(resultStr).trim() + ' — [normalized unstructured output]',
            assumptions: [], findings: [], metrics: {}, evidence: [],
            tests: { executed: false, command: null, exit_code: null, summary: 'Tests not executed' },
            exit_criteria: { ready_for_pr: false, reasons: ['claude result was unstructured; normalized without findings'] },
            error: 'unstructured_output'
          };
        }
      } else if (typeof parsed.result === 'object') {
        return parsed.result;
      }
    }

    // Already a valid report
    if (parsed && parsed.tool && parsed.model && parsed.findings !== undefined) {
      return parsed;
    }
    // Fall through to text extraction
  } catch {
    // Not JSON; will try to extract
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
    // Try to recover truncated JSON
    try {
      return attemptJSONRecovery(extracted);
    } catch (recoveryError) {
      throw new Error(`Extracted text is not valid JSON: ${e.message}`);
    }
  }
}

/**
 * Attempt to recover truncated or malformed JSON
 */
function attemptJSONRecovery(jsonStr) {
  // Track depth to know what needs closing
  let depth = 0;
  let inString = false;
  let escapeNext = false;
  
  for (let i = 0; i < jsonStr.length; i++) {
    const char = jsonStr[i];
    
    if (escapeNext) {
      escapeNext = false;
      continue;
    }
    
    if (char === '\\') {
      escapeNext = true;
      continue;
    }
    
    if (char === '"' && !inString) {
      inString = true;
    } else if (char === '"' && inString) {
      inString = false;
    } else if (!inString) {
      if (char === '{' || char === '[') {
        depth++;
      } else if (char === '}' || char === ']') {
        depth--;
      }
    }
  }
  
  // If truncated, try to close open structures
  let recovered = jsonStr;
  
  // Close open string
  if (inString) {
    recovered += '"';
  }
  
  // Add missing commas or colons if needed
  const lastChar = recovered.trim().slice(-1);
  if (lastChar === ':') {
    recovered += 'null'; // Add null value for missing field
  } else if (lastChar === ',') {
    recovered = recovered.slice(0, -1); // Remove trailing comma
  }
  
  // Close open structures
  while (depth > 0) {
    // Simple heuristic: close with appropriate bracket
    const needsBrace = recovered.lastIndexOf('{') > recovered.lastIndexOf('[');
    recovered += needsBrace ? '}' : ']';
    depth--;
  }
  
  // Try to parse the recovered JSON
  try {
    return JSON.parse(recovered);
  } catch (e) {
    // If recovery failed completely, return partial structure
    // This at least preserves what we could parse
    console.error('Warning: JSON recovery partially failed, returning best effort');
    return {
      error: 'truncated_json',
      partial_data: jsonStr.substring(0, 500),
      recovery_attempted: true
    };
  }
}

function normalizeReport(data, tool) {
  // Always use our known tool and model values (don't trust LLM self-identification)
  if (tool) data.tool = tool;
  if (process.env.MODEL) data.model = process.env.MODEL;
  
  // TODO: Remove more fields from LLM responsibility:
  // - timestamp: We know when we executed the review, use Date.now()
  // - pr.*: We have all PR data in pr.json, inject it here
  // - tests.executed: We know if we ran tests from pipeline config
  // - tests.command: We know the test command from pipeline.config.json
  // - tests.exit_code: We have the actual exit code from test execution
  // The LLM should only provide analysis (summary, findings, assumptions)
  // not report factual data we already know from the execution environment
  
  if (!data.timestamp) data.timestamp = new Date().toISOString();
  if (!data.pr || typeof data.pr !== 'object') {
    data.pr = {};
  }
  if (!data.pr.repo) data.pr.repo = process.env.PR_REPO || 'unknown';
  if (data.pr.number === undefined) {
    const n = parseInt(process.env.PR_NUMBER || '0', 10);
    data.pr.number = Number.isFinite(n) ? n : 0;
  }
  if (!data.pr.head_sha) data.pr.head_sha = process.env.HEAD_SHA || '';
  if (!data.pr.branch) data.pr.branch = process.env.PR_BRANCH || 'unknown';
  if (!data.pr.link) data.pr.link = process.env.RUN_URL || 'https://github.com/';
  if (!data.timestamp) data.timestamp = new Date().toISOString();
  if (!data.assumptions) data.assumptions = [];
  if (!data.findings) data.findings = [];
  if (!data.metrics) data.metrics = {};
  if (!data.evidence) data.evidence = [];
  if (!data.tests) {
    data.tests = {
      executed: false,
      command: null,
      exit_code: null,
      summary: 'Tests not executed'
    };
  } else {
    // Fix null values for tests.executed (schema expects boolean)
    if (data.tests.executed === null || data.tests.executed === undefined) {
      data.tests.executed = false;
    }
    // Ensure boolean type
    if (typeof data.tests.executed !== 'boolean') {
      data.tests.executed = Boolean(data.tests.executed);
    }
  }
  
  if (!data.exit_criteria) data.exit_criteria = {
    ready_for_pr: false,
    reasons: []
  };

  // Ensure summary exists and is a string (do not truncate)
  if (!data.summary) {
    data.summary = 'No summary provided';
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
      // Detect tool from env hint, filename, or content
      let tool = json.tool || process.env.TOOL || null;
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
