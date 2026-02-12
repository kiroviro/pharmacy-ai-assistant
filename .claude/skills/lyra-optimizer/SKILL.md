---
name: lyra-optimizer
description: Optimizes prompts using the Lyra 4-D Methodology (Deconstruct, Diagnose, Develop, Deliver). Use when I ask to "optimize this prompt" or "apply Lyra".
invoke: user
---

# Lyra Prompt Optimization Skill

When activated, follow the 4-D Methodology to refine the user's provided prompt:

1. **Deconstruct**: Identify the core intent, audience, and constraints of the initial prompt.
2. **Diagnose**: Pinpoint clarity gaps or missing context using Lyra's diagnostic patterns.
3. **Develop**: Apply advanced techniques (e.g., XML tagging, chain-of-thought, or few-shot examples).
4. **Deliver**: Provide the final, "agent-ready" prompt in a clean markdown code block.

## Operational Modes

- **BASIC** (default): Provide a quick, optimized version immediately.
- **DETAIL**: Ask 2-3 clarifying questions before delivering the final prompt. Use when the user says "detailed" or "thorough".

## Output Format

Deliver the optimized prompt in this structure:

```markdown
## Analysis
- **Intent**: [1 sentence summary of what the prompt aims to achieve]
- **Gaps Identified**: [Brief list of issues found]
- **Techniques Applied**: [List of optimization techniques used]

## Optimized Prompt
\`\`\`
[The refined, agent-ready prompt here]
\`\`\`
```

## Examples

### Before
```
Write me a function to validate emails
```

### After (BASIC mode)
```xml
<task>
Write a function to validate email addresses.
</task>

<requirements>
- Use RFC 5322 compliant regex pattern
- Return boolean (true = valid, false = invalid)
- Handle edge cases: empty string, null, whitespace-only
</requirements>

<output_format>
- Language: Match the user's project language (infer from context)
- Include brief inline comments for the regex pattern
</output_format>
```

### Before
```
Help me write better code
```

### After (DETAIL mode - would first ask)
1. What language/framework are you using?
2. What type of code? (API, CLI, data processing, etc.)
3. What's your main pain point? (readability, performance, testing, etc.)
