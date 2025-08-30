#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';

// Get the package directory (parent of scripts/)
const scriptDir = path.dirname(new URL(import.meta.url).pathname);
const packageDir = path.dirname(scriptDir);

const schemaPath = path.join(packageDir, 'config', 'schemas', 'report.schema.json');
const reportsDir = path.join(packageDir, 'workspace', 'reports');
const outSummary = path.join(packageDir, 'workspace', 'summary.md');
const outGate = path.join(packageDir, 'workspace', 'gate.txt');

const mustFiles = {
  'claude-code': path.join(reportsDir, 'claude-code.json'),
  'codex-cli': path.join(reportsDir, 'codex-cli.json'),
  'gemini-cli': path.join(reportsDir, 'gemini-cli.json'),
};

// Use draft-07 mode for better compatibility
const ajv = new Ajv({ strict: false, allErrors: true });
addFormats(ajv);

function die(msg) { console.error(msg); process.exit(1); }

const schema = JSON.parse(await fs.readFile(schemaPath, 'utf8'));
const validate = ajv.compile(schema);

const results = [];
const errors = [];
const reportStatus = {};

// Also check for raw outputs
const rawDir = path.join(packageDir, 'workspace', 'reports', 'raw');
const rawFiles = {};
try {
  const rawEntries = await fs.readdir(rawDir).catch(() => []);
  for (const entry of rawEntries) {
    if (entry.endsWith('.raw.txt')) {
      const toolName = entry.replace('.raw.txt', '');
      rawFiles[toolName] = path.join(rawDir, entry);
    }
  }
} catch (e) {
  console.error('Could not read raw directory:', e.message);
}

for (const [tool, file] of Object.entries(mustFiles)) {
  try {
    const raw = await fs.readFile(file, 'utf8');
    let json = JSON.parse(raw);
    reportStatus[tool] = 'parsed';
    
    // Fix common issues before validation
    // 1. Fix null tests.executed (schema expects boolean)
    if (json.tests && (json.tests.executed === null || json.tests.executed === undefined)) {
      json.tests.executed = false;
    }
    
    // 2. Ensure required fields exist with defaults
    if (!json.tool) json.tool = tool;
    if (!json.model) json.model = 'unknown';
    if (!json.timestamp) json.timestamp = new Date().toISOString();
    if (!json.pr) json.pr = {};
    if (!json.summary && json.error) {
      // If there's an error, use it as summary
      json.summary = `Error: ${json.error}`;
    } else if (!json.summary) {
      json.summary = 'No summary provided';
    }
    if (!json.assumptions) json.assumptions = [];
    if (!json.findings) json.findings = [];
    if (!json.tests) json.tests = { executed: false, command: null, exit_code: null, summary: 'Not executed' };
    if (!json.exit_criteria) json.exit_criteria = { ready_for_pr: false, reasons: [] };
    
    // Try validation after fixes
    if (!validate(json)) {
      // Log validation errors as warnings
      const validationErrors = ajv.errorsText(validate.errors, { separator: '\n- ' });
      errors.push(`Schema validation failed for ${tool}:\n- ${validationErrors}`);
      
      // Check if we have minimum required fields to proceed
      if (!json.findings && !json.summary) {
        errors.push(`CRITICAL: Skipping ${tool} - No usable content (missing both findings and summary)`);
        reportStatus[tool] = 'skipped-invalid';
        continue;
      }
      
      // Mark as having validation issues but still usable
      reportStatus[tool] = 'parsed-with-warnings';
      json._validation_warnings = validationErrors;
    }
    results.push(json);
  } catch (e) {
    reportStatus[tool] = 'failed';
    errors.push(`Missing or unreadable report for ${tool}: ${e.message}`);
    
    // Try to read raw file as fallback
    const rawKey = tool === 'claude-code' ? 'claude-code' : 
                   tool === 'codex-cli' ? 'codex-cli' : 
                   tool === 'gemini-cli' ? 'gemini-cli' : tool;
    
    if (rawFiles[rawKey]) {
      try {
        const rawContent = await fs.readFile(rawFiles[rawKey], 'utf8');
        errors.push(`  Raw output available (${rawContent.length} bytes) - check artifacts for full content`);
        
        // Create a minimal report entry with raw content reference
        results.push({
          tool: tool,
          model: 'unknown',
          summary: `Failed to parse JSON report. Raw output available (${rawContent.length} bytes).`,
          findings: [],
          exit_criteria: { ready_for_pr: false, reasons: ['Failed to parse report'] },
          _hasRawOutput: true,
          _rawLength: rawContent.length
        });
      } catch (rawErr) {
        errors.push(`  Could not read raw file: ${rawErr.message}`);
      }
    }
  }
}

