#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';
import CriteriaBuilder from './criteria-builder.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageDir = path.dirname(__dirname);

/**
 * Generate provider CLI commands based on configuration
 */
async function generateProviderCommand(provider, options = {}) {
  const configPath = path.join(packageDir, 'config', 'pipeline.config.json');
  const manifestPath = path.join(packageDir, 'config', 'providers', `${provider}.manifest.json`);
  
  try {
    // Load configuration
    const config = JSON.parse(await fs.readFile(configPath, 'utf8'));
    const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    
    // Build project-specific criteria if available
    let projectCriteriaPath = null;
    if (!options.skipProjectCriteria) {
      const criteriaBuilder = new CriteriaBuilder({
        projectRoot: options.projectRoot || process.cwd(),
        verbose: options.verbose || false
      });
      
      const projectCriteria = await criteriaBuilder.build();
      if (projectCriteria) {
        // Save to cache for use in command
        projectCriteriaPath = await criteriaBuilder.saveToCache(projectCriteria);
      }
    }
    
    // Check if provider is enabled
    if (config.providers[provider]?.enabled === false) {
      return null; // Provider disabled
    }
    
    const providerConfig = config.providers[provider] || {};
    const timeout = providerConfig.timeout_override || config.execution?.timeout_seconds || 120;
    
    // Build command based on provider
    let command = [];
    let preCommand = [];
    let postCommand = [];
    
    switch (provider) {
      case 'claude': {
        // Get CLI command
        const cliCmd = manifest.cli.command;
        
        // Build flags
        const model = providerConfig.model || 'sonnet';
        const flags = providerConfig.flags || {};
        
        command.push(cliCmd);
        
        // Build prompt with optional project criteria
        // Wrap substitution in quotes so entire prompt is a single argument
        let promptCmd = '"$(cat "$PACKAGE_DIR/prompts/review.claude.md"; echo; cat "$PACKAGE_DIR/prompts/review.core.md"';
        if (projectCriteriaPath) {
          promptCmd += `; echo; cat "${projectCriteriaPath}"`;
        }
        promptCmd += ')"';
        
        command.push('-p', promptCmd);
        command.push('--model', model);
        
        if (flags.permission_mode) {
          command.push('--permission-mode', flags.permission_mode);
        }
        if (flags.output_format) {
          command.push('--output-format', flags.output_format);
        }
        
        // Add additional flags
        if (providerConfig.additional_flags) {
          command.push(...providerConfig.additional_flags);
        }
        
        // Add normalization
        postCommand.push('| node "$PACKAGE_DIR/scripts/normalize-json.js"');
        postCommand.push('> "$PACKAGE_DIR/workspace/reports/claude-code.json"');
        
        break;
      }
      
      case 'codex': {
        const cliCmd = manifest.cli.command;
        const model = providerConfig.model || 'gpt-5';
        const reasoning = providerConfig.reasoning_effort || 'low';
        const sandbox = providerConfig.sandbox_mode || 'read-only';
        const workdir = providerConfig.working_directory || '.';
        
        command.push(cliCmd);
        command.push('exec');
        command.push('--output-last-message', '"$PACKAGE_DIR/workspace/reports/codex-cli.raw.txt"');
        command.push('-s', sandbox);
        command.push('-C', workdir);
        
        // Add reasoning effort
        command.push('-c', `model_reasoning_effort="${reasoning}"`);
        
        // Add additional config
        if (providerConfig.additional_config) {
          for (const [key, value] of Object.entries(providerConfig.additional_config)) {
            command.push('-c', `${key}="${value}"`);
          }
        }
        
        // Add prompt with optional project criteria
        let codexPrompt = '"$(cat "$PACKAGE_DIR/prompts/review.codex.md"; echo; cat "$PACKAGE_DIR/prompts/review.core.md"';
        if (projectCriteriaPath) {
          codexPrompt += `; echo; cat "${projectCriteriaPath}"`;
        }
        codexPrompt += ')"';
        command.push(codexPrompt);
        
        // Post-processing
        postCommand.push('>/dev/null 2>&1 &&');
        postCommand.push('cat "$PACKAGE_DIR/workspace/reports/codex-cli.raw.txt" | node "$PACKAGE_DIR/scripts/normalize-json.js" > "$PACKAGE_DIR/workspace/reports/codex-cli.json" &&');
        postCommand.push('rm -f "$PACKAGE_DIR/workspace/reports/codex-cli.raw.txt"');
        
        break;
      }
      
      case 'gemini': {
        const cliCmd = manifest.cli.command;
        const model = providerConfig.model || 'gemini-2.5-pro';
        const flags = providerConfig.flags || {};
        
        // Gemini needs input via echo
        preCommand.push('echo "$(cat "$PACKAGE_DIR/prompts/review.gemini.md"; echo;');
        preCommand.push('echo \'CRITICAL: Output ONLY the JSON object, no markdown code fences or other text.\';');
        preCommand.push('cat "$PACKAGE_DIR/prompts/review.core.md"');
        if (projectCriteriaPath) {
          preCommand.push(`; echo; cat "${projectCriteriaPath}"`);
        }
        preCommand.push(')" |');
        
        // Environment variable
        preCommand.push('GEMINI_API_KEY=""');
        
        command.push(cliCmd);
        command.push('-m', model);
        command.push('-p');
        
        // Add optional flags
        if (flags.sandbox) {
          command.push('-s');
        }
        if (flags.yolo) {
          command.push('-y');
        }
        if (flags.all_files) {
          command.push('-a');
        }
        
        // Add additional flags
        if (providerConfig.additional_flags) {
          command.push(...providerConfig.additional_flags);
        }
        
        // Add normalization
        postCommand.push('2>/dev/null');
        postCommand.push('| node "$PACKAGE_DIR/scripts/normalize-json.js"');
        postCommand.push('> "$PACKAGE_DIR/workspace/reports/gemini-cli.json"');
        
        break;
      }
      
      default:
        throw new Error(`Unknown provider: ${provider}`);
    }
    
    // Build full command with timeout
    let fullCommand = '';
    
    if (options.includeTimeout !== false) {
      fullCommand = `timeout ${timeout} `;
    }
    
    if (preCommand.length > 0) {
      fullCommand += `(${preCommand.join(' ')} `;
    }
    
    fullCommand += command.join(' ');
    
    if (postCommand.length > 0) {
      fullCommand += ` ${postCommand.join(' ')}`;
    }
    
    if (preCommand.length > 0) {
      fullCommand += ')';
    }
    
    // Add error fallback
    const errorJson = {
      tool: `${provider}-${provider === 'claude' ? 'code' : 'cli'}`,
      model: providerConfig.model || 'error',
      error: `${provider} error`,
      findings: [],
      must_fix: [],
      exit_criteria: { ready_for_pr: false }
    };
    
    fullCommand += ` || echo '${JSON.stringify(errorJson)}' > "$PACKAGE_DIR/workspace/reports/${provider}-${provider === 'claude' ? 'code' : 'cli'}.json"`;
    
    return fullCommand;
    
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.error(`Configuration or manifest not found for ${provider}`);
    } else {
      console.error(`Error generating command for ${provider}:`, error.message);
    }
    return null;
  }
}

/**
 * CLI usage
 */
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const provider = process.argv[2];
  const includeTimeout = process.argv[3] !== '--no-timeout';
  
  if (!provider) {
    console.error('Usage: generate-provider-command.js <provider> [--no-timeout]');
    process.exit(1);
  }
  
  try {
    const command = await generateProviderCommand(provider, { includeTimeout });
    if (command) {
      console.log(command);
    } else {
      console.error(`Provider ${provider} is disabled or not found`);
      process.exit(1);
    }
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

export { generateProviderCommand };
