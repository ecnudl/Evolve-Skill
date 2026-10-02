# Build context: this runtime/ directory, NEVER the repository root/.env.
# Select a reviewed Python 3.11 Linux base and supply its repository digest.
# Example: --build-arg BASE_IMAGE=python@sha256:<recorded-manifest-digest>
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
LABEL org.opencontainers.image.title="Evolve-Skill KOR and Spreadsheet native runtime"
ENV PYTHONDONTWRITEBYTECODE=1
COPY requirements-native.txt /opt/requirements-native.txt
RUN python -m pip install --no-cache-dir -r /opt/requirements-native.txt
RUN python -c "import openpyxl,pandas,numpy,sympy,antlr4,yaml,tqdm; from sympy.parsing.latex import parse_latex; assert str(parse_latex('x+1')) == 'x + 1'"
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python"]
