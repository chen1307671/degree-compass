FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=10000
COPY src ./src
COPY reports ./reports
COPY raw ./raw
COPY run.py ./
EXPOSE 10000
CMD ["sh", "-c", "python run.py --serve --port ${PORT}"]
