# Evaluation Factory

## Purpose
Produces eval harnesses and scoring rubrics for agents, prompts, and
workflows. This factory has **no matching top-level library shelf** —
its output (eval suites, scores, regression gates) is consumed directly
by the factory/module being evaluated, not collected in a separate
directory. See [ARCHITECTURE.md](../../ARCHITECTURE.md) §2.

## Responsibilities
- Define the eval suite spec: task set, scoring rubric/grader (rule-based,
  model-graded, or human), pass/fail or scored threshold.
- Provide the harness that runs an eval suite against an agent, prompt
  version, or workflow and produces a comparable score.
- Gate promotion: `prompt-factory` and `agent-factory` both depend on this
  factory to say whether a new version regressed before it's marked
  reusable.

## Architecture
_(To be designed in Phase 1, alongside the first agent — see
[ROADMAP.md](../../ROADMAP.md).)_ Expected shape: eval suites as
structured spec files (task, expected/graded outcome), a runner CLI, and a
results format other factories can query programmatically (pass/fail +
score + diff vs. previous version).

## Inputs
An eval suite spec, and the agent/prompt/workflow version to evaluate.

## Outputs
A score/report; suites themselves are stored alongside what they evaluate
(e.g. `agents/<domain>/evals/`), not in a separate top-level shelf.

## Dependencies
`router/` (if model-graded evals need a specific grading model), `core/`.

## Examples
_(none yet.)_

## Limitations
Not implemented yet. Until it exists, no factory in this platform has a
real regression gate — treat any agent/prompt as unvalidated.

## Future improvements
- Central eval results dashboard across all agents/prompts once volume
  justifies it.
