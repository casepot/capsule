# Prompt Engineering Methodology

A systematic approach to creating effective planning prompts for complex technical problems.

## The PARIS Framework

**P**roblem Archaeology → **A**rchitecture Recognition → **R**isk Illumination → **I**mplementation Scaffolding → **S**uccess Validation

## Quick Navigation

### Core Documents
- [`00-overview.md`](00-overview.md) - Framework overview and principles
- [`template.md`](template.md) - Ready-to-use planning prompt template
- [`examples.md`](examples.md) - Real-world applications across domains

### Phase Guides
1. [`01-problem-archaeology.md`](01-problem-archaeology.md) - Mining historical failures and lessons
2. [`02-architecture-recognition.md`](02-architecture-recognition.md) - Mapping existing infrastructure
3. [`03-risk-illumination.md`](03-risk-illumination.md) - Identifying failure modes early
4. [`04-implementation-scaffolding.md`](04-implementation-scaffolding.md) - Structuring solution approaches
5. [`05-success-validation.md`](05-success-validation.md) - Defining measurable outcomes
6. [`06-prompt-calibration.md`](06-prompt-calibration.md) - Tuning autonomy and precision
7. [`07-integration-guide.md`](07-integration-guide.md) - Combining all phases effectively

## When to Use This Methodology

Perfect for planning:
- **Architecture changes** requiring careful design
- **Performance optimizations** with specific targets
- **Bug fixes** for complex issues
- **Migrations** with compatibility requirements
- **Security implementations** with high stakes
- **Refactoring** with preservation requirements

## Key Principles

1. **Historical Awareness**: Learn from past failures
2. **Infrastructure Respect**: Leverage what exists
3. **Early Risk Detection**: Identify problems during planning
4. **Concrete Specificity**: Vague plans produce vague results
5. **Calibrated Autonomy**: Match exploration to problem complexity

## Quick Start

1. **Assess your problem** using the PARIS checklist
2. **Copy the template** from `template.md`
3. **Fill out each section** using phase guides
4. **Calibrate the prompt** based on problem type
5. **Integrate sections** following the integration guide
6. **Validate** against success criteria

## Methodology Benefits

- **Reproducible**: Same process for any problem
- **Comprehensive**: Covers all planning aspects
- **Risk-aware**: Identifies issues early
- **Specific**: Produces actionable plans
- **Adaptable**: Scales with problem complexity

## Real Impact

This methodology was extracted from creating the v0.2 input implementation planning prompt, which:
- Analyzed 3 versions of failed attempts
- Identified the single-reader invariant as critical
- Recognized existing infrastructure could be leveraged
- Produced a solution requiring <10 lines of code
- Maintained all architectural improvements

## Navigation by Use Case

### "I need to plan a complex change"
Start with [`00-overview.md`](00-overview.md) then use [`template.md`](template.md)

### "I want to understand the methodology"
Read phases 1-7 in order

### "I have a specific problem type"
Check [`examples.md`](examples.md) for similar cases

### "I need to tune my prompt"
Go directly to [`06-prompt-calibration.md`](06-prompt-calibration.md)

### "My prompts are too vague"
Study [`04-implementation-scaffolding.md`](04-implementation-scaffolding.md)

## Remember

The best planning prompts:
- Tell the planner what failed before
- Show what infrastructure exists
- Define clear boundaries
- Specify exact success criteria
- Calibrate exploration appropriately

---

*Methodology Version: 1.0*  
*Created: January 2024*  
*Domain: Technical Planning & Architecture*