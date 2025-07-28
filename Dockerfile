# 1) Imagem base
FROM python:3.11-slim

# 2) Diretório de trabalho dentro do container
WORKDIR /app

# 3) Dependências de sistema (psycopg2-binary já traz o driver, mas
#    incluímos gcc/libpq-dev caso precise compilar algo)
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# 4) Copia e instala os requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) Copia o código-fonte
COPY backend/ .

# 6) Variáveis de ambiente para rodar o Flask
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

# 7) Porta que a aplicação irá escutar
EXPOSE 5000

# 8) Comando padrão para iniciar o servidor
CMD ["flask", "run"]
