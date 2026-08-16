#!/bin/bash

sudo apt install python3-venv python3-pip   # Debian/Ubuntu
python3 -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
