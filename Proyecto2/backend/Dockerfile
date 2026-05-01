FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MONGO_URI=mongodb://mongodb:27017/
ENV MONGO_DB=parkguard_db
ENV JWT_SECRET=parkguard-dev-secret
ENV JWT_EXPIRE_MINUTES=480
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=admin

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]