
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from time import monotonic
import uuid

try:
	import cv2  # type: ignore[import-not-found]
	from ultralytics import YOLO  # type: ignore[import-not-found]
	import easyocr  # type: ignore[import-not-found]
	import paho.mqtt.client as mqtt  # type: ignore[import-not-found]
except ImportError as exc:
	print(f"Missing dependency: {exc.name}. Install required packages.", file=sys.stderr)
	raise SystemExit(1) from exc


ALLOWED_CLASSES = {"car", "motorcycle"}
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC_PREFIX = os.getenv("TOPIC_PREFIX", "/parkguard")
MQTT_CLIENT_ID = f"viv_model_{uuid.uuid4().hex[:8]}"

# Initialize OCR reader globally (initialized on first use)
_ocr_reader = None


def get_ocr_reader():
	"""Get or initialize the OCR reader."""
	global _ocr_reader
	if _ocr_reader is None:
		print("Initializing OCR reader...")
		_ocr_reader = easyocr.Reader(['en', 'es'], gpu=False)
	return _ocr_reader


def extract_plate_text(frame: cv2.Mat, x1: int, y1: int, x2: int, y2: int) -> str | None:
	"""Extract plate text from a region of the frame using OCR."""
	try:
		# Extract the region containing the vehicle
		roi = frame[y1:y2, x1:x2]
		if roi.size == 0:
			return None
		
		# Preprocess the image for better OCR results
		gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
		# Enhance contrast
		clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
		enhanced = clahe.apply(gray)
		
		# Get OCR results
		reader = get_ocr_reader()
		results = reader.readtext(enhanced, detail=0)
		
		if results:
			# Join all detected text
			text = " ".join(results)
			# Filter to keep only alphanumeric characters
			cleaned_text = "".join(c for c in text if c.isalnum() or c.isspace()).strip()
			if cleaned_text:
				return cleaned_text
		
		return None
	except Exception as e:
		print(f"OCR error: {e}")
		return None


def normalize_label(label: str) -> str | None:
	normalized = label.strip().lower()
	car_variants = {"car", "carro", "sedan", "vehicle", "auto", "automobile"}
	motorcycle_variants = {"motorcycle", "motorbike", "moto", "bike"}
	
	if normalized in car_variants:
		return "car"
	if normalized in motorcycle_variants:
		return "motorcycle"
	return None


def open_video_source(source: int | str) -> cv2.VideoCapture:
	backends = []
	if sys.platform.startswith("win"):
		backends.extend([cv2.CAP_DSHOW, cv2.CAP_MSMF])
	backends.append(cv2.CAP_ANY)

	if isinstance(source, int):
		source_candidates = [source] + list(range(source + 1, source + 5))
	else:
		source_candidates = [source]

	for candidate in source_candidates:
		for backend in backends:
			capture = cv2.VideoCapture(candidate, backend)
			if capture.isOpened():
				if isinstance(candidate, int) and candidate != source:
					print(f"Using camera index {candidate} instead of {source}.")
				return capture
			capture.release()

	return cv2.VideoCapture(source)


def create_mqtt_client() -> mqtt.Client | None:
	try:
		client = mqtt.Client(client_id=MQTT_CLIENT_ID)
		client.connect(MQTT_BROKER, MQTT_PORT, 60)
		client.loop_start()
		print(f"MQTT conectado a {MQTT_BROKER}:{MQTT_PORT}")
		return client
	except Exception as exc:
		print(f"No se pudo conectar a MQTT: {exc}")
		return None


def publish_vehicle_detection(client: mqtt.Client | None, vehicle_type: str, plate_text: str, confidence: float) -> None:
	if client is None or not plate_text:
		return

	vehicle_topic = f"{MQTT_TOPIC_PREFIX}/viv/vehicle_detected"
	plate_topic = f"{MQTT_TOPIC_PREFIX}/viv/plate_detected"
	type_topic = f"{MQTT_TOPIC_PREFIX}/tipo/carro" if vehicle_type == "car" else f"{MQTT_TOPIC_PREFIX}/tipo/moto"
	payload = {
		"tipo": vehicle_type,
		"placa": plate_text,
		"confidence": round(float(confidence), 4),
		"timestamp": datetime.now().isoformat(),
		"source": "viv"
	}
	client.publish(vehicle_topic, json.dumps(payload), qos=1)
	client.publish(type_topic, json.dumps(payload), qos=1)
	client.publish(plate_topic, json.dumps({
		"placa": plate_text,
		"tipo": vehicle_type,
		"confidence": round(float(confidence), 4),
		"timestamp": payload["timestamp"],
		"source": "viv"
	}), qos=1)


