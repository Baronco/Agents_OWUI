<!--
Sync Impact Report
Version change: N/A → 1.0.0
Modified principles: template placeholders → code quality, testing, UX consistency, performance, maintainability
Added sections: Quality & Performance Constraints, Development Workflow & Review Process
Removed sections: none
Templates reviewed: ✅ .specify/templates/plan-template.md, ✅ .specify/templates/spec-template.md, ✅ .specify/templates/tasks-template.md, ✅ .specify/templates/checklist-template.md
Follow-up TODOs: none
-->

# Agents OWUI Constitution

## Core Principles

### I. Code Quality is Non-Negotiable
Every code change MUST be readable, consistent, and maintainable. Code MUST follow repository style, avoid unnecessary complexity, and preserve a clean architecture that supports review and long-term evolution.
- Enforce formatting, static analysis, and code review before merge.
- Prefer clarity, explicit intent, and minimal surface area over clever shortcuts.
- All implementation decisions that are not obvious MUST include a brief rationale in code or review notes.

### II. Test-First and Measurable Coverage
All behavior MUST be backed by tests before feature work is accepted. Tests MUST be explicit, deterministic, and repeatable.
- Unit tests MUST cover core business logic and edge cases.
- Integration tests MUST validate external tool interactions, API contracts, and workflow boundaries.
- Tests MUST fail before implementation and pass in CI as a gating requirement.

### III. User Experience Consistency
User-facing behavior MUST be predictable, coherent, and aligned with the repository's UX expectations.
- Inputs, outputs, error handling, and assistant responses MUST follow consistent patterns across similar features.
- Messages and API contracts MUST be clear, concise, and avoid ambiguity.
- Any deviation from established UX patterns MUST be explicitly documented and justified during review.

### IV. Performance Requirements
Performance MUST be defined, measured, and preserved for every feature with operational impact.
- Features MUST document performance expectations and validation criteria in specifications.
- External calls and tool interactions MUST minimize payloads, avoid unnecessary retries, and handle timeouts safely.
- Performance regressions MUST be detected by testable criteria and remediated before merge.

### V. Maintainability and Continuous Improvement
The project MUST remain easy to update, instrument, and extend as requirements evolve.
- Documentation, tests, and architecture MUST be kept in sync with implementation.
- Review feedback MUST be incorporated promptly, and technical debt MUST be tracked with explicit tradeoffs.
- New design choices MUST include a clear path for future optimization and refactoring.

## Quality & Performance Constraints
- All code MUST pass automated linting and static analysis before merging.
- All feature work MUST include measurable acceptance criteria and test coverage aligned with success conditions.
- User-facing contracts MUST preserve stable formats and compatibility across related flows.
- Performance constraints MUST be documented in design artifacts and verified during implementation.

## Development Workflow & Review Process
- Every change MUST be developed in a feature branch, reviewed by a peer, and linked to a specification or task.
- Pull requests MUST include test updates, documentation updates, and a short compliance summary referencing this constitution.
- Reviews MUST verify alignment with code quality, test coverage, UX consistency, and performance requirements.
- Review findings MUST be addressed before merge; deliberate exceptions MUST be documented and approved.

## Governance
This constitution is the baseline for quality decisions across the repository.
- All PRs and reviews MUST verify compliance with these principles.
- Amendments require a documented rationale, an explicit version bump, and a review of dependent plans or templates.
- If a principle change materially affects workflow, testing, or release behavior, the related plan/spec/tasks artifacts MUST be updated.

**Version**: 1.0.0 | **Ratified**: 2026-06-03 | **Last Amended**: 2026-06-03
