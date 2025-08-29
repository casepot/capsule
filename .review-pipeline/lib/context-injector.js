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

    // Critical: Annotated hunks for line number citations
    const annotatedHunks = await this.readFileSafe(
      path.join(this.workspaceDir, 'annotated_hunks.txt'),
      '# No annotated hunks available\n'
    );
    if (annotatedHunks && annotatedHunks.trim()) {
      sections.push('=== ANNOTATED HUNKS (USE FOR LINE CITATIONS) ===');
      sections.push(annotatedHunks);
      sections.push('=== END ANNOTATED HUNKS ===\n');
    }

    // Git diff for understanding changes
    const diff = await this.readFileSafe(
      path.join(this.contextDir, 'diff.patch'),
      '# No diff available\n'
    );
    if (diff && diff.trim() && diff !== '# No diff available') {
      sections.push('=== GIT DIFF ===');
      sections.push(diff);
      sections.push('=== END GIT DIFF ===\n');
    }

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
    
    // Always include annotated hunks first (most important)
    commands.push('if [ -f "$PACKAGE_DIR/workspace/annotated_hunks.txt" ]; then');
    commands.push('  echo "=== ANNOTATED HUNKS (USE FOR LINE CITATIONS) ==="');
    commands.push('  cat "$PACKAGE_DIR/workspace/annotated_hunks.txt"');
    commands.push('  echo "=== END ANNOTATED HUNKS ==="');
    commands.push('  echo');
    commands.push('fi');

    // Include other context files
    const contextFiles = [
      { path: 'context/diff.patch', label: 'GIT DIFF' },
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