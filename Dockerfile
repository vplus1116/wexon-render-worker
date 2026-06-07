FROM python:3.11-slim

# ffmpeg + шрифты (для субтитров) + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Piper TTS (бинарь + либы)
RUN curl -sL -o /tmp/piper.tar.gz \
    https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
 && tar xzf /tmp/piper.tar.gz -C /app \
 && rm /tmp/piper.tar.gz

# Голоса (MVP: русский + английский; остальные языки маппятся в handler.py)
RUN mkdir -p /app/voices \
 && curl -sL -o /app/voices/ru_RU-irina-medium.onnx \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx?download=true" \
 && curl -sL -o /app/voices/ru_RU-irina-medium.onnx.json \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json?download=true" \
 && curl -sL -o /app/voices/en_US-amy-medium.onnx \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx?download=true" \
 && curl -sL -o /app/voices/en_US-amy-medium.onnx.json \
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json?download=true"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY render_t1.py handler.py ./
COPY music/ /app/music/

# RunPod serverless воркер
CMD ["python", "-u", "handler.py"]
