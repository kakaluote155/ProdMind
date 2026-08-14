FROM python:3.12.12-bookworm AS python-runtime
FROM maven:3.9.9-eclipse-temurin-21 AS maven-runtime
FROM node:22.18.0-bookworm

COPY --from=python-runtime /usr/local/ /usr/local/
COPY --from=maven-runtime /opt/java/openjdk/ /opt/java/openjdk/
COPY --from=maven-runtime /usr/share/maven/ /usr/share/maven/

ENV JAVA_HOME=/opt/java/openjdk \
    PATH=/usr/share/maven/bin:/opt/java/openjdk/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY server/requirements-runtime.lock /tmp/requirements-runtime.lock
RUN python -m pip install --no-cache-dir \
    -r /tmp/requirements-runtime.lock \
    build \
    "pytest>=8.4,<9.0" \
    "opentelemetry-sdk>=1.30,<2.0"

WORKDIR /work

CMD ["python", "scripts/build-release.py"]
