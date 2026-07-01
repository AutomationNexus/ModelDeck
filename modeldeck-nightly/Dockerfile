ARG BUILD_FROM=ghcr.io/automationnexus/modeldeck:nightly
FROM ${BUILD_FROM}

USER root
RUN apt-get update \
    && apt-get install --no-install-recommends -y bash util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
