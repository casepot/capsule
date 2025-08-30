#!/usr/bin/env node
/**
 * Execute Provider - Safely executes provider commands without shell injection risks
 * 
 * This replaces the unsafe `bash -c "$CMD"` pattern with proper process spawning,
 * eliminating command injection vulnerabilities while providing consistent context
 * to all providers.
 */

import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import CommandBuilder from './command-builder.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default class ProviderExecutor {
  constructor(options = {}) {
    this.packageDir = options.packageDir || path.dirname(__dirname);
    this.verbose = options.verbose || false;
    this.dryRun = options.dryRun || false;
    this.commandBuilder = new CommandBuilder({
      packageDir: this.packageDir,
      verbose: this.verbose
    });
  }

  /**
   * Execute a provider command safely
   */
  async execute(provider, options = {}) {
    // Build the structured command
    const cmd = await this.commandBuilder.buildCommand(provider, options);
    
    if (!cmd) {
      throw new Error(`Provider ${provider} is disabled or not configured`);
    }

    if (this.verbose) {
      console.error(`Executing ${provider}:`, {
        command: cmd.command,
        args: cmd.args?.map(a => a.length > 50 ? a.substring(0, 50) + '...' : a),
        workingDirectory: cmd.workingDirectory,
        hasStdin: !!cmd.stdin,
        outputFile: cmd.outputFile
      });
    }

    if (this.dryRun) {
      console.log('DRY RUN - Would execute:', cmd);
      return { exitCode: 0, stdout: '', stderr: '' };
    }

    // Special handling for different providers
    if (provider === 'codex') {
      return await this.executeCodex(cmd);
    } else {
      return await this.executeWithStdin(cmd);
    }
  }

  /**
   * Execute command with stdin input (Claude, Gemini)
   */
  async executeWithStdin(cmd) {
    return new Promise((resolve, reject) => {
      // Prepare arguments, replacing STDIN_CONTENT placeholder
      const args = cmd.args.map(arg => 
        arg === 'STDIN_CONTENT' ? '-' : arg
      ).filter(arg => arg !== 'STDIN_CONTENT');

      // Spawn the process with large buffer for output (10MB)
      // Sanitize environment variables (defense-in-depth)
      // Shell scripts also do this, but we add an extra layer here
      const sanitizedEnv = { ...(cmd.env || {}) };
      const sensitiveKeys = [
        'GH_TOKEN', 
        'GITHUB_TOKEN', 
        'ANTHROPIC_API_KEY', 
        'OPENAI_API_KEY', 
        'GEMINI_API_KEY',
        'ANTHROPIC_AUTH_TOKEN'
      ];
      
      for (const key of sensitiveKeys) {
        delete sanitizedEnv[key];
      }
      
      const proc = spawn(cmd.command, args, {
        cwd: cmd.workingDirectory,
        env: sanitizedEnv,
        stdio: ['pipe', 'pipe', 'pipe'],
        maxBuffer: 10 * 1024 * 1024 // Note: maxBuffer is ignored by spawn (only used by exec)
      });

      let stdout = '';
      let stderr = '';
      let timedOut = false;

      // Set up timeout if specified
      let timeoutHandle;
      if (cmd.timeout) {
        timeoutHandle = setTimeout(() => {
          timedOut = true;
          proc.kill('SIGTERM');
          setTimeout(() => {
            if (!proc.killed) {
              proc.kill('SIGKILL');
            }
          }, 5000);
        }, cmd.timeout * 1000);
      }

      // Provide stdin if specified, or close it
      if (cmd.stdin) {
        proc.stdin.write(cmd.stdin);
        proc.stdin.end();
      } else {
        // Close stdin if no content to prevent hanging
        proc.stdin.end();
      }

      // Collect stdout
      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      // Collect stderr
      proc.stderr.on('data', (data) => {
        stderr += data.toString();
        if (this.verbose) {
          console.error(`[${cmd.command}]`, data.toString().trim());
        }
      });

      // Handle process exit
      proc.on('exit', async (code, signal) => {
        if (timeoutHandle) {
          clearTimeout(timeoutHandle);
        }

        if (timedOut) {
          reject(new Error(`Command timed out after ${cmd.timeout} seconds`));
          return;
        }

        try {
          // Always save raw output (stdout and stderr) for debugging
          const combinedOutput = stdout || stderr || 'No output received';
          await this.saveRawOutput(cmd, combinedOutput);
          
          // Process the output
          if (code === 0 || stdout.trim()) {
            // Process and normalize the output
            await this.processOutput(cmd, stdout);
          } else {
            // Write error fallback
            await this.writeErrorOutput(cmd, stderr || 'Command failed');
          }

          resolve({
            exitCode: code || 0,
            stdout,
            stderr,
            signal
          });
        } catch (error) {
          reject(error);
        }
      });

      // Handle process errors
      proc.on('error', (error) => {
        if (timeoutHandle) {
          clearTimeout(timeoutHandle);
        }
        reject(error);
      });
    });
  }

  /**
   * Execute Codex with special handling
   */
  async executeCodex(cmd) {
    // Codex needs the prompt as an argument, not stdin
    return new Promise((resolve, reject) => {
      // Apply same environment sanitization
      const sanitizedEnv = { ...cmd.env };
      const sensitiveKeys = [
        'GH_TOKEN', 
        'GITHUB_TOKEN', 
        'ANTHROPIC_API_KEY', 
        'OPENAI_API_KEY', 
        'GEMINI_API_KEY',
        'ANTHROPIC_AUTH_TOKEN'
      ];
      
      for (const key of sensitiveKeys) {
        delete sanitizedEnv[key];
      }
      
      const proc = spawn(cmd.command, cmd.args, {
        cwd: cmd.workingDirectory,
        env: sanitizedEnv,
        stdio: ['ignore', 'pipe', 'pipe'],
        maxBuffer: 10 * 1024 * 1024 // 10MB to handle large review outputs
      });

      let stdout = '';
      let stderr = '';
      let timedOut = false;

      // Set up timeout
      let timeoutHandle;
      if (cmd.timeout) {
        timeoutHandle = setTimeout(() => {
          timedOut = true;
          proc.kill('SIGTERM');
        }, cmd.timeout * 1000);
      }

      // Collect output
      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
        if (this.verbose) {
          console.error(`[codex]`, data.toString().trim());
        }
      });

      // Handle exit
      proc.on('exit', async (code, signal) => {
        if (timeoutHandle) {
          clearTimeout(timeoutHandle);
        }

        if (timedOut) {
          reject(new Error(`Codex timed out after ${cmd.timeout} seconds`));
          return;
        }

        try {
          // Codex writes to a file, need to read and normalize it
          if (cmd.rawOutputFile) {
            await this.processCodexOutput(cmd);
          }

          resolve({
            exitCode: code || 0,
            stdout,
            stderr,
            signal
          });
        } catch (error) {
          reject(error);
        }
      });

      proc.on('error', (error) => {
        if (timeoutHandle) {
          clearTimeout(timeoutHandle);
        }
        reject(error);
      });
    });
  }

  /**
   * Validate output path to prevent directory traversal
   */
  validateOutputPath(outputPath) {
    // Reject paths containing directory traversal
    if (outputPath.includes('..')) {
      throw new Error(`Invalid output path contains directory traversal: ${outputPath}`);
    }
    
    // Ensure path is within workspace/reports directory
    const resolvedPath = path.resolve(outputPath);
    const expectedDir = path.resolve(this.packageDir, 'workspace/reports');
    
    // Use path.relative for secure validation
    const relative = path.relative(expectedDir, resolvedPath);
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      throw new Error(`Output path outside allowed directory: ${outputPath}`);
    }
    
    return resolvedPath;
  }

  /**
   * Save raw output to file for debugging/audit
   */
  async saveRawOutput(cmd, output) {
    // Determine raw output filename based on the tool
    const toolName = cmd.env?.TOOL || 'unknown';
    let rawFileName;
    
    switch (toolName) {
      case 'claude-code':
        rawFileName = 'claude-code.raw.txt';
        break;
      case 'codex-cli':
        // Codex already has its own raw file handling
        return;
      case 'gemini-cli':
        rawFileName = 'gemini-cli.raw.txt';
        break;
      default:
        rawFileName = `${toolName}.raw.txt`;
    }
    
    const rawDir = path.join(this.packageDir, 'workspace', 'reports', 'raw');
    const rawPath = path.join(rawDir, rawFileName);
    
    try {
      // Create raw directory if it doesn't exist
      await fs.mkdir(rawDir, { recursive: true });
      
      // Save the raw output
      await fs.writeFile(rawPath, output);
      
      if (this.verbose) {
        console.error(`Raw output saved to ${rawPath} (${output.length} bytes)`);
      }
    } catch (error) {
      console.error(`Failed to save raw output: ${error.message}`);
    }
  }

  /**
   * Process and normalize provider output
   */
  async processOutput(cmd, output) {
    // Normalize the JSON output
    const normalized = await this.normalizeJson(output);
    
    // Write to output file
    const validatedPath = this.validateOutputPath(cmd.outputFile);
    await fs.mkdir(path.dirname(validatedPath), { recursive: true });
    await fs.writeFile(validatedPath, normalized);
    
    if (this.verbose) {
      console.error(`Output written to ${cmd.outputFile}`);
    }
  }

  /**
   * Process Codex output from file
   */
  async processCodexOutput(cmd) {
    try {
      // Read the raw output file
      const rawOutput = await fs.readFile(cmd.rawOutputFile, 'utf8');
      
      // Copy raw file to the raw directory for consistency
      const rawDir = path.join(this.packageDir, 'workspace', 'reports', 'raw');
      const rawPath = path.join(rawDir, 'codex-cli.raw.txt');
      await fs.mkdir(rawDir, { recursive: true });
      await fs.copyFile(cmd.rawOutputFile, rawPath);
      
      // Normalize it
      const normalized = await this.normalizeJson(rawOutput);
      
      // Write to final location
      const validatedPath = this.validateOutputPath(cmd.outputFile);
      await fs.writeFile(validatedPath, normalized);
      
      // Keep original raw file - don't delete it anymore
      // await fs.unlink(cmd.rawOutputFile).catch(() => {});
      
      if (this.verbose) {
        console.error(`Codex output processed and written to ${cmd.outputFile}`);
        console.error(`Raw output preserved at ${rawPath}`);
      }
    } catch (error) {
      await this.writeErrorOutput(cmd, error.message);
    }
  }

  /**
   * Normalize JSON output from providers
   */
  async normalizeJson(input) {
    // Use the actual normalize-json.js script that handles all edge cases
    const normalizePath = path.join(this.packageDir, 'scripts', 'normalize-json.js');
    
    return new Promise((resolve, reject) => {
      const proc = spawn('node', [normalizePath], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          // Pass environment for normalize-json.js to use
          TOOL: process.env.TOOL || 'unknown',
          MODEL: process.env.MODEL || 'unknown',
          PR_NUMBER: process.env.PR_NUMBER || '',
          PR_REPO: process.env.PR_REPO || '',
          HEAD_SHA: process.env.HEAD_SHA || '',
          PR_BRANCH: process.env.PR_BRANCH || '',
          RUN_URL: process.env.RUN_URL || ''
        }
      });
      
      let stdout = '';
      let stderr = '';
      
      // Send input to normalize-json.js
      proc.stdin.write(input);
      proc.stdin.end();
      
      // Collect stdout (the normalized JSON)
      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });
      
      // Collect stderr (error messages)
      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });
      
      // Handle process exit
      proc.on('exit', (code) => {
        if (code === 0) {
          // Success - return the normalized JSON
          resolve(stdout);
        } else {
          // Normalization failed - create error JSON
          if (this.verbose && stderr) {
            console.error('normalize-json.js error:', stderr);
          }
          
          const errorJson = {
            tool: process.env.TOOL || 'unknown',
            model: process.env.MODEL || 'unknown',
            timestamp: new Date().toISOString(),
            error: `Failed to normalize output: ${stderr || 'Unknown error'}`,
            raw_output: input.substring(0, 1000),
            findings: [],
            exit_criteria: {
              ready_for_pr: false,
              reasons: ['Failed to generate valid review']
            }
          };
          
          resolve(JSON.stringify(errorJson, null, 2));
        }
      });
      
      // Handle process errors
      proc.on('error', (error) => {
        if (this.verbose) {
          console.error('Failed to spawn normalize-json.js:', error);
        }
        
        // Can't spawn normalizer - return error JSON
        const errorJson = {
          tool: process.env.TOOL || 'unknown',
          model: process.env.MODEL || 'unknown',
          timestamp: new Date().toISOString(),
          error: `Failed to run normalizer: ${error.message}`,
          raw_output: input.substring(0, 1000),
          findings: [],
          exit_criteria: {
            ready_for_pr: false,
            reasons: ['Failed to normalize output']
          }
        };
        
        resolve(JSON.stringify(errorJson, null, 2));
      });
    });
  }

  /**
   * Write error output
   */
  async writeErrorOutput(cmd, errorMessage) {
    const errorJson = {
      tool: cmd.env?.TOOL || 'unknown',
      model: cmd.env?.MODEL || 'unknown',
      timestamp: new Date().toISOString(),
      error: errorMessage,
      findings: [],
      exit_criteria: {
        ready_for_pr: false,
        reasons: ['Provider execution failed']
      }
    };

    const validatedPath = this.validateOutputPath(cmd.outputFile);
    await fs.mkdir(path.dirname(validatedPath), { recursive: true });
    await fs.writeFile(validatedPath, JSON.stringify(errorJson, null, 2));
  }
}

