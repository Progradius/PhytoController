# syntax=docker/dockerfile:1

########################################
# 1) Base Python slim
########################################
FROM python:3.9.22-slim-bullseye

########################################
# 2) Variables d'environnement
########################################
ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

########################################
# 3) Dépendances système (+ sudo + réseau + ping + timedatectl)
########################################
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3-rpi.gpio \
      i2c-tools \
      build-essential \
      sudo \
      network-manager \
      iputils-ping \
      systemd && \
    rm -rf /var/lib/apt/lists/*

########################################
# 4) Création d'un user non-root et droits sudo
########################################
RUN useradd -m appuser \
 && echo "appuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

########################################
# 5) Répertoire de travail
########################################
WORKDIR /app
COPY . .
RUN chown -R appuser:appuser /app

########################################
# 6) Switch to root user et installer Python deps
########################################
COPY requirements.txt .
RUN sudo pip install --no-cache-dir -r requirements.txt

USER appuser
########################################
# 7) Exposer le port HTTP
########################################
EXPOSE 8123

########################################
# 8) Lancement de votre application en sudo
########################################
CMD ["sudo", "python3", "main.py"]
