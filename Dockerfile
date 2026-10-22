FROM ubuntu:24.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Python 3.12
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3-full \
        python3-pip \
        python3.12-venv \
        python3-setuptools \
        build-essential \
        pkg-config \
        cmake \
        && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /opt/spidey-sense

# Copy the project source code
COPY src/ /opt/spidey-sense/src/
COPY pyproject.toml /opt/spidey-sense/
COPY install.sh /opt/spidey-sense/
COPY README.md /opt/spidey-sense/

# Install Python dependencies
# PySide6 via pip, dbus-python via apt, install project in editable mode
RUN python3 -m pip install --break-system-packages PySide6>=6.6.0 && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3-dbus && \
    python3 -m pip install --break-system-packages --no-cache-dir . && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables for X11 (host-side X11 will provide OpenGL)
ENV DISPLAY=:0
ENV QT_QPA_PLATFORM=x11

# Set the entry point
ENTRYPOINT ["python3", "-m", "hanging_reminder.app"]

# Default command (optional, can be overridden)
CMD ["--start-at-login"]