let gate = 'fail';

// Build deterministic aggregate
const byTool = Object.fromEntries(results.map(r => [r.tool, r]));

const allFindings = results.flatMap(r =>
  (r.findings || []).map(f => ({ ...f, _tool: r.tool }))
);

const mustFix = allFindings.filter(f => f.must_fix || f.severity === 'critical' || f.severity === 'high');
const assumptions = results.flatMap(r =>
  (r.assumptions || []).map(a => ({ ...a, _tool: r.tool }))
);

const allReady = results.length === 3
  && results.every(r => r.exit_criteria?.ready_for_pr === true);

if (errors.length === 0 && mustFix.length === 0 && allReady) {
  gate = 'pass';
}

const lines = [];
lines.push(`# Multi‑Model Review Summary`);
lines.push('');
if (errors.length) {
  lines.push('## Validation Errors');
  for (const e of errors) lines.push(`- ${e}`);
  lines.push('');
}
lines.push('## Provider Summaries');
for (const r of results) {
  const status = reportStatus[r.tool] || 'unknown';
  const statusIcon = status === 'parsed' ? '✅' : status === 'failed' ? '⚠️' : '❓';
  lines.push(`### ${statusIcon} ${r.tool} (${r.model})`);
  
  if (r._hasRawOutput) {
    lines.push(`⚠️ JSON parsing failed - raw output available (${r._rawLength} bytes)`);
  }
  
  lines.push(r.summary?.trim() || '_no summary_');
  lines.push('');
}

// Add report status summary
lines.push('## Report Status');
const allTools = Object.keys(mustFiles);
for (const tool of allTools) {
  const status = reportStatus[tool] || 'missing';
  const icon = status === 'parsed' ? '✅' : status === 'failed' ? '❌' : '⚪';
  const rawKey = tool === 'claude-code' ? 'claude-code' : 
                 tool === 'codex-cli' ? 'codex-cli' : 
                 tool === 'gemini-cli' ? 'gemini-cli' : tool;
  const hasRaw = rawFiles[rawKey] ? ' (raw output available)' : '';
  lines.push(`- ${icon} ${tool}: ${status}${hasRaw}`);
}
lines.push('');

lines.push('## Must‑fix (union)');
if (mustFix.length === 0) {
  lines.push('- None');
} else {
  for (const f of mustFix) {
    const locus = [f.file, f.lines].filter(Boolean).join(':');
    lines.push(`- [${f.severity}] (${f._tool}) ${f.category} — ${f.message}${locus ? ` — ${locus}` : ''}`);
    if (f.suggestion) lines.push(`  - Suggestion: ${f.suggestion}`);
    if (Array.isArray(f.evidence) && f.evidence.length) {
      lines.push(`  - Evidence: ${f.evidence.join('; ')}`);
    }
  }
}
lines.push('');

lines.push('## Assumptions with uncertainty');
const uncertain = assumptions.filter(a => a.status === 'uncertain');
if (uncertain.length === 0) {
  lines.push('- None');
} else {
  for (const a of uncertain) {
    lines.push(`- (${a._tool}) ${a.text}`);
    if (a.falsification_step) lines.push(`  - Falsify by: ${a.falsification_step}`);
  }
}
lines.push('');

lines.push(`## Gate: **${gate.toUpperCase()}**`);
lines.push('');

// Add note about accessing raw outputs
if (Object.keys(rawFiles).length > 0) {
  lines.push('💡 **Note**: Raw provider outputs are preserved in the artifacts. Download the artifact to access full unprocessed outputs.');
  lines.push('');
}

lines.push('_This comment was generated by a self‑hosted workflow using subscription/OAuth CLIs only. No API keys were used._');

await fs.writeFile(outSummary, lines.join('\n'));
await fs.writeFile(outGate, gate, 'utf8');

// Exit code mirrors gate (and schema errors)
if (gate === 'pass') process.exit(0);
process.exit(1);