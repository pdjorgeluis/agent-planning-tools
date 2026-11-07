---
name: apt-momus
description: Use on a drafted multi-step, irreversible or expensive spec. Checks it is startable and finishable (advisory).
---

# momus

Run: `python3 {{APT_ROOT}}/tools/momus/momus.py --allow <dir> SPEC.md`

Advisory only: never blocks, never decides. Tested on Hermes only; other
targets follow the vendors' documented conventions and are untested.

(Minimal stub from the code card; the prose card replaces this file. Keep the
`{{APT_ROOT}}` token: the installer swaps it for the install directory.)
