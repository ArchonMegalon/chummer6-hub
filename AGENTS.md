# Agent Runtime Instructions

## Persistent Memory
- Always load and follow `AGENT_MEMORY.md` before starting work.
- Treat entries in `AGENT_MEMORY.md` as active user preferences until the user changes them.

## Execution Rule
- Never stop at milestones while actionable work remains.
- Continue automatically after each completed patch/milestone and report what was reached.
- Only pause when blocked by missing required information, missing credentials/permissions, or an explicit user stop request.

<!-- fleet-design-mirror:start -->
## Fleet Design Mirror
- Load `.codex-design/product/README.md`, `.codex-design/repo/IMPLEMENTATION_SCOPE.md`, and `.codex-design/review/REVIEW_CONTEXT.md` when present.
- Treat `.codex-design/` as the approved local mirror of the cross-repo Chummer design front door.
<!-- fleet-design-mirror:end -->