// Allow direct execution
if (import.meta.url === `file://${process.argv[1]}`) {
  const provider = process.argv[2];
  
  if (!provider || !['claude', 'codex', 'gemini'].includes(provider)) {
    console.error('Usage: execute-provider.js <claude|codex|gemini> [options]');
    console.error('Options:');
    console.error('  --verbose    Show detailed execution info');
    console.error('  --dry-run    Show what would be executed without running');
    console.error('  --timeout N  Override timeout in seconds');
    process.exit(1);
  }

  // Parse options
  const options = {
    verbose: process.argv.includes('--verbose'),
    dryRun: process.argv.includes('--dry-run')
  };

  // Check for timeout override
  const timeoutIndex = process.argv.indexOf('--timeout');
  let executionOptions = {};
  if (timeoutIndex !== -1 && process.argv[timeoutIndex + 1]) {
    executionOptions.timeout = parseInt(process.argv[timeoutIndex + 1]);
  }

  // Execute
  const executor = new ProviderExecutor(options);
  
  try {
    const result = await executor.execute(provider, executionOptions);
    
    if (options.verbose) {
      console.error('Execution result:', {
        exitCode: result.exitCode,
        stdoutLength: result.stdout?.length,
        stderrLength: result.stderr?.length
      });
    }
    
    process.exit(result.exitCode);
  } catch (error) {
    console.error(`Failed to execute ${provider}:`, error.message);
    process.exit(1);
  }
}