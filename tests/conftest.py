"""Fixtures compartilhadas entre os testes.

Cria um app Flask em modo "testing" com banco SQLite em memoria e popula
uma instituicao minima para cobrir as rotas que dependem de <slug>.
"""
import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Institution, InstitutionModule


@pytest.fixture(scope="function")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        # Instituicao de teste com o modulo de IA habilitado.
        inst = Institution(
            slug="teste",
            name="Totem Teste",
            type="zoo",
            ai_name="Guia Teste",
            ai_context="Voce e um assistente de teste.",
            daily_ai_quota=500,
            active=True,
        )
        _db.session.add(inst)
        _db.session.flush()
        _db.session.add(InstitutionModule(
            institution_id=inst.id, module_slug="ia", enabled=True, order=1,
        ))
        _db.session.commit()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def inst(app):
    return Institution.query.filter_by(slug="teste").first()
