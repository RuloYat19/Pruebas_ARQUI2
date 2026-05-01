FROM python:3.11-slim

WORKDIR /app

# Se instalan las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables de entorno por defecto
ENV MQTT_BROKER=mosquitto
ENV MQTT_PORT=1883
ENV MONGO_URI=mongodb://mongodb:27017/
ENV TOPIC_PREFIX=/parkguard

# Comando por defecto
CMD ["python", "main.py"]