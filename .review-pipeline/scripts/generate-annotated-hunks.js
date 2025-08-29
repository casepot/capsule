#!/usr/bin/env node
/**
 * Generate Annotated Hunks (New Version) with absolute new-file line numbers
 *
 * Input:  .review-pipeline/workspace/context/diff.patch (unified diff)
 * Output: .review-pipeline/workspace/annotated_hunks.txt
 *
 * For each file and hunk, prints:
 *   file: <path>
 *   @@ -<oldStart>,<oldCount> +<newStart>,<newCount> @@
 *   After (new):
 *   <newLine>| <content>
 *   ... (only ' ' and '+' lines; '-' lines are omitted because they don't exist in new file)
 */

import fs from 'node:fs/promises';
import path from 'node:path';

const workspaceDir = path.resolve('.review-pipeline/workspace');
const ctxDir = path.join(workspaceDir, 'context');
const diffPath = path.join(ctxDir, 'diff.patch');
const outPath = path.join(workspaceDir, 'annotated_hunks.txt');

function parseHunkHeader(line) {
  // @@ -OLD_START,OLD_COUNT +NEW_START,NEW_COUNT @@
  const m = line.match(/^@@\s-([0-9]+)(?:,([0-9]+))?\s\+([0-9]+)(?:,([0-9]+))?\s@@/);
  if (!m) return null;
  const oldStart = parseInt(m[1], 10);
  const oldCount = m[2] ? parseInt(m[2], 10) : 1;
  const newStart = parseInt(m[3], 10);
  const newCount = m[4] ? parseInt(m[4], 10) : 1;
  return { oldStart, oldCount, newStart, newCount };
}

function stripMarker(line) {
  // Remove leading diff marker and one space: ' ', '+', '-'
  if (line.length === 0) return line;
  const marker = line[0];
  if (marker === ' ' || marker === '+' || marker === '-') {
    return line.length >= 2 && line[1] === ' ' ? line.slice(2) : line.slice(1);
  }
  return line;
}

async function main() {
  try {
    const diffText = await fs.readFile(diffPath, 'utf8');
    const lines = diffText.split(/\r?\n/);
    let currentFile = null; // new file path (from +++)
    let newLine = 0;
    let oldLine = 0;
    let inHunk = false;
    let output = [];

    const push = (s='') => output.push(s);

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Detect file headers
      if (line.startsWith('+++ ')) {
        const m = line.match(/^\+\+\+\s([ab]\/(.*)|\/(.*)|(.+))/);
        if (m) {
          // Extract path after b/ if present
          let p = line.slice(4).trim();
          if (p.startsWith('b/')) p = p.slice(2);
          if (p === '/dev/null') { currentFile = null; continue; }
          currentFile = p;
          // Separate files with a blank line
          push('');
          push(`file: ${currentFile}`);
          inHunk = false;
        }
        continue;
      }

      // Hunk header
      if (line.startsWith('@@')) {
        const hdr = parseHunkHeader(line);
        if (!hdr || !currentFile) { inHunk = false; continue; }
        ({ oldStart: oldLine, newStart: newLine } = hdr);
        push(line); // original @@ header for orientation
        push('After (new):');
        inHunk = true;
        continue;
      }

      if (!inHunk || !currentFile) {
        continue;
      }

      // Hunk body lines
      if (line.startsWith(' ')) {
        // context: present in new file
        const content = stripMarker(line);
        push(`${newLine}| ${content}`);
        newLine++; oldLine++;
      } else if (line.startsWith('+')) {
        // added: present in new file
        const content = stripMarker(line);
        push(`${newLine}| ${content}`);
        newLine++;
      } else if (line.startsWith('-')) {
        // removed: not in new file; advance old only
        oldLine++;
      } else if (line.startsWith('\\ No newline at end of file')) {
        // ignore
      } else {
        // Unknown line inside hunk; print as a comment (rare)
        push(`# ${line}`);
      }
    }

    const outText = output.join('\n').trim();
    await fs.mkdir(workspaceDir, { recursive: true });
    await fs.writeFile(outPath, outText + '\n', 'utf8');
    console.log(`Annotated hunks written to ${outPath}`);
  } catch (err) {
    console.error(`Failed to generate annotated hunks: ${err.message}`);
    process.exit(1);
  }
}

main().catch(e => { console.error(e); process.exit(1); });

