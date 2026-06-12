"""Test-suite environment setup.

Runs before any test module imports application code. Points storage at a
session-scoped temp directory so tests never depend on host paths like
/data (unwritable on CI runners) and never leak files between runs.
"""

import os
import tempfile

# Must happen before backend.config.get_settings() is first called anywhere.
_TEST_MEDIA_DIR = tempfile.mkdtemp(prefix="avatarforge-test-media-")
os.environ["LOCAL_STORAGE_PATH"] = _TEST_MEDIA_DIR

# Rate limiting off by default in tests; test_ratelimit re-enables explicitly.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
