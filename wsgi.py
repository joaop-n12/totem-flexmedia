"""Ponto de entrada WSGI para servidores de produção (Gunicorn/uWSGI).

Em produção, o Gunicorn carrega este módulo e usa o objeto `application`.
Não executar diretamente — use `gunicorn -c gunicorn.conf.py wsgi:application`.
"""
import os
from app import create_app

application = create_app(os.environ.get("FLASK_ENV", "production"))
app = application
