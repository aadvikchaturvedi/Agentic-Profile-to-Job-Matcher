"""
Configuration for Ollama integration
Sets up the local Ollama model connection.
"""

import os

# Ollama Configuration
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")

# Parser Configuration
PARSER_CONFIG = {
    "ollama_base_url": OLLAMA_BASE_URL,
    "default_model": OLLAMA_DEFAULT_MODEL,
    "timeout": 60,
    "temperature": 0.3,  # Lower temperature for more structured output
}

# Recommended models for resume parsing:
# - mistral: Fast and good quality
# - neural-chat: Optimized for conversations and structured output
# - llama2: Good general purpose model
# - orca: Great for instruction following and structured output

print(f"""
Ollama Configuration:
  Base URL: {OLLAMA_BASE_URL}
  Default Model: {OLLAMA_DEFAULT_MODEL}
  
To start Ollama locally, run:
  ollama serve
  
To pull a model, run (in a new terminal):
  ollama pull mistral
  ollama pull neural-chat
  ollama pull llama2
""")
