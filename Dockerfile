# Hermes Life OS - zero-install container image.
#
# Quickest possible trial (with a local Ollama container, no API key at all):
#   docker compose up -d
#   docker compose exec ollama ollama pull llama3.1
#   docker compose run --rm hermes-life-os --mode onboard
#
# Or standalone, with your own provider key:
#   docker build -t hermes-life-os .
#   docker run --rm -it -e ANTHROPIC_API_KEY=sk-ant-... \
#       -v hermes-life-os-data:/root/.hermes \
#       hermes-life-os --mode morning

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist user data (mood/sleep/nutrition logs, profile, habits, goals)
# across container runs by mounting a volume here.
VOLUME ["/root/.hermes"]

ENTRYPOINT ["python", "demo/demo_life_os.py"]
CMD ["--mode", "onboard"]
