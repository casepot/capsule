#!/usr/bin/env node
/**
 * Context Injector - Provides workspace context files to AI providers
 * 
 * Handles reading and formatting of workspace files (annotated_hunks.txt, diff.patch, etc.)
 * for injection into provider stdin, ensuring all providers have access to the same context.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default class ContextInjector {
  constructor(options = {}) {
    this.packageDir = options.packageDir || path.dirname(__dirname);
    this.workspaceDir = path.join(this.packageDir, 'workspace');
    this.contextDir = path.join(this.workspaceDir, 'context');
    this.verbose = options.verbose || false;
  }

  /**
   * Read a file safely, returning empty string if not found
   */
  async readFileSafe(filePath, defaultContent = '') {
    try {
      return await fs.readFile(filePath, 'utf8');
    } catch (error) {
      if (this.verbose) {
        console.error(`Warning: Could not read ${filePath}: ${error.message}`);
      }
      return defaultContent;
    }
  }

  /**
   * Build the complete context content for provider input
   */
  async buildContext() {
    const sections = [];

    // Enhanced diff with line numbers for citations and full change context
    // Try enhanced_diff.txt first, fall back to annotated_hunks.txt for compatibility
    let enhancedDiff = await this.readFileSafe(
      path.join(this.workspaceDir, 'enhanced_diff.txt'),
      ''
    );
    
    // Fallback to annotated_hunks.txt if enhanced diff doesn't exist
    if (!enhancedDiff || !enhancedDiff.trim()) {
      enhancedDiff = await this.readFileSafe(
        path.join(this.workspaceDir, 'annotated_hunks.txt'),
        '# No diff available\n'
      );
    }
    
    if (enhancedDiff && enhancedDiff.trim()) {
      sections.push('=== ENHANCED DIFF WITH LINE NUMBERS ===');
      sections.push('FORMAT LEGEND:');
      sections.push('  + 123| Added line (new in this version, line 123)');
      sections.push('  -    | Removed line (deleted, no line number)');
      sections.push('    456| Unchanged context line (exists at line 456)');
      sections.push('');
      sections.push(enhancedDiff);
      sections.push('=== END ENHANCED DIFF ===\n');
    }

    // Note: Git diff removed - now included in enhanced diff above

    // PR metadata
    const prJson = await this.readFileSafe(
      path.join(this.contextDir, 'pr.json'),
      '{}'
    );
    if (prJson && prJson !== '{}') {
      sections.push('=== PR METADATA ===');
      sections.push(prJson);
      sections.push('=== END PR METADATA ===\n');
    }

    // List of modified files
    const filesList = await this.readFileSafe(
      path.join(this.contextDir, 'files.txt'),
      ''
    );
    if (filesList && filesList.trim()) {
      sections.push('=== MODIFIED FILES ===');
      sections.push(filesList);
      sections.push('=== END MODIFIED FILES ===\n');
    }

    // Test results if available
    const tests = await this.readFileSafe(
      path.join(this.contextDir, 'tests.txt'),
      ''
    );
    if (tests && tests.trim()) {
      sections.push('=== TEST RESULTS ===');
      sections.push(tests);
      sections.push('=== END TEST RESULTS ===\n');
    }

    return sections.join('\n');
  }

  /**
   * Build shell commands to cat context files (legacy compatibility)
   * This is used when we need to maintain compatibility with existing shell-based commands
   */
  async buildContextCommands() {
    const commands = [];
    
    // Include enhanced diff (or fall back to annotated hunks)
    commands.push('if [ -f "$PACKAGE_DIR/workspace/enhanced_diff.txt" ]; then');
    commands.push('  echo "=== ENHANCED DIFF WITH LINE NUMBERS ==="');
    commands.push('  echo "FORMAT LEGEND:"');
    commands.push('  echo "  + 123| Added line (new in this version, line 123)"');
    commands.push('  echo "  -    | Removed line (deleted, no line number)"');
    commands.push('  echo "    456| Unchanged context line (exists at line 456)"');
    commands.push('  echo');
    commands.push('  cat "$PACKAGE_DIR/workspace/enhanced_diff.txt"');
    commands.push('  echo "=== END ENHANCED DIFF ==="');
    commands.push('  echo');
    commands.push('elif [ -f "$PACKAGE_DIR/workspace/annotated_hunks.txt" ]; then');
    commands.push('  echo "=== ANNOTATED HUNKS (USE FOR LINE CITATIONS) ==="');
    commands.push('  cat "$PACKAGE_DIR/workspace/annotated_hunks.txt"');
    commands.push('  echo "=== END ANNOTATED HUNKS ==="');
    commands.push('  echo');
    commands.push('fi');

    // Include other context files (diff.patch removed - now in enhanced diff)
    const contextFiles = [
      { path: 'context/pr.json', label: 'PR METADATA' },
      { path: 'context/files.txt', label: 'MODIFIED FILES' },
      { path: 'context/tests.txt', label: 'TEST RESULTS' }
    ];

    for (const { path: filePath, label } of contextFiles) {
      commands.push(`if [ -f "$PACKAGE_DIR/workspace/${filePath}" ]; then`);
      commands.push(`  echo "=== ${label} ==="`);
      commands.push(`  cat "$PACKAGE_DIR/workspace/${filePath}"`);
      commands.push(`  echo "=== END ${label} ==="`);
      commands.push('  echo');
      commands.push('fi');
    }

    return commands.join('\n');
  }

  /**
   * Check if required context files exist
   */
  async validateContext() {
    const issues = [];
    
    // Check for critical files
    const annotatedHunksPath = path.join(this.workspaceDir, 'annotated_hunks.txt');
    try {
      const stats = await fs.stat(annotatedHunksPath);
      if (stats.size === 0) {
        issues.push('annotated_hunks.txt is empty');
      }
    } catch (error) {
      issues.push('annotated_hunks.txt is missing (required for line citations)');
    }

    const diffPath = path.join(this.contextDir, 'diff.patch');
    try {
      const stats = await fs.stat(diffPath);
      if (stats.size === 0) {
        issues.push('diff.patch is empty');
      }
    } catch (error) {
      issues.push('diff.patch is missing');
    }

    return {
      valid: issues.length === 0,
      issues
    };
  }
}

// Allow direct execution for testing
if (import.meta.url === `file://${process.argv[1]}`) {
  const injector = new ContextInjector({ verbose: true });
  
  if (process.argv.includes('--validate')) {
    const validation = await injector.validateContext();
    console.log('Context validation:', validation);
  } else if (process.argv.includes('--commands')) {
    const commands = await injector.buildContextCommands();
    console.log(commands);
  } else {
    const context = await injector.buildContext();
    console.log(context);
  }
}