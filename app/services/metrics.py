"""Agregacoes de uso por instituicao.

Atende o backlog Trello:
  - Sprint 4 (Alta) — refinar dashboard admin com metricas por instituicao.
  - Epico Operador, US2 (Baixa) — registrar metricas (qtd interacoes,
    perguntas mais feitas, idiomas usados).

Por que um modulo separado em vez de queries soltas no route?
  - Reusa as mesmas agregacoes no JSON endpoint, na pagina HTML e em
    eventuais exports CSV no futuro.
  - Concentra o conhecimento sobre como `input_type` codifica o canal
    (voice/text/translate:<lang>) — mudou aqui, mudou em todo lado.
  - Facilita testar regressoes nas regras (ex.: "translate:en conta como
    interacao em ingles") sem precisar de Flask context.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import ExperienceRating, InteractionLog


# ── Configuracoes ──────────────────────────────────────────────────────────────

DEFAULT_DAYS = 30
TOP_QUESTIONS_LIMIT = 10
TOP_QUESTIONS_MIN_LEN = 4   # ignora "ok", "oi", "sim"... ruido nao e' insight


@dataclass
class DailyCount:
    date: str          # ISO YYYY-MM-DD
    total: int


@dataclass
class ChannelBreakdown:
    voice: int
    text: int
    translate: int     # soma de todos os translate:<lang>
    other: int


@dataclass
class LanguageUsage:
    """Idiomas pedidos via /api/translate. Aproximacao: nao temos detector
    de idioma de entrada da IA de voz, so o destino da traducao."""
    code: str          # "en", "pt", "es"...
    count: int


@dataclass
class TopQuestion:
    text: str
    count: int


@dataclass
class RatingsSummary:
    """Resumo de avaliacoes da experiencia no periodo."""
    count: int
    average: float | None             # None quando count == 0
    distribution: dict[int, int]      # {1: 0, 2: 1, 3: 5, 4: 9, 5: 12}
    recent_comments: list[str]        # ate 5 comentarios mais recentes (truncados)


@dataclass
class InstitutionMetrics:
    institution_id: int
    period_days: int
    total: int
    daily: list[DailyCount]
    channels: ChannelBreakdown
    languages: list[LanguageUsage]
    top_questions: list[TopQuestion]
    ratings: RatingsSummary


# ── API publica ────────────────────────────────────────────────────────────────

def collect_metrics(institution_id: int, days: int = DEFAULT_DAYS) -> InstitutionMetrics:
    """Snapshot de uso de uma instituicao nos ultimos `days` dias.

    Optei por agregar em Python depois de uma query enxuta em vez de
    multiplos GROUP BYs no banco. Volume esperado por instituicao no
    horizonte da Sprint 4 (centenas/milhares de logs por mes) cabe
    confortavelmente em memoria, e a logica fica testavel sem fixtures
    pesadas. Quando passarmos de ~500k linhas/mes, dai sim refatoramos
    em SQL agregado com indice em (institution_id, created_at).
    """
    if days <= 0:
        days = DEFAULT_DAYS

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        InteractionLog.query
        .filter(InteractionLog.institution_id == institution_id)
        .filter(InteractionLog.created_at >= cutoff)
        .with_entities(
            InteractionLog.input_text,
            InteractionLog.input_type,
            InteractionLog.created_at,
        )
        .all()
    )

    return InstitutionMetrics(
        institution_id=institution_id,
        period_days=days,
        total=len(rows),
        daily=_aggregate_daily(rows, days),
        channels=_aggregate_channels(rows),
        languages=_aggregate_languages(rows),
        top_questions=_aggregate_top_questions(rows),
        ratings=_aggregate_ratings(institution_id, cutoff),
    )


def collect_metrics_dict(institution_id: int, days: int = DEFAULT_DAYS) -> dict:
    """Versao serializavel — alimenta o endpoint JSON e templates Jinja."""
    m = collect_metrics(institution_id, days)
    return {
        "institution_id": m.institution_id,
        "period_days": m.period_days,
        "total": m.total,
        "daily": [{"date": d.date, "total": d.total} for d in m.daily],
        "channels": {
            "voice": m.channels.voice,
            "text": m.channels.text,
            "translate": m.channels.translate,
            "other": m.channels.other,
        },
        "languages": [{"code": l.code, "count": l.count} for l in m.languages],
        "top_questions": [{"text": q.text, "count": q.count} for q in m.top_questions],
        "ratings": {
            "count": m.ratings.count,
            "average": m.ratings.average,
            "distribution": m.ratings.distribution,
            "recent_comments": m.ratings.recent_comments,
        },
    }


# ── Helpers privados ───────────────────────────────────────────────────────────

def _aggregate_daily(rows, days: int) -> list[DailyCount]:
    """Devolve TODOS os dias da janela, mesmo os sem interacao (zero).

    Sem isso, o grafico fica com gaps e o leitor nao percebe dias mortos —
    que sao o sinal mais importante (totem desligado, instituicao fechada).
    """
    counts: Counter[str] = Counter()
    for _text, _type, created in rows:
        counts[created.date().isoformat()] += 1

    today = datetime.utcnow().date()
    return [
        DailyCount(
            date=(today - timedelta(days=i)).isoformat(),
            total=counts.get((today - timedelta(days=i)).isoformat(), 0),
        )
        for i in reversed(range(days))
    ]


def _aggregate_channels(rows) -> ChannelBreakdown:
    voice = text = trans = other = 0
    for _t, ttype, _c in rows:
        ttype = (ttype or "").lower()
        if ttype == "voice":
            voice += 1
        elif ttype == "text":
            text += 1
        elif ttype.startswith("translate:"):
            trans += 1
        else:
            other += 1
    return ChannelBreakdown(voice=voice, text=text, translate=trans, other=other)


def _aggregate_languages(rows) -> list[LanguageUsage]:
    """Conta por codigo de idioma extraido de `input_type='translate:<code>'`.

    Pulamos voice/text porque nao temos sinal de idioma confiavel para
    elas — adicionar deteccao de idioma na IA de voz seria outro PR.
    """
    counter: Counter[str] = Counter()
    for _t, ttype, _c in rows:
        ttype = (ttype or "").lower()
        if ttype.startswith("translate:"):
            code = ttype.split(":", 1)[1].strip() or "?"
            counter[code] += 1
    return [
        LanguageUsage(code=code, count=count)
        for code, count in counter.most_common()
    ]


def _aggregate_ratings(institution_id: int, cutoff: datetime) -> RatingsSummary:
    """Estatisticas das avaliacoes anonimas (estrelas + comentarios).

    Calcula tudo em uma unica query reduzida — o conjunto de ratings
    raramente cresce mais que centenas por mes por instituicao, entao
    materializar as linhas e' aceitavel e simplifica os agregados.
    """
    rows = (
        ExperienceRating.query
        .filter(ExperienceRating.institution_id == institution_id)
        .filter(ExperienceRating.created_at >= cutoff)
        .order_by(ExperienceRating.created_at.desc())
        .all()
    )
    if not rows:
        return RatingsSummary(count=0, average=None,
                              distribution={i: 0 for i in range(1, 6)},
                              recent_comments=[])

    total = sum(r.stars for r in rows)
    avg = round(total / len(rows), 2)
    dist = {i: 0 for i in range(1, 6)}
    for r in rows:
        if 1 <= r.stars <= 5:
            dist[r.stars] += 1

    # Truncamos a 200 chars cada comentario para nao explodir o response do
    # endpoint JSON. Comentarios completos ficam disponiveis via futura UI
    # admin (ainda nao construida — Trello "baixa" so pediu o resumo).
    comments = [(r.comment or "")[:200] for r in rows[:5] if r.comment]

    return RatingsSummary(
        count=len(rows), average=avg, distribution=dist,
        recent_comments=comments,
    )


def _aggregate_top_questions(rows) -> list[TopQuestion]:
    """Top N perguntas, normalizadas e filtradas para reduzir ruido.

    Normalizacao:
      - lowercase + strip
      - colapsa whitespace interno
      - descarta < TOP_QUESTIONS_MIN_LEN chars
      - descarta entradas vazias e null
    """
    counter: Counter[str] = Counter()
    for text, _ttype, _c in rows:
        if not text:
            continue
        normalized = " ".join(text.lower().split())
        if len(normalized) < TOP_QUESTIONS_MIN_LEN:
            continue
        counter[normalized] += 1
    return [
        TopQuestion(text=text, count=count)
        for text, count in counter.most_common(TOP_QUESTIONS_LIMIT)
    ]


# ── Visao agregada do super_admin ──────────────────────────────────────────────

def collect_platform_summary(days: int = DEFAULT_DAYS) -> list[dict]:
    """Uma linha por instituicao com totais — usado no dashboard global.

    Query agregada (GROUP BY) em vez de N+1: barato mesmo com muitas
    instituicoes. Ordena por volume desc para o admin ver primeiro quem
    esta usando mais o totem.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.session.query(
            InteractionLog.institution_id,
            InteractionLog.input_type,
            func.count(InteractionLog.id),
        )
        .filter(InteractionLog.created_at >= cutoff)
        .group_by(InteractionLog.institution_id, InteractionLog.input_type)
        .all()
    )

    by_inst: dict[int, dict] = {}
    for inst_id, input_type, count in rows:
        bucket = by_inst.setdefault(inst_id, {
            "institution_id": inst_id,
            "total": 0, "voice": 0, "text": 0, "translate": 0, "other": 0,
        })
        bucket["total"] += count
        ttype = (input_type or "").lower()
        if ttype == "voice":
            bucket["voice"] += count
        elif ttype == "text":
            bucket["text"] += count
        elif ttype.startswith("translate:"):
            bucket["translate"] += count
        else:
            bucket["other"] += count

    return sorted(by_inst.values(), key=lambda r: r["total"], reverse=True)
