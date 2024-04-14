#!/usr/bin/env bash

set -e

# TODO: Install only dependencies from pyproject.toml, not the package as well
# https://github.com/pypa/pip/issues/11440
# python -m pip install --upgrade ../

# Keep in sync with pyproject.toml dependencies sections
pip install --upgrade xsdata typing_extensions
