"""
Prompts module for the ViaPharma OTC Chatbot.

Contains structured prompts for LLM processing that can be updated
without code changes for easier maintenance and A/B testing.
"""

from src.prompts.unified_prompt import (
    UNIFIED_SYSTEM_PROMPT,
    build_prompt,
)

__all__ = [
    "UNIFIED_SYSTEM_PROMPT",
    "build_prompt",
]
