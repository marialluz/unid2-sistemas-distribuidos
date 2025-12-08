FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl

COPY main.py .
RUN pip install flask requests

CMD ["python", "main.py"]