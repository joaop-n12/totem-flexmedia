"""Testes da API de IA — /api/chat e /api/voice.

A OpenAI eh mockada para garantir que nenhum teste gere custo real.
Cobertura:
  - 400 quando mensagem vazia
  - 200 no caminho feliz (mock da resposta)
  - 429 quando a quota diaria por tenant eh atingida
  - 503 quando a OpenAI esta offline (APIConnectionError)
"""
from unittest.mock import patch, MagicMock
import pytest

from app.extensions import db
from app.models import Institution, InteractionLog


# ── Helpers de mock ──────────────────────────────────────────────────────────

def _mock_chat_client(answer="Resposta simulada"):
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=answer))]
    )
    return client


# ── /api/chat ────────────────────────────────────────────────────────────────

def test_chat_mensagem_vazia(client):
    r = client.post("/teste/api/chat", json={"message": ""})
    assert r.status_code == 400


def test_chat_caminho_feliz(client, app):
    with patch("app.routes.voice._get_client", return_value=_mock_chat_client("Oi!")):
        r = client.post("/teste/api/chat", json={"message": "Ola"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["response"] == "Oi!"
    # Verifica que o InteractionLog foi gravado
    with app.app_context():
        assert InteractionLog.query.count() == 1


def test_chat_quota_diaria_bloqueia(client, app):
    # Zera a quota da instituicao — qualquer chamada deve ser barrada antes da OpenAI.
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        inst.daily_ai_quota = 1
        # Cria 1 log hoje para ja estar no limite
        db.session.add(InteractionLog(
            institution_id=inst.id, input_text="x", response_text="y", input_type="text",
        ))
        db.session.commit()

    # Nao deveria nem chegar na OpenAI — falharia se chamasse (client nao mockado)
    r = client.post("/teste/api/chat", json={"message": "Ola"})
    assert r.status_code == 429
    data = r.get_json()
    assert data["error"] == "quota"
    assert "limite" in data["message"].lower()


def test_chat_openai_offline(client):
    from openai import APIConnectionError
    broken = MagicMock()
    broken.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
    with patch("app.routes.voice._get_client", return_value=broken):
        r = client.post("/teste/api/chat", json={"message": "Ola"})
    assert r.status_code == 503
    assert r.get_json()["error"] == "offline"


# ── /api/voice ───────────────────────────────────────────────────────────────

def test_voice_sem_audio(client):
    r = client.post("/teste/api/voice", data={})
    assert r.status_code == 400


def test_voice_quota_bloqueia_antes_de_processar(client, app):
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        inst.daily_ai_quota = 1
        db.session.add(InteractionLog(
            institution_id=inst.id, input_text="x", response_text="y", input_type="voice",
        ))
        db.session.commit()
    r = client.post("/teste/api/voice", data={})
    assert r.status_code == 429
    assert r.get_json()["error"] == "quota"
