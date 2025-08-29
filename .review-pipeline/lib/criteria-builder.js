#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageDir = path.dirname(__dirname);

/**
 * Project Criteria Builder
 * 
 * Builds project-specific review criteria prompts from:
 * 1. .review-criteria.md file (structured markdown)
 * 2. .reviewrc.json custom_prompts section
 * 
 * Generates a prompt fragment that gets appended to the core review prompt
 */
export class CriteriaBuilder {
  constructor(options = {}) {
    this.options = {
      projectRoot: process.cwd(),
      criteriaFile: '.review-criteria.md',
      configFile: '.reviewrc.json',
      cacheDir: path.join(packageDir, 'workspace', '.cache'),
      verbose: false,
      ...options
    };
    
    this.criteria = null;
    this.config = null;
  }

  /**
   * Build project criteria prompt
   */
  async build() {
    try {
      // Try to load criteria file first
      const criteriaPrompt = await this.loadCriteriaFile();
      if (criteriaPrompt) {
        return criteriaPrompt;
      }
      
      // Fall back to config-based criteria
      const configPrompt = await this.buildFromConfig();
      if (configPrompt) {
        return configPrompt;
      }
      
      return null; // No project-specific criteria
      
    } catch (error) {
      if (this.options.verbose) {
        console.error('Error building project criteria:', error.message);
      }
      return null;
    }
  }

