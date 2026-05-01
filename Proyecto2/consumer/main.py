#!/usr/bin/env python3
from dotenv import load_dotenv
import os
import sys

# Se cargan las variables de entorno
load_dotenv()

from utils.logger import setup_logger
from mqtt.client import MQTTClient

logger = setup_logger(__name__)

def main():
    logger.info("=" * 60)
    logger.info("PARKGUARD 2.0 - MQTT CONSUMER")
    logger.info("=" * 60)
    
    # Se verifican las variables de entorno
    required_vars = [
        "MQTT_BROKER", 
        "MONGO_URI"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Hay variables faltantes: {missing}")
        sys.exit(1)
    
    # Se inicia el cliente
    client = MQTTClient()
    client.run()

if __name__ == "__main__":
    main()