# Nomisma agent coordination

This policy replaces the earlier coordination guidance in
`.codex/agents/agents.md`, including its paper-trading default.
Keep the existing agent definitions in `.codex/agents/*.toml` intact and
use each file's actual `name` field when selecting or referring to an agent.

## Main agent responsibilities

These coordination rules apply to the top-level main conversation.
A delegated subagent should perform its assigned specialist task,
return its findings, and not recursively delegate unless explicitly
authorized.

The main agent owns:

- understanding the user's task
- planning and dividing the work
- choosing the appropriate specialist agents
- managing dependencies and shared interfaces
- collecting evidence and resolving conflicting findings
- integrating results and reporting to the user

Delegate substantial specialist work to the actual configured agents.
Do not merely imitate their roles in the main conversation.
If an agent cannot be spawned, report the limitation.

## Task routing

`researcher`:
Trading hypotheses, mathematical derivations, signal definitions,
position sizing, assumptions, and validation design.

`developer`:
Strategy implementation, backtesting logic, portfolio accounting,
application code, and unit tests.

`data_engineer`:
Market-data ingestion, schemas, timestamp alignment, corporate
actions, data validation, and reproducible datasets.

`reviewer`:
Independent review of mathematical consistency, implementation,
data handling, execution assumptions, and test coverage.

`infra_engineer`:
Environments, dependencies, reproducible execution, integration
tests, offline backtests, logging, and operational tooling.

`risk_officer`:
Independent assessment of validation evidence, risk controls,
unresolved issues, and paper-trading readiness.

## Delegation procedure

Use only the agents relevant to the current task.

For every assignment, provide:

- the objective and completion criteria
- relevant files, specifications, and previous findings
- permitted file changes and ownership boundaries
- required checks and expected output

Wait for prerequisites before starting dependent tasks.
Run independent investigations in parallel where useful.
Do not assign simultaneous edits to the same files.

Give agents the relevant findings from previous stages explicitly.
Do not assume they already know everything discussed in the main chat.

Read-only agents return reports to the main agent.
The main agent may save those reports, preserving their attribution
and conclusions.

## Workflow for substantial strategy changes

1. Establish requirements and acceptance criteria.
2. Use `researcher` and `data_engineer` to resolve mathematical
   requirements and data feasibility.
3. Agree on the mathematical specification and data interface.
4. Delegate implementation to `developer` and `data_engineer`,
   with separate file ownership.
5. Obtain independent review from `reviewer`.
6. Have `infra_engineer` execute tests and reproducible backtests.
7. Route defects back to the responsible agent, then repeat
   affected review and validation.
8. Have `risk_officer` assess the evidence for the exact version tested.

Scale this workflow to the task. A small investigation does not
require all six agents.

Do not weaken acceptance criteria to obtain approval.
Rejection and insufficient evidence are valid outcomes.
Do not fabricate results or treat missing evidence as a passing result.

## Trading boundaries

Default to research and offline backtesting.
Paper-trading execution requires an explicitly scoped request.
Do not submit live orders or enable live deployment.

Risk-officer sign-off is advisory; it does not authorize real-money
execution.

## Final reporting

Report:

- which agents actually ran and their assignments
- files changed
- tests and backtests actually executed
- unresolved findings and missing evidence
- the risk assessment, when requested
