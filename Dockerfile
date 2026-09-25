FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libopus0 libsodium23 git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# ก็อปทั้ง repo (รวม image.png ถ้านายอัปไว้ ถ้าไม่มีก็ไม่พัง)
COPY . ./
CMD ["python", "bot.py"]
