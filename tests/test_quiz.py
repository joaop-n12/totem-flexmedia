"""Testes do modulo Quiz/Curiosidades.

Cobre:
  - Modelo QuizQuestion: serializacao de opcoes, is_valid, to_public_dict
    (NAO vaza correct_index/curiosity).
  - Rota publica /<slug>/quiz exige modulo 'quiz' habilitado.
  - POST /<slug>/api/quiz/answer: valida payload, isola tenant, registra
    log, devolve curiosidade.
  - Validacao de cross-tenant: pergunta de outra instituicao nao pode
    ser respondida pelo slug errado.
  - Limites: opcoes em excesso descartadas; choice fora de range rejeitado.
"""
import json

import pytest

from app.extensions import db
from app.models import (
    InstitutionModule, InteractionLog, QuizQuestion, Institution,
)


# ── Fixture: institui modulo quiz na inst de teste ────────────────────────────

@pytest.fixture
def quiz_setup(app):
    """Habilita o modulo 'quiz' e cria 3 perguntas validas."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        # Habilita o modulo (a fixture conftest cria so 'ia').
        if not inst.has_module("quiz"):
            db.session.add(InstitutionModule(
                institution_id=inst.id, module_slug="quiz",
                enabled=True, order=99,
            ))
        for i, txt in enumerate(["Qual cor do céu?", "2 + 2 = ?", "Capital do BR?"]):
            q = QuizQuestion(
                institution_id=inst.id,
                question=txt,
                correct_index=0,
                curiosity=f"Curiosidade {i}",
                category="Geral",
                order=i,
                active=True,
            )
            q.options = ["Resposta certa", "Errada A", "Errada B"]
            db.session.add(q)
        db.session.commit()
        return {"institution_id": inst.id}


# ════════════════════════════════════════════════════════════════════════════
# Modelo
# ════════════════════════════════════════════════════════════════════════════

def test_options_round_trip(app):
    with app.app_context():
        q = QuizQuestion(institution_id=1, question="?", correct_index=0)
        q.options = ["A", "B", "C"]
        # options_json e' a fonte; reading via property reconstroi.
        assert json.loads(q.options_json) == ["A", "B", "C"]
        assert q.options == ["A", "B", "C"]


def test_options_setter_descarta_strings_vazias(app):
    with app.app_context():
        q = QuizQuestion(institution_id=1, question="?", correct_index=0)
        q.options = ["A", "", " ", "B"]
        assert q.options == ["A", "B"]


def test_options_setter_trunca_excesso(app):
    """Mais de MAX_OPTIONS sao descartadas (defesa contra payload gigante)."""
    with app.app_context():
        q = QuizQuestion(institution_id=1, question="?", correct_index=0)
        q.options = [f"opt{i}" for i in range(20)]
        from app.models.quiz import MAX_OPTIONS
        assert len(q.options) == MAX_OPTIONS


def test_is_valid_true_para_pergunta_completa(app):
    with app.app_context():
        q = QuizQuestion(institution_id=1, question="?", correct_index=0)
        q.options = ["A", "B"]
        assert q.is_valid() is True


@pytest.mark.parametrize("setup,bad", [
    (lambda q: setattr(q, "question", ""), "pergunta vazia"),
    (lambda q: setattr(q, "options_json", "[\"A\"]"), "menos de 2 opcoes"),
    (lambda q: setattr(q, "correct_index", 5), "correct_index fora de range"),
])
def test_is_valid_false_em_combinacoes_invalidas(app, setup, bad):
    with app.app_context():
        q = QuizQuestion(institution_id=1, question="?", correct_index=0)
        q.options = ["A", "B"]
        setup(q)
        assert q.is_valid() is False, f"deveria invalidar: {bad}"


def test_to_public_dict_nao_vaza_resposta_correta(app):
    """Critico: payload publico nunca pode conter `correct_index`."""
    with app.app_context():
        q = QuizQuestion(institution_id=1, question="?", correct_index=2,
                         curiosity="Segredo de bastidor")
        q.options = ["A", "B", "C", "D"]
        data = q.to_public_dict()
        assert "correct_index" not in data
        assert "curiosity" not in data
        assert data["question"] == "?"


# ════════════════════════════════════════════════════════════════════════════
# Rota publica /<slug>/quiz
# ════════════════════════════════════════════════════════════════════════════

def test_quiz_page_404_quando_modulo_desabilitado(client):
    """Por default a fixture habilita so 'ia'. /quiz deve dar 404."""
    r = client.get("/teste/quiz", follow_redirects=False)
    assert r.status_code == 404


def test_quiz_page_renderiza_intro_quando_modulo_habilitado(client, quiz_setup):
    import re
    r = client.get("/teste/quiz")
    assert r.status_code == 200
    # Tela de entrada presente.
    assert "Quer testar seu conhecimento?".encode("utf-8") in r.data
    # JSON embebido na pagina (criterio Trello 3.8 — sem fetch extra).
    assert b"quizQuestionsData" in r.data
    # Resposta correta NUNCA aparece NO PAYLOAD PUBLICO.
    # Extraimos o conteudo do <script id="quizQuestionsData"> e validamos
    # que ele e' um JSON sem `correct_index`/`curiosity`. (A string
    # `correct_index` aparece no JS handler do feedback — ali e' OK; o
    # gabarito so chega via resposta do servidor apos o submit.)
    m = re.search(
        rb'<script id="quizQuestionsData"[^>]*>(.*?)</script>',
        r.data, re.DOTALL,
    )
    assert m is not None, "embed JSON nao encontrado"
    payload_text = m.group(1).decode("utf-8")
    payload = json.loads(payload_text)
    assert isinstance(payload, list) and payload
    for q in payload:
        assert "correct_index" not in q
        assert "curiosity" not in q


def test_quiz_page_404_para_slug_inexistente(client):
    r = client.get("/inexistente/quiz")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# POST /<slug>/api/quiz/answer
# ════════════════════════════════════════════════════════════════════════════

def test_answer_resposta_correta_devolve_curiosidade(app, client, quiz_setup):
    with app.app_context():
        q = QuizQuestion.query.filter_by(institution_id=quiz_setup["institution_id"]).first()
        qid, correct = q.id, q.correct_index

    r = client.post("/teste/api/quiz/answer", json={
        "question_id": qid, "choice_index": correct,
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["correct"] is True
    assert body["correct_index"] == correct
    assert body["curiosity"]


def test_answer_resposta_errada_marca_correto(app, client, quiz_setup):
    with app.app_context():
        q = QuizQuestion.query.filter_by(institution_id=quiz_setup["institution_id"]).first()
        qid, correct = q.id, q.correct_index

    wrong = (correct + 1) % 3
    r = client.post("/teste/api/quiz/answer", json={
        "question_id": qid, "choice_index": wrong,
    })
    body = r.get_json()
    assert body["correct"] is False
    assert body["correct_index"] == correct


def test_answer_payload_invalido_400(client, quiz_setup):
    r = client.post("/teste/api/quiz/answer", json={"foo": "bar"})
    assert r.status_code == 400


def test_answer_id_inexistente_404(client, quiz_setup):
    r = client.post("/teste/api/quiz/answer", json={
        "question_id": 99999, "choice_index": 0,
    })
    assert r.status_code == 404


def test_answer_logga_em_interaction_log(app, client, quiz_setup):
    """Cada resposta gera InteractionLog com input_type='quiz:correct/incorrect'.

    Permite que a pagina de metricas conte sessoes de quiz como canal proprio.
    """
    with app.app_context():
        q = QuizQuestion.query.filter_by(institution_id=quiz_setup["institution_id"]).first()
        qid, correct = q.id, q.correct_index

    client.post("/teste/api/quiz/answer", json={
        "question_id": qid, "choice_index": correct,
    })
    with app.app_context():
        log = (InteractionLog.query
               .filter_by(institution_id=quiz_setup["institution_id"])
               .order_by(InteractionLog.id.desc())
               .first())
        assert log is not None
        assert log.input_type == "quiz:correct"


def test_answer_isola_cross_tenant(app, client, quiz_setup):
    """Pergunta de outra instituicao nao pode ser respondida via slug 'teste'."""
    with app.app_context():
        outra = Institution(slug="outra-quiz", name="Outra", type="zoo",
                            ai_name="x", ai_context="y",
                            daily_ai_quota=500, active=True)
        db.session.add(outra)
        db.session.flush()
        outra_q = QuizQuestion(
            institution_id=outra.id, question="alheia", correct_index=0,
            active=True,
        )
        outra_q.options = ["A", "B"]
        db.session.add(outra_q)
        db.session.commit()
        outra_qid = outra_q.id

    # 'teste' tenta responder pergunta da 'outra' → 404.
    r = client.post("/teste/api/quiz/answer", json={
        "question_id": outra_qid, "choice_index": 0,
    })
    assert r.status_code == 404


def test_quiz_page_filtra_perguntas_invalidas(app, client, quiz_setup):
    """Perguntas mal formadas em banco antigo nao podem aparecer no totem."""
    with app.app_context():
        # Pergunta com correct_index fora do range — invalida.
        bad = QuizQuestion(
            institution_id=quiz_setup["institution_id"],
            question="quebrada", correct_index=99, active=True,
        )
        bad.options = ["A", "B"]
        db.session.add(bad)
        db.session.commit()
        bad_id = bad.id

    r = client.get("/teste/quiz")
    assert r.status_code == 200
    # JSON embebido NAO deve conter a pergunta quebrada.
    assert f'"id": {bad_id}'.encode() not in r.data
