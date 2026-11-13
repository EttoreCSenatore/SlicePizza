# The "web" image: Caddy with the menu site inside, in front of the API.
# Build it from the repository root (it needs frontend/ and infra/caddy/):
#
#   docker build -f infra/caddy/Dockerfile -t slicepizza-web .
#
# The root .dockerignore keeps everything else out of the build context.
FROM caddy:2-alpine

# The official image gives the caddy binary the capability to bind ports below
# 1024. This image listens on 8080 and runs with all capabilities dropped and
# no-new-privileges, so remove it: a binary asking for a capability it cannot
# get may fail to start.
RUN setcap -r /usr/bin/caddy

COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
COPY frontend/menu/ /srv/

# Caddy writes nothing to disk with this Caddyfile, but point its folders to a
# place an unprivileged user can write, just in case.
ENV XDG_CONFIG_HOME=/tmp/caddy/config \
    XDG_DATA_HOME=/tmp/caddy/data

# Same unprivileged uid as the API image.
USER 10001:10001

EXPOSE 8080

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
