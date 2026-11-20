ARG POSTGRES_IMAGE=pgvector/pgvector:pg17
FROM ${POSTGRES_IMAGE}
ARG DEBIAN_MIRROR=http://deb.debian.org
RUN sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|" /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Dir::Etc::sourceparts=- -o Dir::Etc::sourcelist=sources.list.d/debian.sources \
    && apt-get install -y --no-install-recommends python3 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY run_reader.py /opt/run-reader.py
USER 65532:65532
ENTRYPOINT ["/usr/bin/python3", "-IB", "/opt/run-reader.py"]
CMD []
