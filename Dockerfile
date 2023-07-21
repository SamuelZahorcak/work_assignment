FROM python:3.12.0b4-slim-bookworm
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
CMD ["python","fsm.py"]