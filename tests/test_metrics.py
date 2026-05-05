"""Testes das agregacoes de uso por instituicao.

Foco no modulo `app.services.metrics` — logica pura sobre InteractionLog,
testavel sem mexer no fluxo de auth do admin. As rotas em si sao garantidas
por integracao via test_smoke (auth gating) e podem ser estendidas no futuro.
"""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import Institution, InteractionLog
from app.services.metrics import (
    DEFAULT_DAYS,
    TOP_QUESTIONS_MIN_LEN,
    collect_metrics,
    collect_metrics_dict,
    collect_platform_summary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def populated(app):
    """Popula a instituicao 'teste' com logs sinteticos cobrindo varios dias,
    canais e idiomas. Retorna o id da instituicao."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        now = datetime.utcnow()

        def add(text, ttype, days_ago):
            db.session.add(InteractionLog(
                institution_id=inst.id,
                input_text=text,
                input_type=ttype,
                response_text="(resposta)",
                created_at=now - timedelta(days=days_ago),
            ))

        # Hoje: voz, texto, traducao en
        add("Onde fica o banheiro?", "voice", days_ago=0)
        add("Onde fica o banheiro?", "voice", days_ago=0)  # repeticao p/ top
        add("qual o horario?", "text", days_ago=0)
        add("Hello", "translate:en", days_ago=0)
        # 5 dias atras: mais traducoes en + uma es
        add("Where is the entrance", "translate:en", days_ago=5)
        add("Donde esta la salida", "translate:es", days_ago=5)
        # 10 dias atras
        add("oi", "text", days_ago=10)  # ruido — abaixo do MIN_LEN
        # 40 dias atras — fora da janela default de 30 dias
        add("antiguidade", "voice", days_ago=40)

        db.session.commit()
        return inst.id


# ── collect_metrics — caminhos basicos ────────────────────────────────────────

def test_collect_metrics_total_respeita_janela(app, populated):
    """30 dias default exclui o log de 40 dias atras."""
    with app.app_context():
        m = collect_metrics(populated, days=30)
        # Total dentro da janela: 7 (todos exceto o de 40 dias)
        assert m.total == 7
        assert m.period_days == 30


def test_collect_metrics_janela_customizada(app, populated):
    with app.app_context():
        m = collect_metrics(populated, days=3)
        # Apenas os 4 logs de hoje devem entrar.
        assert m.total == 4


def test_collect_metrics_janela_invalida_cai_no_default(app, populated):
    """days <= 0 nao deve crashar — usa o default."""
    with app.app_context():
        m = collect_metrics(populated, days=0)
        assert m.period_days == DEFAULT_DAYS


# ── Daily breakdown ────────────────────────────────────────────────────────────

def test_daily_inclui_dias_zerados(app, populated):
    """Todos os 30 dias devem aparecer na serie, mesmo sem interacoes."""
    with app.app_context():
        m = collect_metrics(populated, days=30)
        assert len(m.daily) == 30
        # Pelo menos um dia tem zero (a maioria dos dias em populated nao tem log).
        assert any(d.total == 0 for d in m.daily)
        # Ultimo elemento e' "hoje" (4 interacoes adicionadas).
        assert m.daily[-1].total == 4


def test_daily_ordenado_cronologicamente(app, populated):
    with app.app_context():
        m = collect_metrics(populated, days=10)
        dates = [d.date for d in m.daily]
        assert dates == sorted(dates), "daily deve estar do mais antigo ao mais recente"


# ── Channel breakdown ──────────────────────────────────────────────────────────

def test_channels_classifica_voz_texto_traducao(app, populated):
    with app.app_context():
        m = collect_metrics(populated, days=30)
        assert m.channels.voice == 2
        assert m.channels.text == 2
        assert m.channels.translate == 3   # 1 hoje + 1 en + 1 es
        assert m.channels.other == 0


def test_channels_other_pega_tipo_desconhecido(app, populated):
    """Robustez — input_type fora do enum nao pode crashar nem inflar canais."""
    with app.app_context():
        db.session.add(InteractionLog(
            institution_id=populated, input_text="?", input_type="ufo",
            response_text="?", created_at=datetime.utcnow(),
        ))
        db.session.commit()
        m = collect_metrics(populated, days=30)
        assert m.channels.other == 1


# ── Languages (translate:<code>) ──────────────────────────────────────────────

def test_languages_so_conta_traducoes(app, populated):
    with app.app_context():
        m = collect_metrics(populated, days=30)
        codes = {l.code: l.count for l in m.languages}
        # 2 pedidos em ingles + 1 em espanhol; voice/text NAO contam.
        assert codes == {"en": 2, "es": 1}


def test_languages_ordenado_por_frequencia(app, populated):
    with app.app_context():
        m = collect_metrics(populated, days=30)
        counts = [l.count for l in m.languages]
        assert counts == sorted(counts, reverse=True)


# ── Top questions ──────────────────────────────────────────────────────────────

def test_top_questions_normaliza_e_agrupa_repeticoes(app, populated):
    """Mesma pergunta com case/spacing diferente deve agrupar."""
    with app.app_context():
        db.session.add(InteractionLog(
            institution_id=populated,
            input_text="ONDE FICA O   banheiro?",
            input_type="voice",
            response_text="?",
            created_at=datetime.utcnow(),
        ))
        db.session.commit()
        m = collect_metrics(populated, days=30)
        # Antes da normalizacao havia 2 ocorrencias. Apos adicao 1 com
        # case/spacing diferente → contagem total 3 numa unica entrada.
        assert m.top_questions, "top_questions nao deveria estar vazio"
        top = m.top_questions[0]
        assert top.text == "onde fica o banheiro?"
        assert top.count == 3


def test_top_questions_filtra_entradas_curtas(app, populated):
    """'oi' (2 chars) deve ser ignorado mesmo que apareca varias vezes."""
    with app.app_context():
        m = collect_metrics(populated, days=30)
        for q in m.top_questions:
            assert len(q.text) >= TOP_QUESTIONS_MIN_LEN


# ── Serializacao ──────────────────────────────────────────────────────────────

def test_collect_metrics_dict_serializavel_em_json(app, populated):
    import json
    with app.app_context():
        d = collect_metrics_dict(populated, days=30)
        # Roundtrip JSON valida que nao tem datetime/Counter perdidos.
        assert json.loads(json.dumps(d))["total"] == d["total"]
        assert "daily" in d and "channels" in d and "languages" in d


# ── Platform summary ──────────────────────────────────────────────────────────

def test_platform_summary_agrupa_por_instituicao(app, populated):
    """Resumo do dashboard global: 1 linha por instituicao com totais."""
    with app.app_context():
        rows = collect_platform_summary(days=30)
        assert len(rows) == 1
        row = rows[0]
        assert row["institution_id"] == populated
        assert row["total"] == 7
        assert row["voice"] == 2
        assert row["translate"] == 3


def test_platform_summary_ordena_por_volume_desc(app):
    """Quem usa mais o totem aparece primeiro."""
    with app.app_context():
        # Cria uma segunda instituicao com mais logs.
        big = Institution(slug="big", name="Big Zoo", type="zoo",
                          ai_name="A", ai_context="b",
                          daily_ai_quota=500, active=True)
        db.session.add(big)
        db.session.flush()
        for _ in range(5):
            db.session.add(InteractionLog(
                institution_id=big.id, input_text="x", input_type="voice",
                response_text="y", created_at=datetime.utcnow(),
            ))
        # 'teste' fica com 1 unica interacao.
        teste = Institution.query.filter_by(slug="teste").first()
        db.session.add(InteractionLog(
            institution_id=teste.id, input_text="x", input_type="voice",
            response_text="y", created_at=datetime.utcnow(),
        ))
        db.session.commit()

        rows = collect_platform_summary(days=30)
        ids = [r["institution_id"] for r in rows]
        # big (5) vem antes de teste (1).
        assert ids.index(big.id) < ids.index(teste.id)


# ── Rota de metricas — auth gate ──────────────────────────────────────────────

def test_metrics_route_exige_auth(client):
    """Rota de metricas e' super_admin_required — sem login → redirect 302."""
    r = client.get("/admin/platform/metrics/1", follow_redirects=False)
    assert r.status_code in (302, 401, 403)


def test_metrics_json_route_exige_auth(client):
    r = client.get("/admin/platform/metrics/1.json", follow_redirects=False)
    assert r.status_code in (302, 401, 403)
