FROM python:3.13
RUN useradd -m -d /home/container container
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=container:container . .
# RUN chmod -r 777 . test without
ENV USER=container HOME=/home/container
USER container
WORKDIR /home/container
CMD ["python3", "/app/main.py"]
