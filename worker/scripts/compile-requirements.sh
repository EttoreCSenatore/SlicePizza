#!/bin/sh
# Regenerate the worker's lock files from the version ranges in the .in files:
#
#   requirements.in        -> requirements.txt        (what the image installs)
#   requirements-dev.in    -> requirements-dev.txt    (what the tests install)
#   requirements-tools.in  -> requirements-tools.txt  (pip-tools, which runs this)
#
# Each lock file pins every package, direct or not, to one version, with the
# sha256 hashes of its published files. pip-compile keeps the versions already
# in the lock files and only resolves what changed in the .in files, unless
# you pass --upgrade or --upgrade-package NAME.
#
# It must run with the Python in worker/.python-version, the one of the image
# (CI checks that the FROM line of worker/Dockerfile matches it). From worker/:
#
#   docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/worker -w /worker \
#       "python:$(cat .python-version)-slim" scripts/compile-requirements.sh
#
# Add --upgrade-package pika (or --upgrade) at the end to update packages.
# CI runs it too and fails if the lock files are not up to date.
set -eu

cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}
want=$(cat .python-version)
have=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if [ "$have" != "$want" ]; then
    echo "error: $PYTHON is Python $have, but the lock files are for Python $want (.python-version)." >&2
    echo "Run it in Docker instead: see the top of this script." >&2
    exit 1
fi

# A throwaway virtual environment: nothing is installed into your Python or
# your .venv, and pip-tools comes from its own lock file, hashes checked.
venv=$(mktemp -d)
trap 'rm -rf "$venv"' EXIT
"$PYTHON" -m venv "$venv"
"$venv/bin/python" -m pip install --quiet --disable-pip-version-check \
    --require-hashes --only-binary=:all: -r requirements-tools.txt

# --no-reuse-hashes: take every hash from PyPI again instead of copying the
# ones already in the lock file, so a hash edited by hand does not survive.
compile() {
    "$venv/bin/python" -m piptools compile --quiet --generate-hashes \
        --no-reuse-hashes --strip-extras "$@"
}

# The dev file is constrained by requirements.txt, so compile that one first.
compile --output-file=requirements.txt "$@" requirements.in
compile --output-file=requirements-dev.txt "$@" requirements-dev.in
# --allow-unsafe: pin pip and setuptools too, which pip-tools needs.
compile --allow-unsafe --output-file=requirements-tools.txt "$@" requirements-tools.in

echo "Updated the requirements*.txt lock files. Commit them with the .in files."
