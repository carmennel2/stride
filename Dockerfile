FROM python:3.11-slim AS builder

# gcc/g++ for the numpy + scikit-learn wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user gunicorn==21.2.0


FROM python:3.11-slim AS runtime

RUN useradd --create-home --uid 1000 stride
USER stride
WORKDIR /home/stride/app

COPY --from=builder /root/.local /home/stride/.local
ENV PATH=/home/stride/.local/bin:$PATH

COPY --chown=stride:stride . .

RUN mkdir -p instance

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "stride:create_app()"]
