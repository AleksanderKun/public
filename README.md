# LinkJob AI

A desktop application for real-time conversation analysis, inspired by LockedIn AI.

## Features

- Start conversation session
- Capture conversation text
- Manual text input (MVP)
- Send conversation context to local Ollama
- Generate responses/suggestions using local model
- Display suggestions in overlay
- Maintain session history
- Stop session
- Handle Ollama errors and unavailability
- Non-blocking GUI

## Technology

- Python 3.11+
- PyQt5
- requests
- Ollama HTTP API
- QThread for network/AI operations

## Configuration

Use environment variables:

- `OLLAMA_API_BASE` (default: `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default: `qwen2.5-coder:14b`)
- `OLLAMA_CONTEXT_LENGTH` (default: `16384`)
- `OLLAMA_TIMEOUT` (default: `120`)

## Installation

1. Install Python 3.11
2. Create virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Install Ollama and pull the model:
   ```bash
   ollama pull qwen2.5-coder:14b
   ```
5. Run Ollama
6. Set environment variables:
   ```bash
   set OLLAMA_API_BASE=http://127.0.0.1:11434
   set OLLAMA_MODEL=qwen2.5-coder:14b
   set OLLAMA_CONTEXT_LENGTH=16384
   set OLLAMA_TIMEOUT=120
   ```
7. Run the application:
   ```bash
   python main.py
   ```
8. Run tests:
   ```bash
   pytest
   ```
