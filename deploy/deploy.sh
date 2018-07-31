#!/usr/bin/env bash
# deploy.py shortcut
dir=$(dirname "$0")
cd $dir && pipenv run ./deploy.py "$@" | $PAGER
