import paho.mqtt.client as mqtt
import json
import os
import signal
import sys
from typing import Dict, Any
from utils.logger import setup_logger
from baseDeDatos.mongodb import MongoDBClient
from mqtt.manejadores import MQTTMessageHandler

logger = setup_logger(__name__)

class MQTTClient:
    def __init__(self):
        # Configuración desde variables de entorno
        self.broker = os.getenv("MQTT_BROKER", "localhost")
        self.port = int(os.getenv("MQTT_PORT", 1883))
        self.client_id = os.getenv("MQTT_CLIENT_ID", "parkguard_consumer")
        self.topic_prefix = os.getenv("TOPIC_PREFIX", "/parkguard")
        
        # Clientes
        self.mqtt_client = mqtt.Client(client_id=self.client_id)
        self.db_client = MongoDBClient()
        self.handler = None
        
        # Flag para loop infinito
        self.running = True
        
        # Se configuran los callbacks
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        
        # Se manejan las señales para el cierre del graceful
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def connect(self) -> bool:
        # Se conecta a MongoDB
        if not self.db_client.connect():
            logger.error("Hubo problemas al conectar a MongoDB")
            return False
        
        self.handler = MQTTMessageHandler(self.db_client)
        
        # Se conecta al broker MQTT
        try:
            self.mqtt_client.connect(self.broker, self.port, 60)
            logger.info(f"Se ha conectado correctamente al broker MQTT {self.broker}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Hubo problemas al conectar al MQTT: {e}")
            return False
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("✅ Conexión MQTT establecida")
            
            # Se suscribe a los tópicos
            topics = [
                (f"{self.topic_prefix}/access/request", 1),      # Solicitudes RFID
                (f"{self.topic_prefix}/viv/vehicle_detected", 1),# Detección vehicular VIV
                (f"{self.topic_prefix}/occupancy/change", 1),    # Cambios de ocupación
                (f"{self.topic_prefix}/emergency/trigger", 2),   # Emergencias
                (f"{self.topic_prefix}/exit/request", 1),        # Solicitudes de salida
                (f"{self.topic_prefix}/fan/command", 1),         # Comandos de ventilador (desde frontend)
                (f"{self.topic_prefix}/space/manage", 1),        # Gestión de espacios (desde frontend)
                (f"{self.topic_prefix}/status/gas", 1),          # Nivel de gas
                (f"{self.topic_prefix}/registration/start", 1),  # Iniciar modo lector RFID
                (f"{self.topic_prefix}/registration/card_scanned", 1),  # Tarjeta leída por Raspberry
                (f"{self.topic_prefix}/users/list/request", 1),
                (f"{self.topic_prefix}/users/toggle/request", 1),
                (f"{self.topic_prefix}/users/delete/request", 1),
                (f"{self.topic_prefix}/users/update/request", 1),
                (f"{self.topic_prefix}/stats/request", 1),
            ]
            
            for topic, qos in topics:
                client.subscribe(topic, qos)
                logger.info(f"Se ha suscrito correctamente a {topic} (QoS {qos})")
                
            # Publicar que el consumer está activo
            client.publish(f"{self.topic_prefix}/system/consumer/status", "online", qos=1, retain=True)
            
        else:
            logger.error(f"Hubo problemas en la conexión de MQTT, código: {rc}")
    
    def on_message(self, client, userdata, msg):
        # Callback cuando llega un mensaje
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"📩 Mensaje recibido en {msg.topic}: {payload}")
            
            response = None
            response_topic = None
            
            # Se enruta según el tópico
            if msg.topic.endswith("/access/request"):
                response = self.handler.handle_access_request(payload)
                response_topic = f"{self.topic_prefix}/access/response"

            elif msg.topic.endswith("/viv/vehicle_detected"):
                response = self.handler.handle_viv_vehicle_detected(payload)
                response_topic = f"{self.topic_prefix}/access/response"
                
            elif msg.topic.endswith("/occupancy/change"):
                self.handler.handle_occupancy_change(payload)
                
            elif msg.topic.endswith("/emergency/trigger"):
                response = self.handler.handle_emergency_trigger(payload)
                response_topic = f"{self.topic_prefix}/emergency/command"
                
            elif msg.topic.endswith("/exit/request"):
                response = self.handler.handle_exit_request(payload)
                response_topic = f"{self.topic_prefix}/exit/command"
                
            elif msg.topic.endswith("/fan/command"):
                response = self.handler.handle_fan_command(payload)
                response_topic = f"{self.topic_prefix}/fan/control"
                
            elif msg.topic.endswith("/space/manage"):
                response = self.handler.handle_space_management(payload)
                response_topic = f"{self.topic_prefix}/space/status"
                
            elif msg.topic.endswith("/status/gas"):
                # Solo se registra el nivel de gas
                logger.info(f"📊 Nivel de gas: {payload.get('value')}")

            elif msg.topic.endswith("/registration/start"):
                response = self.handler.handle_registration_start(payload)
                response_topic = f"{self.topic_prefix}/registration/status"

            elif msg.topic.endswith("/registration/card_scanned"):
                response = self.handler.handle_registration_card_scanned(payload)
                response_topic = f"{self.topic_prefix}/registration/result"

            elif msg.topic.endswith("/users/list/request"):
                response = self.handler.handle_users_list_request(payload)
                response_topic = f"{self.topic_prefix}/users/list/response"

            elif msg.topic.endswith("/users/toggle/request"):
                response = self.handler.handle_user_toggle_request(payload)
                response_topic = f"{self.topic_prefix}/users/toggle/response"

            elif msg.topic.endswith("/users/delete/request"):
                response = self.handler.handle_user_delete_request(payload)
                response_topic = f"{self.topic_prefix}/users/delete/response"

            elif msg.topic.endswith("/users/update/request"):
                response = self.handler.handle_user_update_request(payload)
                response_topic = f"{self.topic_prefix}/users/update/response"

            elif msg.topic.endswith("/stats/request"):
                response = self.handler.handle_stats_request(payload)
                response_topic = f"{self.topic_prefix}/stats/response"
            
            # Se publica la respuesta si existe
            if response and response_topic:
                self.mqtt_client.publish(
                    response_topic,
                    json.dumps(response),
                    qos=1
                )
                logger.info(f"Se ha publicado la respuesta en {response_topic}")
            
        except json.JSONDecodeError:
            logger.error(f"Hubo problemas decodificando el JSON: {msg.payload}")
        except Exception as e:
            logger.error(f"Hubo problemas al procesar el mensaje: {e}")
    
    def on_disconnect(self, client, userdata, rc):
        # Callback cuando se desconecta del broker
        logger.warning("Se ha desconectado del broker MQTT")
    
    def signal_handler(self, signum, frame):
        # Se manejan las señales para cierre del graceful
        logger.info("Señal de terminación recibida, por lo tanto se está cerrando...")
        self.running = False
        self.mqtt_client.disconnect()
        self.db_client.close()
        sys.exit(0)
    
    def run(self):
        # Se inicia el loop principal
        logger.info("Iniciando con el ParkGuard Consumer...")
        
        if self.connect():
            self.mqtt_client.loop_start()
            
            logger.info("El Consumer está listo y está esperando los mensajes...")
            
            # Se mantiene vivo
            while self.running:
                try:
                    # Se publica el heartbeat cada 30 segundos
                    self.mqtt_client.publish(
                        f"{self.topic_prefix}/system/consumer/heartbeat",
                        "alive",
                        qos=0
                    )
                    
                    import time
                    time.sleep(30)
                    
                except KeyboardInterrupt:
                    break
                    
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.db_client.close()
            logger.info("El Consumer se ha detenido")
        else:
            logger.error("Hubo problemas al iniciar el Consumer")
            sys.exit(1)