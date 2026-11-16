# Task-form wrapper without a demonstrated need

Do not introduce a task-form wrapper solely on the assumption that the existing form functions all
share the same arguments. They have different inputs, and recurrence parsing and draft-state logic
already have a task-form module. Likewise, the template's grouped-field check classifies field
types; it does not enumerate recurrence kinds.

This decision does not rule out refactoring when a specific maintenance problem is demonstrated.

## Prior requests

- [#22: Refactor task-form arguments](https://github.com/gpompeo/dinkydash/issues/22)
