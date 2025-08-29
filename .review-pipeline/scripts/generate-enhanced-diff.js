#!/usr/bin/env node
/**
 * Generate Enhanced Annotated Diff
 * 
 * Creates a unified diff format that shows:
 * - Removed lines (- prefix, no line number)
 * - Added lines (+ prefix, with line number)
 * - Context lines (space prefix, with line number)
 * 
 * Input:  .review-pipeline/workspace/context/diff.patch (unified diff)
 * Output: .review-pipeline/workspace/enhanced_diff.txt
 * 
 * Format:
 *   file: <path>
 *   @@ -<oldStart>,<oldCount> +<newStart>,<newCount> @@
 *   + 123| added line content
 *   - | removed line content
 *     456| unchanged context line
 */

import fs from 'node:fs/promises';
import path from 'node:path';

const workspaceDir = path.resolve('.review-pipeline/workspace');
const ctxDir = path.join(workspaceDir, 'context');
const diffPath = path.join(ctxDir, 'diff.patch');
const outPath = path.join(workspaceDir, 'enhanced_diff.txt');

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

function formatLine(marker, lineNum, content) {
  if (marker === '-') {
    // Removed lines don't have line numbers in the new file
    return `-    | ${content}`;
  } else if (marker === '+') {
    // Added lines get their line number with + prefix
    const numStr = String(lineNum).padStart(4, ' ');
    return `+${numStr}| ${content}`;
  } else {
    // Context lines (unchanged) get their line number with space prefix
    const numStr = String(lineNum).padStart(4, ' ');
    return ` ${numStr}| ${content}`;
  }
}

async function main() {
  try {
    const diffText = await fs.readFile(diffPath, 'utf8');
    const lines = diffText.split(/\r?\n/);
    
    let output = [];
    let currentFile = null;
    let newLineNum = 0;
    let inHunk = false;
    let seenFirstDiff = false;
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      // Skip git metadata at the beginning (From, Date, Subject, etc.)
      if (!seenFirstDiff && !line.startsWith('diff --git ')) {
        continue;
      }
      
      // File header (diff --git a/file b/file)
      if (line.startsWith('diff --git ')) {
        seenFirstDiff = true;
        // Extract the file path from the b/ part
        const match = line.match(/^diff --git a\/.* b\/(.+)$/);
        if (match) {
          currentFile = match[1];
          // Don't output the diff --git line itself, we'll output when we see +++
          continue;
        }
      }
      
      // Handle --- lines to identify deleted files
      if (line.startsWith('--- ')) {
        const match = line.match(/^--- a\/(.+)$/);
        if (match && match[1] !== '/dev/null') {
          // This will be used if the file is deleted (when +++ is /dev/null)
          const oldFile = match[1];
          // Check if next line is +++ /dev/null (file deletion)
          if (i + 1 < lines.length && lines[i + 1] === '+++ /dev/null') {
            if (output.length > 0) {
              output.push('');  // Empty line separator
            }
            output.push(`file: ${oldFile} (deleted)`);
            currentFile = oldFile;  // Track for the deletion hunks
          }
        }
        continue;
      }
      
      // Skip index, mode lines
      if (line.startsWith('index ') || 
          line.startsWith('new file mode') || 
          line.startsWith('deleted file mode')) {
        continue;
      }
      
      // New file path (+++ b/path)
      if (line.startsWith('+++ ')) {
        const match = line.match(/^\+\+\+ b\/(.+)$/);
        if (match) {
          const newFile = match[1];
          if (newFile !== '/dev/null') {
            currentFile = newFile;
            // Add a separator between files if not the first one
            if (output.length > 0 && !output[output.length - 1].startsWith('file:')) {
              output.push('');  // Empty line separator
            }
            output.push(`file: ${currentFile}`);
          } else {
            // File is being deleted
            currentFile = null;
          }
        }
        continue;
      }
      
      // Hunk header
      if (line.startsWith('@@')) {
        const hunk = parseHunkHeader(line);
        if (hunk && currentFile) {
          output.push(line); // Keep the @@ line as-is
          newLineNum = hunk.newStart;
          inHunk = true;
        }
        continue;
      }
      
      // Process diff lines within a hunk
      if (inHunk && currentFile) {
        if (line.length === 0) {
          // Empty line in diff
          output.push(formatLine(' ', newLineNum, ''));
          newLineNum++;
        } else {
          const marker = line[0];
          const content = line.substring(1);
          
          if (marker === '-') {
            // Removed line - no line number in new file
            output.push(formatLine('-', null, content));
          } else if (marker === '+') {
            // Added line
            output.push(formatLine('+', newLineNum, content));
            newLineNum++;
          } else if (marker === ' ') {
            // Context line (unchanged)
            output.push(formatLine(' ', newLineNum, content));
            newLineNum++;
          } else if (marker === '\\') {
            // "\ No newline at end of file" - skip
            continue;
          } else {
            // Not part of the diff anymore (shouldn't happen in well-formed diff)
            inHunk = false;
            // Process this line again as a potential new file header
            i--;
          }
        }
      }
    }
    
    // Write the enhanced diff
    await fs.mkdir(path.dirname(outPath), { recursive: true });
    await fs.writeFile(outPath, output.join('\n'));
    
    console.log(`Enhanced diff written to: ${outPath}`);
    console.log(`Total lines: ${output.length}`);
    
    // Also create a symlink for backward compatibility
    const legacyPath = path.join(workspaceDir, 'annotated_hunks.txt');
    try {
      await fs.unlink(legacyPath);
    } catch {}
    await fs.symlink('enhanced_diff.txt', legacyPath);
    console.log(`Symlink created: annotated_hunks.txt -> enhanced_diff.txt`);
    
  } catch (error) {
    console.error('Failed to generate enhanced diff:', error);
    process.exit(1);
  }
}

main();