def main() -> int:
	parser = argparse.ArgumentParser(description="Detect cars and motorcycles using webcam.")
	parser.add_argument("--model", default="yolov8n.pt", help="Model path or name.")
	parser.add_argument("--source", default=0, help="Webcam index or video path.")
	parser.add_argument("--conf", type=float, default=0.5, help="Confidence threshold.")
	parser.add_argument("--imgsz", type=int, default=960, help="Inference image size.")
	parser.add_argument("--save-dir", type=Path, default=Path("capturas_viv"), help="Directory to save images.")
	parser.add_argument("--save-interval", type=float, default=1.5, help="Seconds between saves.")
	args = parser.parse_args()

	model = YOLO(args.model)
	source = int(args.source) if str(args.source).isdigit() else args.source
	capture = open_video_source(source)
	mqtt_client = create_mqtt_client()
	args.save_dir.mkdir(parents=True, exist_ok=True)
	last_saved_at = 0.0

	if not capture.isOpened():
		print(f"Unable to open video source: {args.source}", file=sys.stderr)
		return 1

	print("Detecting cars and motorcycles. Press 'q' to quit.")

	try:
		while True:
			ok, frame = capture.read()
			if not ok:
				break

			# Flip the frame vertically (invert Y axis)
			frame = cv2.flip(frame, 0)
			#FLIP HORIZONTAL
			

			results = model.predict(frame, conf=args.conf, imgsz=args.imgsz, verbose=False)
			
			detections = []
			names = results[0].names
			for box in results[0].boxes:
				class_id = int(box.cls[0])
				confidence = float(box.conf[0])
				raw_label = names.get(class_id, str(class_id)) if isinstance(names, dict) else names[class_id]
				normalized_label = normalize_label(raw_label)
				
				if not normalized_label:
					continue
				
				x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
				
				# Extract plate text from the vehicle region
				plate_text = extract_plate_text(frame, x1, y1, x2, y2)
				
				detections.append({
					"label": normalized_label,
					"confidence": confidence,
					"box": (x1, y1, x2, y2),
					"plate_text": plate_text
				})

			annotated = frame.copy()
			for det in detections:
				x1, y1, x2, y2 = det["box"]
				cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 200, 0), 2)
				
				# Display vehicle label and confidence
				cv2.putText(
					annotated,
					f"{det['label']} {det['confidence']:.2f}",
					(x1, max(20, y1 - 30)),
					cv2.FONT_HERSHEY_SIMPLEX,
					0.6,
					(0, 200, 0),
					2,
				)
				
				# Display plate text if detected
				if det["plate_text"]:
					cv2.putText(
						annotated,
						f"Placa: {det['plate_text']}",
						(x1, max(20, y1 - 10)),
						cv2.FONT_HERSHEY_SIMPLEX,
						0.5,
						(0, 255, 255),
						2,
					)

			if detections:
				for det in detections:
					if det["plate_text"]:
						print(f"Detección: {det['label']} ({det['confidence']:.2f}) - Placa: {det['plate_text']}")
						publish_vehicle_detection(mqtt_client, det["label"], det["plate_text"], det["confidence"])
					else:
						print(f"Detección: {det['label']} ({det['confidence']:.2f}) - Placa: No detectada")

				if any(det["plate_text"] for det in detections):
					now = monotonic()
					if now - last_saved_at >= args.save_interval:
						timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
						output_file = args.save_dir / f"vehiculo_{timestamp}.jpg"
						cv2.imwrite(str(output_file), annotated)
						print(f"Saved: {output_file}")
						last_saved_at = now

			cv2.imshow("Vehicle Detection - Cars & Motorcycles", annotated)
			if cv2.waitKey(1) & 0xFF == ord("q"):
				break
	finally:
		capture.release()
		if mqtt_client is not None:
			mqtt_client.loop_stop()
			mqtt_client.disconnect()
		cv2.destroyAllWindows()

	return 0


if __name__ == "__main__":
	raise SystemExit(main())