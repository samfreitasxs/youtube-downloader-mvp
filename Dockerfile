# Use uma imagem base do Python
FROM python:3.11-slim

# Instala dependências do sistema (apenas ffmpeg)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Cria diretório de trabalho
WORKDIR /app

# Copia e instala dependências Python para otimizar o cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos do projeto
COPY . .

# Expõe a porta que o Gunicorn vai usar
EXPOSE 5000

# Comando para rodar a aplicação com Gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]