FROM python:3.13
RUN useradd -m -d /home/container container
WORKDIR /opt/bot
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown -R container:container /opt/bot /home/container /entrypoint.sh
ENV USER=container HOME=/home/container
USER container
WORKDIR /home/container

CMD ["/bin/bash", "/entrypoint.sh"]
