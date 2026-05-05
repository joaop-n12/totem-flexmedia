"""Testes da avaliacao de experiencia (rating).

Cobre:
  - Modelo: validacao de estrelas, anonimato (sem session_id/IP).
  - Rota publica: gate por modulo 'avaliacao' habilitado.
  - POST /api/rating: aceita 1-5, recusa fora do range, recusa nao-int,
    trunca comentario excessivo, isolamento por tenant.
  - Metricas: avg/count/distribution incorporados; resumo NAO mistura
    instituicoes e respeita janela temporal.
"""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import ExperienceRating, Institution, InstitutionModule
from app.models.rating import MAX_COMMENT_LEN
from app.services.metrics import collect_metrics


# ── Fixture: habilita modulo avaliacao ────────────────────────────────────────

@pytest.fixture
def rating_setup(app):
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        if not inst.has_module("avaliacao"):
            db.session.add(InstitutionModule(
                institution_id=inst.id, module_slug="avaliacao",
                enabled=True, order=99,
            ))
            db.session.commit()
        return {"institution_id": inst.id}


# ════════════════════════════════════════════════════════════════════════════
# Modelo
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("value,expected", [
    (1, True), (3, True), (5, True),
    (0, False), (6, False), (-1, False),
    (None, False), ("4", True), ("abc", False), (3.5, True),
])
def test_is_valid_stars(value, expected):
    """3.5 (float) e '4' (string) sao aceitos pelo int() — comportamento ok."""
    assert ExperienceRating.is_valid_stars(value) is expected


def test_modelo_nao_persiste_dados_pessoais(app, rating_setup):
    """Defesa LGPD — schema do modelo NAO inclui IP, session, user_agent."""
    inspector = ExperienceRating.__table__.columns.keys()
    pii_fields = {"ip_address", "session_id", "user_agent", "user_id", "email"}
    assert not (set(inspector) & pii_fields), \
        f"Schema do rating tem campo de PII: {set(inspector) & pii_fields}"


# ════════════════════════════════════════════════════════════════════════════
# Gate de modulo
# ════════════════════════════════════════════════════════════════════════════

def test_rating_page_404_quando_modulo_desabilitado(client):
    r = client.get("/teste/rating", follow_redirects=False)
    assert r.status_code == 404


def test_rating_page_renderiza_quando_modulo_ativo(client, rating_setup):
    r = client.get("/teste/rating")
    assert r.status_code == 200
    assert "Como foi sua experiência?".encode("utf-8") in r.data
    # Estrelas no DOM (5 botoes).
    assert r.data.count(b'class="rating-star"') == 5


def test_post_rating_404_quando_modulo_desabilitado(client):
    r = client.post("/teste/api/rating", json={"stars": 5})
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# POST /api/rating
# ════════════════════════════════════════════════════════════════════════════

def test_post_rating_caminho_feliz(app, client, rating_setup):
    r = client.post("/teste/api/rating", json={"stars": 5, "comment": "ótimo!"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    with app.app_context():
        rating = ExperienceRating.query.first()
        assert rating is not None
        assert rating.stars == 5
        assert rating.comment == "ótimo!"
        assert rating.institution_id == rating_setup["institution_id"]


def test_post_rating_sem_comentario(client, rating_setup):
    r = client.post("/teste/api/rating", json={"stars": 4})
    assert r.status_code == 200


@pytest.mark.parametrize("payload,expected_status", [
    ({"stars": 0}, 400),
    ({"stars": 6}, 400),
    ({"stars": "abc"}, 400),
    ({"stars": None}, 400),
    ({}, 400),
])
def test_post_rating_recusa_estrelas_invalidas(client, rating_setup, payload, expected_status):
    r = client.post("/teste/api/rating", json=payload)
    assert r.status_code == expected_status


def test_post_rating_trunca_comentario_excessivo(app, client, rating_setup):
    """Comentario > MAX_COMMENT_LEN e' truncado server-side, nao rejeitado."""
    longo = "X" * (MAX_COMMENT_LEN + 500)
    r = client.post("/teste/api/rating", json={"stars": 3, "comment": longo})
    assert r.status_code == 200

    with app.app_context():
        rating = ExperienceRating.query.first()
        assert len(rating.comment) == MAX_COMMENT_LEN


def test_post_rating_isolamento_por_tenant(app, client, rating_setup):
    """Outras instituicoes nao recebem ratings que vieram pelo slug 'teste'."""
    with app.app_context():
        outra = Institution(
            slug="outra-rating", name="Outra", type="zoo", ai_name="x",
            ai_context="y", daily_ai_quota=500, active=True,
        )
        db.session.add(outra)
        db.session.commit()
        outra_id = outra.id

    client.post("/teste/api/rating", json={"stars": 5, "comment": "for testing"})

    with app.app_context():
        for_outra = ExperienceRating.query.filter_by(institution_id=outra_id).count()
        assert for_outra == 0


def test_post_rating_slug_inexistente_404(client):
    r = client.post("/inexistente/api/rating", json={"stars": 5})
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# Metricas — resumo de ratings
# ════════════════════════════════════════════════════════════════════════════

def test_metrics_sem_ratings_devolve_zeros(app, rating_setup):
    with app.app_context():
        m = collect_metrics(rating_setup["institution_id"], days=30)
        assert m.ratings.count == 0
        assert m.ratings.average is None
        assert m.ratings.distribution == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        assert m.ratings.recent_comments == []


def test_metrics_com_ratings_calcula_media_e_distribuicao(app, rating_setup):
    iid = rating_setup["institution_id"]
    with app.app_context():
        for stars in [5, 5, 4, 3, 1]:
            db.session.add(ExperienceRating(institution_id=iid, stars=stars))
        db.session.add(ExperienceRating(institution_id=iid, stars=5,
                                        comment="comentário recente"))
        db.session.commit()

        m = collect_metrics(iid, days=30)
        assert m.ratings.count == 6
        assert m.ratings.average == round((5+5+4+3+1+5) / 6, 2)
        assert m.ratings.distribution[5] == 3
        assert m.ratings.distribution[4] == 1
        assert m.ratings.distribution[3] == 1
        assert m.ratings.distribution[1] == 1
        assert "comentário recente" in m.ratings.recent_comments


def test_metrics_ratings_respeita_janela_temporal(app, rating_setup):
    iid = rating_setup["institution_id"]
    now = datetime.utcnow()
    with app.app_context():
        # Dentro da janela de 30 dias
        db.session.add(ExperienceRating(
            institution_id=iid, stars=5, created_at=now - timedelta(days=10)
        ))
        # Fora da janela
        db.session.add(ExperienceRating(
            institution_id=iid, stars=1, created_at=now - timedelta(days=60)
        ))
        db.session.commit()

        m = collect_metrics(iid, days=30)
        assert m.ratings.count == 1
        assert m.ratings.average == 5.0


def test_metrics_ratings_isolado_por_tenant(app, rating_setup):
    """Resumo da inst A nao deve incluir ratings da inst B."""
    iid = rating_setup["institution_id"]
    with app.app_context():
        outra = Institution(
            slug="outra-met", name="O", type="zoo", ai_name="x",
            ai_context="y", daily_ai_quota=500, active=True,
        )
        db.session.add(outra)
        db.session.flush()
        db.session.add(ExperienceRating(institution_id=outra.id, stars=1))
        db.session.add(ExperienceRating(institution_id=iid, stars=5))
        db.session.commit()

        m = collect_metrics(iid, days=30)
        assert m.ratings.count == 1
        assert m.ratings.average == 5.0
