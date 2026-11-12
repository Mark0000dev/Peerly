# Exact official HAProxy base used by the credential-free transport proof.
FROM haproxy:3.2-alpine@sha256:96ec3c75a9264ba94e733eeacb44051ed6e7b79bb77a73c2c36f236b6423f1f0
COPY --chmod=0444 haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
COPY --chmod=0444 otlp.cfg /usr/local/etc/haproxy/otlp.cfg
COPY --chmod=0555 otlp-entrypoint.sh /usr/local/bin/peerly-ai-otlp
USER haproxy
CMD ["haproxy", "-W", "-db", "-f", "/usr/local/etc/haproxy/haproxy.cfg"]
