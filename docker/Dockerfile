# Test image: twinbird + a pinned netbird binary, for running NetBird instances
# inside an isolated container network namespace (no collision with the host daemon).
#
# Build:  docker build -f docker/Dockerfile -t twinbird-test .
# Run:    docker run -d --name tb-test \
#             --cap-add=NET_ADMIN --device=/dev/net/tun \
#             twinbird-test
# Use:    docker exec tb-test twinbird up <name> \
#             --management-url https://api.netbird.io:443 --setup-key <KEY>
FROM python:3.11-slim

ARG NETBIRD_VERSION=0.72.1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl iproute2 iptables \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/netbirdio/netbird/releases/download/v${NETBIRD_VERSION}/netbird_${NETBIRD_VERSION}_linux_amd64.tar.gz" \
        | tar -xz -C /usr/local/bin netbird \
    && netbird version

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Keep the container (and thus the detached netbird daemons twinbird spawns) alive.
CMD ["sleep", "infinity"]
