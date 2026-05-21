"""Configuração do Gunicorn para o Totem FlexMedia em produção.

Uso:
    gunicorn -c gunicorn.conf.py wsgi:application
"""
import multiprocessing
import os

# Socket Unix — o Nginx faz proxy_pass para este socket.
bind = os.environ.get("GUNICORN_BIND", "unix:/tmp/totem-flexmedia.sock")

# Workers: para um Raspberry Pi 4/5 (4 cores) mantemos 2 workers.
# Totens atendem poucos usuários simultâneos, não precisa (2*cores)+1.
workers = int(os.environ.get("GUNICORN_WORKERS", 2))
# gthread (nao "sync"): o worker sync IGNORA `threads`, entao com sync o totem
# tinha so 2 slots reais (workers x 1). A SSE de /api/local/wake-stream prende
# 1 slot permanentemente — sobra 1 pro resto e qualquer concorrencia fila.
# Sintoma: POST /api/heartbeat travando ate o timeout do client.
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# Timeouts (segundos). A IA/Whisper pode demorar, por isso 60s.
timeout = 60
graceful_timeout = 30
keepalive = 5

# Reinicia workers para evitar leak de memória (útil em Pi).
max_requests = 1000
max_requests_jitter = 100

# Logs
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Identificação do processo
proc_name = "totem-flexmedia"

# Permissões do socket (nginx precisa ler/escrever)
umask = 0o007
