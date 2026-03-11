# Generic review checklist

Use this review context in every mirrored Chummer code repo.

## 1. Boundary check

* Does this change stay inside the repo’s implementation scope?
* Does it widen ownership into another repo’s area?
* Does it reintroduce a boundary that was intentionally split out?

Reject if:

* play behavior appears inside presentation
* workbench behavior appears inside play
* run-services regrows registry persistence or media execution
* engine regrows UI or hosted-service authority
* ui-kit gains domain DTOs or service logic

## 2. Contract check

* Is any cross-repo DTO being added?
* If yes, is the owning package already defined in `CONTRACT_SETS.yaml`?
* Is the change consuming a canonical package or copying source?

Reject if:

* the change creates a duplicate shared DTO family
* the change uses an ambiguous or legacy package name when canon is defined
* the change smuggles engine semantics into play/run wrappers

## 3. Mirror check

* Does `.codex-design/product/*` exist?
* Does `.codex-design/repo/IMPLEMENTATION_SCOPE.md` exist?
* Does the mirrored scope match the code being changed?

Reject if:

* the repo is missing mirrored design context
* the change contradicts mirrored scope without a corresponding design-repo update

## 4. Milestone check

* Which milestone is this change serving?
* Does it unblock or change a published blocker?
* Does the design repo need an update because sequencing changed?

Reject if:

* the change claims milestone progress but central milestones say otherwise
* the change silently changes rollout order or package ownership

## 5. README drift check

* Does the repo README still describe the current architecture?
* Does the change depend on a README that is known to be stale?

Reject if:

* a stale README is used as architecture authority over central design

## 6. Test and verification check

* Are the relevant contract or boundary tests updated?
* If the repo owns a package, is its verification harness updated?
* If the repo consumes a package, is package-only consumption preserved?

## 7. Review summary format

Every substantive review should answer:

* scope fit: pass/fail
* boundary fit: pass/fail
* contract fit: pass/fail
* mirror fit: pass/fail
* milestone fit: pass/fail
* required design-repo follow-up: yes/no

## 8. Escalate immediately when

* ownership is ambiguous
* package canon is ambiguous
* mirror coverage is missing
* a split boundary is being locally re-merged
* central design files are obviously stale or contradictory

The fastest safe move in those cases is to fix `chummer-design`, not to guess locally.
