FROM python:3.13-slim-bookworm

# Set correct timezone
RUN ln -sf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime

# Create generic xero user
RUN useradd -c "generic app user" -d /home/xero -s /bin/bash -m xero

# Switch to application directory, creating it if needed
WORKDIR /home/xero/project

# Make sure xero owns app directory, if WORKDIR created it:
# https://github.com/docker/docs/issues/13574
RUN chown -R xero:xero /home/xero

# Change context to xero user for remaining steps
USER xero

# Copy application files to image, and ensure xero user owns everything
COPY --chown=xero:xero . .

# Include local python bin into xero user's path, mostly for pip
ENV PATH=/home/xero/.local/bin:${PATH}

# Make sure pip is up to date, and don't complain if it isn't yet
RUN pip install --upgrade pip --disable-pip-version-check

# Install requirements for this application
RUN pip install --no-cache-dir -r requirements.txt --user --no-warn-script-location
