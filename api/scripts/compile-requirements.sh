#!/bin/sh
# Regenerate the API's lock files from the version ranges in the .in files:
#
#   requirements.in      -> requirements.txt      (what the image installs)
#   requirements-dev.in  -> requirements-dev.txt  (what the tests install)
#
# Each lock file pins every package, direct or not, to one version, with the
# sha256 hashes of its published files. pip-compile keeps the versions already
# in the lock files and only resolves what changed in the .in files, unless
# you pass --upgrade or --upgrade-package NAME.
#
# Run it with the Python of the image (the FROM line of api/Dockerfile), so
# the resolution matches what the image runs. From the api/ directory:
#
#   docker run --rm -v "$PWD":/api -w /api python:3.15-slim scripts/compile-requirements.sh
#   docker run --rm -v "$PWD":/api -w /api python:3.15-slim scripts/compile-requirements.sh --upgrade-package fastapi
#
# CI runs it too and fails if the lock files are not up to date.
set -eu

cd "$(dirname "$0")/.."

# Same pip-tools version everywhere, so the files come out byte for byte the same.
PIP_TOOLS_VERSION=7.6.2
python -m pip install --quiet --disable-pip-version-check "pip-tools==${PIP_TOOLS_VERSION}"

# The dev file is constrained by requirements.txt, so compile that one first.
python -m piptools compile --quiet --generate-hashes --strip-extras \
    --output-file=requirements.txt "$@" requirements.in
python -m piptools compile --quiet --generate-hashes --strip-extras \
    --output-file=requirements-dev.txt "$@" requirements-dev.in

echo "Updated requirements.txt and requirements-dev.txt. Commit them with the .in files."
