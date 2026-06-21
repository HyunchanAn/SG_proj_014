FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# Install Python 3.10
RUN apt-get update && apt-get install -y software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y python3.10 python3.10-distutils curl \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN python3.10 -m pip install --no-cache-dir -e .

COPY . .

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
