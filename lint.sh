#!/bin/bash
flake8 . --count --show-source --statistics --max-line-length=120 --exclude "*/migrations/*"
