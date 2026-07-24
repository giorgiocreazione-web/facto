# -*- coding: utf-8 -*-
"""Fallback universale: `python -m facto ...`.

Se il comando `facto` non e' nel PATH (tipico di `pip install --user` su
Windows, dove gli script vanno in %APPDATA%\\Python\\...\\Scripts), questo modo
funziona SEMPRE — non dipende dal PATH, solo da `python`.
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
