# Evidence Model

ProdMind diagnoses failures from normalized evidence, not from raw log text alone.

## Evidence properties

Every evidence item should eventually carry:

- type
- summary
- source
- timestamp
- correlation identifiers
- sensitivity classification
- optional raw reference

## Initial evidence types

- `user_action`
- `http`
- `trace`
- `log`
- `exception`
- `database`
- `metric`
- `history`

## Root-cause rule

A root-cause statement must be supported by evidence. If ProdMind cannot establish a sufficiently strong chain, the result should be `insufficient_evidence`.

Example:

```text
create-user
    ↓
POST /api/users → 500
    ↓
trace abc123
    ↓
DuplicateKeyException
    ↓
PostgreSQL unique constraint uk_user_phone
    ↓
Root cause: duplicate user data
```

Historical incidents may raise a hypothesis but must not by themselves prove the current root cause.
