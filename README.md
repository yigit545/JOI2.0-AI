# JOI 2.0

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-blue.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=black)
![LLM](https://img.shields.io/badge/LLM-Llama_3_via_Ollama-black)

> A fully local AI companion with vision, memory, and system-level tools. No cloud required.

JOI 2.0 is a local AI companion that runs entirely on your own machine. It uses **Llama 3.0** served through **Ollama**, enriches answers with **RAG** (Retrieval-Augmented Generation), and ships with a **pygame**-based GUI and an optional vision mode. It is developed and tested on **Pardus Linux**.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Operating Modes](#operating-modes)
- [Project Structure](#project-structure)
- [Tool Modules](#tool-modules)
- [Translation (EN → TR)](#translation-en--tr)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Local LLM:** Llama 3.0 runs through Ollama, so your data never leaves your machine.
- **RAG:** Responses are grounded with retrieved context. Context utilization is under active improvement.
- **Memory:** JOI keeps track of past interactions to stay fresh and conversational.
- **Chat-bubble GUI:** A scrollable, modern chat layout.
- **Vision mode:** The `JOIEye` component adds visual perception on top of the pygame interface.
- **SILENT / INFERENCE split:** User-facing output (`SILENT`) is kept separate from the model's internal reasoning trace (`INFERENCE`).
- **Output sanitizing:** Malformed model output is repaired by `clean_response()`.
- **Tool modules:** Cross-platform modules for file and package management.
- **Offline-first design:** Wherever possible, JOI relies on the Python standard library (`os`, `sys`).

---

## Architecture

```
┌───────────────┐     ┌────────────────┐     ┌───────────────────┐
│ GUI (pygame)  │◄───►│ response_queue │◄───►│ JOIEye (vision)   │
└──────┬────────┘     └────────────────┘     └───────────────────┘
       │
       ▼
┌───────────────────┐   ┌───────────────┐   ┌───────────────────┐
│ Prompt + Memory   │──►│ RAG context   │──►│ Ollama (Llama 3)  │
└───────────────────┘   └───────────────┘   └─────────┬─────────┘
                                                      │
                                                      ▼
                                            ┌───────────────────┐
                                            │ clean_response()  │
                                            └─────────┬─────────┘
                                                      ▼
                                      SILENT output  /  INFERENCE trace
```

**Flow:**

1. User input arrives through the GUI (or through `JOIEye` in vision mode).
2. The input is combined with the system prompt and memory, and RAG adds relevant context.
3. The request is sent to Llama 3.0 through Ollama.
4. The raw output is sanitized by `clean_response()`.
5. The result is delivered to the GUI through `response_queue`.

---

## Requirements

| Component | Details |
|---|---|
| OS | Ubuntu 22.04(development environment); other Linux distributions are expected to work |
| Python | 3.10 or newer recommended |
| Ollama | Llama 3.0 model pulled locally |
| GPU | Developed on an NVIDIA RTX 4060; weaker hardware works but with slower responses |
| Libraries | `pygame` and everything listed in `requirements.txt` |

---

## Installation

> The repository URL and file names below are placeholders. Adjust them to match your repository.

### 1. Clone the repository

```bash
git clone https://github.com/yigit545/JOI2.0-AI.git
cd JOI2_0
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Ollama and pull the model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3
```

### 5. (Optional) Translation models

For better Turkish output quality (see [Translation](#translation-en--tr)):

```bash
pip install transformers sentencepiece torch
```

---

## Usage

Make sure the Ollama service is running:

```bash
ollama serve
```

Then start JOI:

```bash
# Vision mode + GUI
python3 JOI2_0_visionv2.py

# GUI only
python3 gui_app.py
```

### Command-line flags

| Flag | Description |
|---|---|
| `--no-vision` | Skip vision mode |
| `--quiet` | Suppress verbose logging |

> Flag names are illustrative. Update them to match the `argparse` definitions in your code.

---

## Operating Modes

### Text / GUI mode
Text interaction through the chat-bubble interface.

### Vision mode
The `JOIEye` component processes visual input in the pygame window. Responses are passed back to the interface through `response_queue`.

### SILENT and INFERENCE
- **SILENT:** The final output shown or spoken to the user.
- **INFERENCE:** The model's internal reasoning trace, kept separate from user-facing output.

---

## Project Structure

```
JOI2_0/
├── JOI2_0_visionv2.py     # Main app: vision mode + GUI entry point
├── gui_app.py             # Chat-bubble GUI
├── file_manager.py        # File management tool
├── package_manager.py     # Package management tool
├── requirements.txt
├── LICENSE
└── README.md
```

> Add any additional modules and folders (memory store, RAG index, etc.) to reflect the current layout.

---

## Tool Modules

JOI interacts with the system through modules that share a consistent signature. They use cross-platform dispatch and fall back gracefully when optional dependencies are missing.

### `file_manager.py`
Built on `os` and `shutil`. Supported operations:

- `list`: list directory contents
- `info`: get file or folder details
- `mkdir`: create a directory
- `rename`: rename a file or folder
- `move`: move a file or folder
- `copy`: copy a file or folder
- `delete`: delete a file or folder
- `search`: search for files

### `package_manager.py`
Built on `os.popen` and `os.system`. Supported operations: `check`, `update`, `upgrade`, `full`.

Supported package managers:

| Platform | Manager |
|---|---|
| Debian / Pardus / Ubuntu | `apt` |
| Fedora / RHEL | `dnf`, `yum` |
| Arch | `pacman` |
| openSUSE | `zypper` |
| macOS | `brew` |
| Windows | `winget` |

### Module signature convention

All tool modules follow the same parameter layout:

```python
def tool(parameters: dict, response=None, player=None, session_memory=None):
    ...
```

---

## Translation (EN → TR)

Llama 3.0's Turkish output quality can be limited, so English responses can be translated to Turkish with one of these models:

- **[Helsinki-NLP/opus-mt-en-tr](https://huggingface.co/Helsinki-NLP/opus-mt-en-tr):** lightweight and fast
- **[NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M):** broader coverage, higher quality

```python
from transformers import pipeline

translator = pipeline("translation", model="Helsinki-NLP/opus-mt-en-tr")
print(translator("Hello, how can I help you today?")[0]["translation_text"])
```

---

## Configuration

| Setting | Description |
|---|---|
| Model name | Ollama model to use (e.g. `llama3`) |
| System prompt | Defines JOI's personality and behavior |
| Memory | How conversation history is stored and recalled |
| RAG | Context sources and retrieval parameters |
| Translation | Enable/disable and model choice |

---

## Roadmap

- [x] Chat-bubble, scrollable GUI
- [x] `response_queue` wired through `JOIEye`
- [x] `clean_response()` for malformed model output
- [x] Tightened system prompt
- [x] Memory feature
- [x] `file_manager.py` and `package_manager.py`
- [x] **Prompt reviewer:** detect user intent to reduce the number of calls needed per task
- [x] **Coding ability:** tool use / code execution so JOI can write and run code
- [x] **GitHub API access**
- [x] **Stronger offline capability**, relying mainly on `os` and `sys`
- [ ] More tool modules: `computer_control`, `computer_settings`, `file_processor`, `browser_control`, `desktop`, `open_app`, `send_message`, `system_monitor`, `youtube_video`, `web_search`
- [ ] Integrated EN → TR translation
- [x] Better RAG context utilization

---

## Troubleshooting

**Cannot connect to Ollama**
Check that `ollama serve` is running and the model is available (`ollama list`).

**Model output is malformed or contains extra text**
Review `clean_response()` and the system prompt.

**Vision mode does not start**
Check camera access and the pygame installation, or launch with the flag that disables vision.

**Turkish responses are poor quality**
Enable the translation layer and try `opus-mt-en-tr` or NLLB-200.

**Package management commands fail**
Administrator (`sudo`) privileges may be required. Make sure your distribution's package manager is supported.

---

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes.
4. Push the branch and open a Pull Request.

When adding new tool modules, please follow the existing signature convention (`parameters, response, player, session_memory`) and the graceful-fallback approach.

---

## License

Copyright © 2026 Yiğit Erim Özdamar

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

You may inspect, study, modify, and use this software for **personal, educational, research, testing, and other non-commercial purposes**, subject to the terms of the license.

**Commercial use is not permitted without explicit permission from the copyright holder.**

For commercial licensing or permission, please contact the copyright holder.
