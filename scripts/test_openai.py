#!/usr/bin/env python3
"""
Validate OpenAI/Anthropic API key connectivity.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config_manager import ConfigManager
from src.content.generator import create_ai_provider


def main():
    config = ConfigManager()
    provider_name = config.ai.provider
    print(f"Testing {provider_name} API connectivity...\n")

    try:
        ai = create_ai_provider(config.ai)
        result = ai.generate(
            system_prompt="You are a helpful assistant.",
            user_prompt="Say 'Hello, OpenLinkedIn!' in one short sentence.",
        )
        print(f"Provider: {result.provider}")
        print(f"Model: {result.model}")
        print(f"Tokens: {result.tokens_used}")
        print(f"Response: {result.content}")
        print("\nAPI connection successful!")
    except Exception as e:
        print(f"ERROR: API connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
