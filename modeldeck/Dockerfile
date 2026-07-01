ARG BUILD_FROM=ghcr.io/automationnexus/modeldeck:v0.0.7
FROM ${BUILD_FROM}

USER root
RUN apt-get update \
    && apt-get install --no-install-recommends -y bash util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod +x /run.sh

# Stay root so run.sh can read Supervisor-owned /data/options.json, then drop privileges.
CMD ["/run.sh"]