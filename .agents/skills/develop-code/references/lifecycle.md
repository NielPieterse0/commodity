# Lifecycle Gates

| `Phase` | Required state | Gate to advance |
|---|---|---|
| `Understand` | Authority, current behavior, desired outcome, boundaries, unknowns, repository commands, and recovery context identified | No material source or instruction is unread; unknowns are classified |
| `Classify` | Small, Medium, or Complex with evidence | Higher-risk triggers checked; required gates and artifacts selected |
| `Specify` | Requirements, exclusions, acceptance evidence, and open decisions recorded at level-appropriate depth | Requirements are testable; any governing decision or consent gate is satisfied |
| `Plan` | Ordered work maps to requirements and names checks, review points, and recovery | No blocking ambiguity; any governing change-workflow gate is satisfied |
| `Implement` | Tasks executed within scope; behavior changes use test-first evidence unless an authorized exception is recorded | Task checks pass; lifecycle state and traceability are current |
| `Review` | Spec, plan, docs, code, tests, risk, simplicity, and evidence reviewed together | Blocking findings fixed and affected scope re-reviewed |
| `Verify` | Fresh commands prove the current state | Every completion claim has current supporting output |
| `Close` | Requirements reconcile to evidence; recovery and residual work are explicit | Only optional or out-of-scope work remains |

## Control Rules

- Stop at a gate when authority conflicts, a governing decision or consent requirement is unsatisfied, a material product/risk choice remains open, a destructive action lacks consent, or verification fails. This lifecycle does not add approval requirements solely from complexity classification.
- A sub-skill result is phase evidence, not a lifecycle transition. Return here and evaluate the gate.
- Update the specification before implementing a changed requirement. Update the plan before executing changed work.
- An implementation edit after review invalidates the affected review. An edit after verification invalidates the affected evidence.
- Maintain requirement-to-task-to-test/evidence traceability for Medium and Complex work. Small work may keep the mapping inline.
- Resume from durable artifacts and current repository evidence, not conversational memory.
