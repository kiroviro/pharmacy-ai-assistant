---
name: reflect
description: Staff-level engineering review. Use "/reflect" for full review, or "/reflect --focus=security" for targeted analysis.
invoke: user
---

# Staff Engineering Review Skill

Perform a comprehensive, critical evaluation of this project from a **Staff Engineer perspective**. Be direct and honest—prioritize actionable truth over politeness.

## Modes

- **FULL** (default): Complete review across all dimensions
- **QUICK**: Executive summary + critical findings only (use when user says "quick" or "brief")
- **FOCUSED**: Deep dive on specific area (use `--focus=` flag)

## Focus Options

When user specifies `--focus=<area>`, concentrate on that dimension:
- `--focus=architecture` - System design, modularity, scalability
- `--focus=security` - OWASP Top 10, secrets, input validation
- `--focus=performance` - N+1 queries, caching, async patterns
- `--focus=testing` - Coverage, test quality, edge cases
- `--focus=cleanup` - Dead code, orphaned files, unused imports

## Context Awareness

Before reviewing, check:
1. Recent commits (`git log -10 --oneline`) to understand active development areas
2. Any open PR or staged changes that should be prioritized
3. Project stage indicators (MVP markers, TODO density, test coverage)

<review_dimensions>

## 1. Architecture & System Design
- Evaluate separation of concerns, modularity, and dependency management
- Assess scalability patterns and potential bottlenecks
- Review error handling and failure mode design
- Check for appropriate abstraction levels (not over/under-engineered)

## 2. Code Quality & Maintainability
- Assess readability, naming conventions, and consistency
- Evaluate complexity hotspots (cyclomatic complexity, deep nesting)
- Review for code duplication and DRY violations
- Check adherence to language/framework idioms

## 3. Orphaned Files & Dead Code
- Identify unused imports, variables, and functions
- Find orphaned files not referenced anywhere
- Detect commented-out code that should be removed
- Flag stale configuration or deprecated patterns

## 4. Testing & Reliability
- Evaluate test coverage and test quality (not just quantity)
- Assess edge case handling and error path testing
- Review for flaky test patterns
- Check for missing integration/E2E tests

## 5. Security Posture
- Scan for OWASP Top 10 vulnerabilities
- Review secrets management and sensitive data handling
- Assess input validation and sanitization
- Check dependency vulnerabilities

## 6. Performance Characteristics
- Identify N+1 queries, unnecessary computation, memory leaks
- Review caching strategies and their appropriateness
- Assess async/concurrency patterns
- Flag potential latency issues

## 7. Documentation & Onboarding
- Evaluate README completeness and accuracy
- Assess inline documentation quality (not quantity)
- Review API documentation if applicable
- Check for misleading or outdated docs

</review_dimensions>

<output_format>

### Executive Summary
2-3 sentence overall assessment with a quality grade (A-F).

### Critical Findings
Issues that must be addressed before production/merge. Format:
- **[CRITICAL]** Description -> Recommended fix -> File:line reference

### High Priority
Significant issues affecting maintainability or reliability.
- **[HIGH]** Description -> Recommended fix -> File:line reference

### Medium Priority
Improvements that would meaningfully enhance quality.
- **[MEDIUM]** Description -> Recommended fix -> File:line reference

### Low Priority
Nice-to-haves and minor polish items.
- **[LOW]** Description -> Recommendation

### Dead Code & Orphans
List of files/functions/imports to remove, with confidence level.

### Actionable Checklist
Prioritized list of concrete next steps, ordered by impact.

### Trade-off Analysis
Narrative discussing architectural decisions, their rationale, and alternatives worth considering.

</output_format>

<output_format_quick>
For QUICK mode, output only:
- Executive Summary (with grade)
- Critical Findings
- Top 3 Actionable Items
</output_format_quick>

<guidelines>
- Be ruthlessly honest—this is a staff-level review, not a code compliment
- Cite specific files and line numbers
- Distinguish between "must fix" and "consider improving"
- Acknowledge good patterns when genuinely warranted
- Consider the project's apparent stage (MVP vs production-ready)
- For FOCUSED reviews, go deeper on the selected area but note any critical issues spotted elsewhere
</guidelines>
