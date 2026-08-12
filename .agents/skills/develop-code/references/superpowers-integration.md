# Specialist Skill Integration

`develop-code` remains the controller. Invoke only skills available in the active runtime and applicable to the classified work.

| Need | Invocation | Return evidence |
|---|---|---|
| Unclear requirements/design | **REQUIRED SUB-SKILL:** Use `superpowers:brainstorming` | Approved decisions or explicitly open decisions reflected in the spec |
| Explicit implementation plan | **REQUIRED SUB-SKILL:** Use `superpowers:writing-plans` | Plan in the canonical project location, mapped to requirements |
| Same-session task delegation | **REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` | Per-task implementation, test, and review evidence |
| Inline or separate-session execution | **REQUIRED SUB-SKILL:** Use `superpowers:executing-plans` | Completed task state and specified checks |
| Behavior change | **REQUIRED SUB-SKILL:** Use `superpowers:test-driven-development` | Observed failing test, minimal fix, passing test, safe refactor |
| Code review checkpoint | **REQUIRED SUB-SKILL:** Use `superpowers:requesting-code-review` | Findings against requirements and current diff |
| Completion claim | **REQUIRED SUB-SKILL:** Use `superpowers:verification-before-completion` | Fresh command output supporting each claim |
| Authorized branch closeout | **REQUIRED SUB-SKILL:** Use `superpowers:finishing-a-development-branch` | Verified and user-selected integration/retention outcome |

Do not copy a specialist's full process into lifecycle artifacts. Pass it the canonical inputs and constraints, let it own its method, then bring its outputs back to the current gate.

## Planned Review Skills

When installed and applicable:

- **REQUIRED SUB-SKILL:** Use `security-review` for security, privacy, trust-boundary, secret, authorization, or sensitive-data review.
- **REQUIRED SUB-SKILL:** Use `code-review` for implementation correctness and spec/plan compliance review.
- **REQUIRED SUB-SKILL:** Use `simpler-code` to challenge unnecessary complexity without changing required behavior.
- **REQUIRED SUB-SKILL:** Use `smarter-code` to assess whether a materially clearer, safer, or more effective design is warranted without expanding scope.

If a named skill is unavailable, record that fact and perform the base Review Contract. Do not imitate an unavailable skill or claim its specialist gate passed.
