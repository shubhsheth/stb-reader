# Planning and Task Breakdown Guide

This document outlines a systematic approach for decomposing work into manageable, verifiable tasks—essential when handling large features or unclear requirements.

## Key Principles

The workflow follows four sequential phases: SPECIFY → PLAN → TASKS → IMPLEMENT, with human review at each checkpoint. Planning must occur in read-only mode before any implementation begins.

## When to Apply This Method

Use task breakdown when:
- You possess specifications requiring implementation units
- Work feels too expansive to initiate
- Multiple agents or sessions need parallelization
- Scope communication to stakeholders is necessary
- Implementation sequence isn't straightforward

Avoid this approach for "single-file changes with obvious scope" or specs already containing defined tasks.

## Critical Planning Steps

**Step 0** requires identifying unresolved technical questions requiring research spikes before planning proceeds—invalid assumptions necessitate plan rewrites.

**Step 2** maps dependencies bottom-up, ensuring foundations precede dependent components.

**Step 3** emphasizes vertical slicing (one complete feature path) over horizontal slicing (all database, then all API, then UI).

Each task requires:
- Clear description and acceptance criteria
- Verification procedures
- File references
- Scope estimation (XS through XL)

## Task Sizing Standards

Tasks should remain Small to Medium (1-5 files). Anything exceeding 8 files needs further decomposition. "If a task is L or larger, it should be broken into smaller tasks."

## Quality Assurance

Before implementation, verify every task has acceptance criteria, verification steps, correct dependency ordering, and that all specification requirements map to tasks. Flag gaps as CRITICAL, HIGH, or MEDIUM severity.
