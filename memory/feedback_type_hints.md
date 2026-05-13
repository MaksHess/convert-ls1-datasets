---
name: Preserve type hints with TYPE_CHECKING
description: When deferring imports to speed up CLI startup, use TYPE_CHECKING guard instead of weakening type annotations
type: feedback
---

Use `if TYPE_CHECKING:` to preserve full type annotations when moving imports to be lazy. Never weaken a type hint (e.g. `list[Channel]` → `list`) as a workaround.

**Why:** User wants type safety and accurate annotations intact, even when imports are deferred for runtime performance.

**How to apply:** Add `from typing import TYPE_CHECKING` at the top, put type-only imports under `if TYPE_CHECKING:`, and keep annotations unchanged.