  /**
   * Load and process .review-criteria.md file
   */
  async loadCriteriaFile() {
    const criteriaPath = path.join(this.options.projectRoot, this.options.criteriaFile);
    
    try {
      const content = await fs.readFile(criteriaPath, 'utf8');
      
      // Validate structure (must have at least one recognized section)
      const validSections = [
        '<project_context>',
        '<additional_review_dimensions>',
        '<critical_paths>',
        '<project_standards>',
        '<compliance_requirements>',
        '<zero_tolerance_issues>',
        '<custom_checks>'
      ];
      
      const hasValidSection = validSections.some(section => content.includes(section));
      if (!hasValidSection) {
        throw new Error(`${this.options.criteriaFile} must contain at least one valid section: ${validSections.join(', ')}`);
      }
      
      // Wrap in a project-specific section for the prompt
      const prompt = `
<project_specific_criteria>
This project has defined specific review criteria that must be evaluated in addition to the standard review dimensions:

${content.trim()}
</project_specific_criteria>
`;
      
      if (this.options.verbose) {
        console.log(`Loaded project criteria from ${criteriaPath}`);
      }
      
      return prompt;
      
    } catch (error) {
      if (error.code !== 'ENOENT' && this.options.verbose) {
        console.error(`Error loading criteria file: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Build criteria from .reviewrc.json configuration
   */
  async buildFromConfig() {
    const configPath = path.join(this.options.projectRoot, this.options.configFile);
    
    try {
      const config = JSON.parse(await fs.readFile(configPath, 'utf8'));
      
      // Check for review_criteria section first
      if (config.review_criteria) {
        return this.buildStructuredCriteria(config.review_criteria);
      }
      
      // Fall back to custom_prompts section
      if (config.review_overrides?.custom_prompts) {
        return this.buildSimpleCriteria(config.review_overrides.custom_prompts);
      }
      
      return null;
      
    } catch (error) {
      if (error.code !== 'ENOENT' && this.options.verbose) {
        console.error(`Error loading config file: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Build prompt from structured review_criteria
   */
  buildStructuredCriteria(criteria) {
    const sections = [];
    
    // Add project context if specified
    if (criteria.project_context) {
      sections.push(`<project_context>\n${criteria.project_context}\n</project_context>`);
    }
    
    // Add security requirements
    if (criteria.security_requirements?.length > 0) {
      const requirements = criteria.security_requirements.map(req => {
        let text = `- **${req.name}**: ${req.description || ''}`;
        if (req.paths?.length > 0) {
          text += `\n  Applies to: ${req.paths.join(', ')}`;
        }
        if (req.severity_override) {
          text += `\n  All violations are ${req.severity_override} severity`;
        }
        return text;
      }).join('\n');
      
      sections.push(`<security_requirements>\n${requirements}\n</security_requirements>`);
    }
    
    // Add performance requirements
    if (criteria.performance_requirements) {
      const perf = criteria.performance_requirements;
      const requirements = [];
      
      if (perf.response_time_ms) {
        requirements.push(`- Response time must be < ${perf.response_time_ms}ms`);
      }
      if (perf.database_queries_per_request) {
        requirements.push(`- Maximum ${perf.database_queries_per_request} database queries per request`);
      }
      if (perf.memory_limit_mb) {
        requirements.push(`- Memory usage must stay below ${perf.memory_limit_mb}MB`);
      }
      
      if (requirements.length > 0) {
        sections.push(`<performance_requirements>\n${requirements.join('\n')}\n</performance_requirements>`);
      }
    }
    
    // Add custom rules
    if (criteria.custom_rules?.length > 0) {
      const rules = criteria.custom_rules.map(rule => {
        return `- **Pattern**: \`${rule.pattern}\`\n  **Severity**: ${rule.severity}\n  **Message**: ${rule.message}`;
      }).join('\n\n');
      
      sections.push(`<custom_checks>\n${rules}\n</custom_checks>`);
    }
    
    // Add critical paths
    if (criteria.critical_paths?.length > 0) {
      const paths = criteria.critical_paths.map(p => {
        if (typeof p === 'string') {
          return `- \`${p}\``;
        }
        return `- \`${p.path}\`: ${p.description}`;
      }).join('\n');
      
      sections.push(`<critical_paths>\nThe following paths require extra scrutiny:\n${paths}\n</critical_paths>`);
    }
    
    if (sections.length === 0) {
      return null;
    }
    
    return `
<project_specific_criteria>
This project has defined specific review criteria:

${sections.join('\n\n')}
</project_specific_criteria>
`;
  }

  /**
   * Build prompt from simple custom_prompts
   */
  buildSimpleCriteria(customPrompts) {
    const sections = [];
    
    if (customPrompts.additional_context) {
      sections.push(`<project_context>\n${customPrompts.additional_context}\n</project_context>`);
    }
    
    if (customPrompts.focus_areas?.length > 0) {
      const areas = customPrompts.focus_areas.map(area => `- ${area}`).join('\n');
      sections.push(`<focus_areas>\nPay special attention to:\n${areas}\n</focus_areas>`);
    }
    
    if (customPrompts.ignore_patterns?.length > 0) {
      const patterns = customPrompts.ignore_patterns.map(p => `- ${p}`).join('\n');
      sections.push(`<ignore_patterns>\nDo not flag issues in files matching:\n${patterns}\n</ignore_patterns>`);
    }
    
    // Handle prepend/append as raw additions
    const parts = [];
    
    if (customPrompts.prepend) {
      parts.push(customPrompts.prepend);
    }
    
    if (sections.length > 0) {
      parts.push(`
<project_specific_criteria>
${sections.join('\n\n')}
</project_specific_criteria>
`);
    }
    
    if (customPrompts.append) {
      parts.push(customPrompts.append);
    }
    
    return parts.length > 0 ? parts.join('\n\n') : null;
  }

  /**
   * Save generated criteria to cache
   */
  async saveToCache(content) {
    try {
      await fs.mkdir(this.options.cacheDir, { recursive: true });
      const cachePath = path.join(this.options.cacheDir, 'project-criteria.md');
      await fs.writeFile(cachePath, content, 'utf8');
      return cachePath;
    } catch (error) {
      if (this.options.verbose) {
        console.error('Failed to cache criteria:', error.message);
      }
      return null;
    }
  }
}

/**
 * CLI usage
 */
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const builder = new CriteriaBuilder({
    verbose: true,
    projectRoot: process.argv[2] || process.cwd()
  });
  
  builder.build().then(criteria => {
    if (criteria) {
      console.log('Generated project criteria:');
      console.log(criteria);
    } else {
      console.log('No project-specific criteria found');
    }
  }).catch(error => {
    console.error('Error:', error.message);
    process.exit(1);
  });
}

export default CriteriaBuilder;