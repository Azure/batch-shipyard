#!/usr/bin/env bash

set -e
set -o pipefail

# environment variables used
# SHIPYARD_USER_PROLOGUE_CMD: pre-exec user cmd
# SHIPYARD_USER_EPILOGUE_CMD: post-exec user cmd
# SHIPYARD_ENV_EXCLUDE: environment vars to exclude
# SHIPYARD_ENV_FILE: env file
# SHIPYARD_RUNTIME: docker or singularity
# SHIPYARD_RUNTIME_CMD: run or exec
# SHIPYARD_RUNTIME_CMD_OPTS: options
# SHIPYARD_CONTAINER_IMAGE_NAME: container name
# SHIPYARD_USER_CMD: user command

## PRE-EXEC
if [ -n "$SHIPYARD_USER_PROLOGUE_CMD" ]; then
    eval "$SHIPYARD_USER_PROLOGUE_CMD"
fi

## TASK EXEC
# dump env for envfile
if [ -n "$SHIPYARD_ENV_EXCLUDE" ]; then
    env | grep -vE "$SHIPYARD_ENV_EXCLUDE" > "$SHIPYARD_ENV_FILE"
else
    env > "$SHIPYARD_ENV_FILE"
fi

SHIPYARD_RUNTIME_CMD_OPTS=$(eval echo "${SHIPYARD_RUNTIME_CMD_OPTS}")

if [ -n "$SHIPYARD_RUNTIME" ]; then
    eval "$SHIPYARD_RUNTIME $SHIPYARD_RUNTIME_CMD $SHIPYARD_RUNTIME_CMD_OPTS \
        $SHIPYARD_CONTAINER_IMAGE_NAME $SHIPYARD_USER_CMD"
else
    eval "$SHIPYARD_USER_CMD"
fi

## POST EXEC
if [ -n "$SHIPYARD_USER_EPILOGUE_CMD" ]; then
    eval "$SHIPYARD_USER_EPILOGUE_CMD"
fi
