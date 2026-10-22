#!/bin/bash
# Docker-run script for Spider-Man Hanging Reminder
# Sets up X11 forwarding and volume mounts for persistence

set -e

# Check if DISPLAY is set
if [ -z "$DISPLAY" ]; then
    echo "ERROR: DISPLAY variable not set. Please run with X11 forwarding."
    echo "Example: xhost +local:docker && DISPLAY=\$DISPLAY ./run-docker.sh"
    exit 1
fi

# Allow X11 connections from the Docker container
xhost +local:docker 2>/dev/null || echo "xhost already set or not available"

# Get the current user's UID and GID
UID=$(id -u)
GID=$(id -g)

# Run the Docker container with:
# - X11 socket forwarding (/tmp/.X11-unix)
# - X11 authentication (XAUTHORITY)
# - Persistent storage for SQLite tasks (~/.local/share/spidey-sense)
# - Persistent storage for config (~/.config/spidey-sense)
# - User namespace matching (UID:GID) via env vars
# - PYTHONPATH set to the mounted source directory
docker run -d \
    -e DISPLAY=$DISPLAY \
    -e XAUTHORITY=${XAUTHORITY:-/home/$USER/.Xauthority} \
    -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -v ${XAUTHORITY:-/home/$USER/.Xauthority}:/home/$USER/.Xauthority:ro \
    -v ~/.local/share/spidey-sense:/opt/spidey-sense/.local/share/spidey-sense:Z \
    -v ~/.config/spidey-sense:/opt/spidey-sense/.config/spidey-sense:Z \
    -e PYTHONPATH=/opt/spidey-sense/src \
    -e PUID=$UID \
    -e PGID=$GID \
    --user $UID:$GID \
    --rm \
    spidey-sense:latest

# Restore X11 access for local users
xhost -local:docker 2>/dev/null || true