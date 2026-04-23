# Incremental Implementation Guide

This document outlines a disciplined approach to building features in small, testable increments rather than large, monolithic changes.

## Core Principle

"Build in thin vertical slices — implement one piece, test it, verify it, then expand." Each increment should leave the system in a working, deployable state.

## Key Workflow Phases

The implementation phase follows specification, planning, and task breakdown. Work must proceed through established phase layers—completing setup before foundation work, foundation before core features—without skipping ahead to incomplete levels.

## The Increment Cycle

Each slice follows this pattern:
1. Implement the smallest complete piece
2. Run the test suite
3. Confirm the slice works as expected
4. Commit with a descriptive message
5. Proceed to the next slice

## Slicing Approaches

**Vertical slices** deliver end-to-end functionality (database through UI). **Contract-first slicing** defines API specifications before parallel backend/frontend work. **Risk-first slicing** tackles uncertain pieces early to avoid wasted effort.

## Implementation Rules

**Simplicity first**: Question whether abstractions justify their complexity. Three similar code blocks beats premature generalization.

**Scope discipline**: Touch only what the task requires. Don't refactor adjacent code or add unspecified features.

**One thing at a time**: Each commit addresses a single logical change.

**Keep it compilable**: The project must build and existing tests must pass between increments.

**Feature flags**: Hide incomplete work behind toggles when merging to main.

**Safe defaults**: New code should default to conservative, opt-in behavior.

**Rollback-friendly**: Each increment should be independently revertable.

## Critical Gate

Task completion requires validating acceptance criteria explicitly—not merely passing tests, which only prove code does what it does, not what the specification requires.
