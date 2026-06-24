import os

# Force deterministic mock-LLM mode for the whole test session (no API spend).
os.environ.setdefault("USE_MOCK_LLM", "true")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
