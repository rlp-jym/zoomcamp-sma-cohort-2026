#!/usr/bin/env python

# # 00 - Smoke test
#
# Proves the notebook toolchain works end to end: the package imports, config loads,
# and this notebook exports to a script that runs headless (P0-14).
#
# Kernel: `crypto-cross-pred`. Export with:
#
# ```bash
# uv run jupyter nbconvert --to python notebooks/00_smoke.ipynb --output-dir scripts
# uv run python scripts/00_smoke.py
# ```

# In[ ]:


import crypto_cross_pred
from crypto_cross_pred.config import get_settings

settings = get_settings()
print(f"crypto_cross_pred {crypto_cross_pred.__version__}")
print(f"dev period: {settings.dates.dev_start} -> {settings.dates.dev_end}")
print(f"holdout:    {settings.dates.holdout_start} -> {settings.dates.holdout_end}")
