# Async Capability Documentation

## Directory Structure

### `/current/` - Active Documentation

Contains all current, relevant documents for the PyREPL3 async capability implementation.

#### Naming Convention
- **00-09**: Foundation documents
- **10-19**: Implementation prompts (requirements)
- **20-29**: Technical specifications (implementation details)

#### Foundation (00-09)
- `00_foundation_resonate.md` - Resonate SDK integration foundation and architectural basis

#### Implementation Prompts (10-19)
- `10_prompt_async_executor.md` - Async executor implementation requirements
- `11_prompt_capability_system.md` - Capability injection system requirements
- `12_prompt_namespace_persistence.md` - Namespace persistence requirements

#### Technical Specifications (20-29)
- `20_spec_architecture.md` - System architecture and design
- `21_spec_resonate_integration.md` - Resonate SDK integration details
- `22_spec_async_execution.md` - AsyncExecutor implementation
- `23_spec_capability_system.md` - Capability injection and security
- `24_spec_namespace_management.md` - Thread-safe namespace management
- `25_spec_api_reference.md` - Complete API documentation
- `26_spec_security_model.md` - Security architecture and policies
- `27_spec_testing_validation.md` - Testing strategies and validation

### `/archive/` - Obsolete Documentation

Contains documents that have been superseded or are no longer relevant. All files prefixed with `obsolete_`.

#### Original Prompts (Superseded)
- `obsolete_10_prompt_async_executor_v1.md` - Original async executor prompt
- `obsolete_11_prompt_capability_system_v1.md` - Original capability system prompt
- `obsolete_12_prompt_namespace_persistence_v1.md` - Original namespace persistence prompt

#### Deprecated Components
- `obsolete_30_protocol_bridge.md` - Replaced by Resonate promises
- `obsolete_31_standard_capabilities.md` - Incorporated into specifications
- `obsolete_32_protocol_documentation.md` - Replaced by Resonate integration

#### Completed Investigations
- `obsolete_00_investigation_insights.md` - Investigation findings (incorporated)
- `obsolete_01_investigation_polling.md` - Polling investigation (complete)

## Document Evolution

1. **Initial Prompts** → **REFINED Prompts** (based on investigation insights)
2. **REFINED Prompts** → **Technical Specifications** (comprehensive implementation docs)
3. **Protocol Bridge** → **Resonate Promises** (architectural evolution)

## Key Technical Decisions

- **PyCF_ALLOW_TOP_LEVEL_AWAIT (0x1000000)**: Core mechanism for top-level await
- **Namespace Merge Policy**: Never replace, always merge to prevent KeyError
- **Capability-Based Security**: Enforce at injection, not code preprocessing
- **Resonate Integration**: Durability and distributed execution foundation

## Quick Start

For implementation, refer to documents in `/current/` in this order:

1. Read `00_resonate_foundation.md` for architectural context
2. Review the REFINED prompts for implementation requirements
3. Follow the technical specifications for detailed implementation
4. Use `05_api_reference_specification.md` for API contracts
5. Validate with `07_testing_validation_specification.md`

## Status

All specifications are complete and ready for implementation.