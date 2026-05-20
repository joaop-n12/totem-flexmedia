"""Voice & AI routes: text chat + voice (Whisper + GPT + TTS)."""
import logging
import os
import base64
import tempfile
import threading

from flask import Blueprint, current_app, render_template, request, jsonify, send_from_directory
from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError

from app.extensions import db, limiter
from app.helpers import load_institution, build_ai_context
from app.models import InteractionLog
from app.services.i18n import get_locale, locale_display_name, t

logger = logging.getLogger(__name__)

voice_bp = Blueprint("voice", __name__)

VOZES_PERMITIDAS = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
MAX_CHAT_LEN = 500   # chars accepted from user text
MAX_LOG_LEN  = 1000  # chars stored in DB (response may be longer)

# Mapeia o locale da sessao para o codigo ISO-639-1 esperado pela API Whisper.
# Sem isso, transcrevia tudo como PT mesmo quando o visitante falava EN/ES —
# o resultado virava texto sem nexo e a IA respondia em PT por inercia. Com o
# parametro correto, Whisper detecta a fonologia certa e devolve o texto na
# lingua falada, que entao alimenta a chamada do chat ja travada no locale.
WHISPER_LANG = {"pt": "pt", "en": "en", "es": "es"}


def _aplicar_trava_de_idioma(system_prompt: str, locale: str) -> str:
    """Anexa instrucao FORTE de idioma ao final do system prompt.

    Por que no fim e nao no inicio?
      O `build_ai_context` produz texto majoritariamente em PT (nome do
      assistente, descricoes de eventos, FAQs cadastradas pelo cliente). O
      modelo tende a espelhar a lingua do contexto. Colocar a trava como
      ULTIMA instrucao do system prompt aproveita o vies de recencia: ela
      e' a regra que mais "queima" na atencao na hora de gerar o token 1.

    Por que reforcar mesmo para PT?
      Garantia simetrica de comportamento — facil de depurar (logs sempre
      mostram a trava). Custa ~30 tokens, irrelevante diante de gpt-4o-mini.
    """
    nome = locale_display_name(locale)
    return (
        f"{system_prompt}\n\n"
        f"=== LANGUAGE LOCK (highest priority) ===\n"
        f"You MUST respond exclusively in {nome} (locale code: {locale}).\n"
        f"Ignore the language of the surrounding context — it may be in "
        f"Portuguese for historical reasons. Translate facts, hours, names "
        f"of events/places into {nome} naturally. Keep proper nouns (animal "
        f"species, brand names, venue names) only when they have no widely "
        f"accepted local equivalent. Tone: friendly, concise.\n"
        f"=== END LANGUAGE LOCK ==="
    )

# Saudacao proativa disparada pelo sensor de proximidade. Texto curto e
# convidativo — proposito unico e' engajar quem se aproximou do totem sem
# exigir toque ou fala primeiro.
GREETING_TEXTS = {
    "pt": "Seja bem-vindo! Gostaria de tirar alguma dúvida sobre a nossa visita?",
    "en": "Welcome! Would you like to ask a question about your visit?",
    "es": "¡Bienvenido! ¿Le gustaría hacer alguna pregunta sobre su visita?",
    "fr": "Bienvenue ! Souhaitez-vous poser une question sur votre visite ?",
}

# Cache em memoria do TTS de saudacao por (slug, locale, voice). Evita gastar
# chamadas OpenAI a cada presenca detectada — a frase e' fixa por locale.
# Nao precisa de TTL: a frase nao muda; reinicio do worker zera tudo.
_GREETING_CACHE: dict[tuple[str, str, str], bytes] = {}
_GREETING_LOCK = threading.Lock()

# Mensagens amigaveis exibidas no totem quando a IA esta indisponivel.
# Sao diferenciadas por motivo para que o admin consiga diagnosticar via logs,
# mas o visitante sempre ve um texto simples e util — agora traduzido para o
# locale travado na sessao (chaves voice.server.* no catalogo i18n).
def _msg_offline():    return t("voice.server.offline")
def _msg_rate_limit(): return t("voice.server.rate_limit")
def _msg_auth():       return t("voice.server.auth_error")
def _msg_generic():    return t("voice.server.generic")
def _msg_quota():      return t("voice.server.quota")


def _get_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


# ── Totem-facing AI page ───────────────────────────────────────────────────────

@voice_bp.route("/<slug>/ia")
def ia_page(slug):
    inst = load_institution(slug)
    if not inst.has_module("ia"):
        from flask import abort
        abort(404)
    return render_template("voice/index.html", institution=inst)


# ── Voice endpoint (Whisper → GPT → TTS) ──────────────────────────────────────

@voice_bp.route("/<slug>/api/voice", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour")
def voice_api(slug):
    inst = load_institution(slug)
    # Gate de quota diaria — evita estouro de custo OpenAI por tenant.
    if inst.ai_quota_exceeded():
        logger.warning("voice_api quota diaria atingida slug=%s", slug)
        return jsonify({"error": "quota", "message": _msg_quota()}), 429
    tmp_path = None
    try:
        if "audio" not in request.files:
            return jsonify({"error": t("voice.server.no_audio")}), 400

        audio_file = request.files["audio"]
        voice = request.form.get("voice", "nova")
        if voice not in VOZES_PERMITIDAS:
            voice = "nova"

        client = _get_client()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_file.save(tmp)
            tmp_path = tmp.name

        # Whisper precisa do codigo ISO do idioma falado. Antes vinha
        # hardcoded como "pt" — agora reflete o locale travado na sessao.
        locale = get_locale()
        whisper_lang = WHISPER_LANG.get(locale, "pt")
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                model="whisper-1", file=f, language=whisper_lang
            )
        user_text = transcription.text.strip()[:MAX_CHAT_LEN]

        # Trava de idioma aplicada SEMPRE (inclusive PT) para garantir
        # comportamento simetrico e logs previsiveis.
        system_prompt = _aplicar_trava_de_idioma(build_ai_context(inst), locale)

        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            max_tokens=300,
        )
        answer = chat.choices[0].message.content.strip()

        tts = client.audio.speech.create(model="tts-1", voice=voice, input=answer)
        tts_b64 = base64.b64encode(tts.read()).decode("utf-8")

        db.session.add(InteractionLog(
            institution_id=inst.id,
            input_text=user_text[:MAX_LOG_LEN],
            input_type="voice",
            response_text=answer[:MAX_LOG_LEN],
        ))
        db.session.commit()

        return jsonify({"transcription": user_text, "response": answer, "tts_base64": tts_b64})

    except (APIConnectionError, APITimeoutError):
        logger.warning("voice_api offline/timeout for slug=%s", slug)
        return jsonify({"error": "offline", "message": _msg_offline()}), 503
    except RateLimitError:
        logger.warning("voice_api rate-limited for slug=%s", slug)
        return jsonify({"error": "rate_limit", "message": _msg_rate_limit()}), 429
    except AuthenticationError:
        logger.error("voice_api auth error for slug=%s (chave OpenAI invalida?)", slug)
        return jsonify({"error": "auth", "message": _msg_auth()}), 503
    except Exception:
        logger.exception("voice_api error for slug=%s", slug)
        return jsonify({"error": "generic", "message": _msg_generic()}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Saudacao proativa por sensor de proximidade ───────────────────────────────
#
# Disparada pelo front (templates/base.html) quando a maquina de estados entra
# em ACTIVE — ou seja, quando o HC-SR04 detecta que alguem se aproximou.
# Difere do /api/voice tradicional porque NAO espera entrada de
# voz nem toque; o objetivo e' engajamento proativo.
#
# Seguranca/custo:
#   - Texto fixo por locale (sem injecao de input do usuario na chamada IA).
#   - Cache em memoria por (slug, locale, voice): primeira aproximacao gera,
#     proximas reusam — quota diaria nao e' debitada para repeticoes.
#   - Fallback estatico: se existir static/audio/greeting_<locale>.mp3, serve
#     direto sem OpenAI (zero custo, zero dependencia de rede).
#   - Gate de modulo IA + quota: respeitam as mesmas regras do voice_api.

@voice_bp.route("/<slug>/api/voice/greeting", methods=["GET"])
@limiter.limit("30 per minute; 200 per hour")
def voice_greeting(slug):
    inst = load_institution(slug)
    if not inst.has_module("ia"):
        return jsonify({"error": "module_disabled"}), 404

    locale = get_locale()
    text = GREETING_TEXTS.get(locale, GREETING_TEXTS["pt"])
    voice = request.args.get("voice", "nova")
    if voice not in VOZES_PERMITIDAS:
        voice = "nova"

    # 1) Fallback estatico — operador pode pre-gravar o audio e evitar OpenAI.
    static_dir = os.path.join(current_app.root_path, "..", "static", "audio")
    static_dir = os.path.abspath(static_dir)
    static_name = f"greeting_{locale}.mp3"
    if os.path.isfile(os.path.join(static_dir, static_name)):
        return send_from_directory(static_dir, static_name, mimetype="audio/mpeg")

    # 2) Cache em memoria — frase fixa, gera uma vez por (slug, locale, voice).
    cache_key = (slug, locale, voice)
    with _GREETING_LOCK:
        cached = _GREETING_CACHE.get(cache_key)
    if cached is not None:
        return jsonify({"text": text, "tts_base64": base64.b64encode(cached).decode("utf-8")})

    # 3) Gate de quota (so para a primeira geracao por locale do dia).
    if inst.ai_quota_exceeded():
        logger.warning("voice_greeting quota diaria atingida slug=%s", slug)
        return jsonify({"error": "quota", "message": _msg_quota(), "text": text}), 429

    try:
        client = _get_client()
        tts = client.audio.speech.create(model="tts-1", voice=voice, input=text)
        audio_bytes = tts.read()
        with _GREETING_LOCK:
            _GREETING_CACHE[cache_key] = audio_bytes

        # Loga como interacao "greeting" — alimenta as metricas de canal.
        db.session.add(InteractionLog(
            institution_id=inst.id,
            input_text="(proximity-trigger)",
            input_type="greeting",
            response_text=text[:MAX_LOG_LEN],
        ))
        db.session.commit()

        return jsonify({"text": text, "tts_base64": base64.b64encode(audio_bytes).decode("utf-8")})

    except (APIConnectionError, APITimeoutError):
        logger.warning("voice_greeting offline/timeout for slug=%s", slug)
        return jsonify({"error": "offline", "message": _msg_offline(), "text": text}), 503
    except RateLimitError:
        logger.warning("voice_greeting rate-limited for slug=%s", slug)
        return jsonify({"error": "rate_limit", "message": _msg_rate_limit(), "text": text}), 429
    except AuthenticationError:
        logger.error("voice_greeting auth error for slug=%s (chave OpenAI invalida?)", slug)
        return jsonify({"error": "auth", "message": _msg_auth(), "text": text}), 503
    except Exception:
        logger.exception("voice_greeting error for slug=%s", slug)
        return jsonify({"error": "generic", "message": _msg_generic(), "text": text}), 500


# ── Text chat endpoint ─────────────────────────────────────────────────────────

@voice_bp.route("/<slug>/api/chat", methods=["POST"])
@limiter.limit("20 per minute; 60 per hour")
def chat_api(slug):
    inst = load_institution(slug)
    if inst.ai_quota_exceeded():
        logger.warning("chat_api quota diaria atingida slug=%s", slug)
        return jsonify({"error": "quota", "message": _msg_quota()}), 429
    data = request.get_json(silent=True) or {}
    user_text = (data.get("message") or "").strip()[:MAX_CHAT_LEN]

    if not user_text:
        return jsonify({"error": t("voice.server.empty_msg")}), 400

    # Mesma voz padrao do canal por voz — o front passa a voz selecionada
    # nas pills; se vier algo invalido caimos no fallback seguro.
    voice = (data.get("voice") or "nova").strip().lower()
    if voice not in VOZES_PERMITIDAS:
        voice = "nova"

    try:
        client = _get_client()
        # Trava de idioma aplicada SEMPRE (inclusive PT) — mesma estrategia
        # do /api/voice, garante simetria entre canais.
        locale = get_locale()
        system_prompt = _aplicar_trava_de_idioma(build_ai_context(inst), locale)

        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            max_tokens=300,
        )
        answer = chat.choices[0].message.content.strip()

        # TTS global: o chat por texto agora tambem devolve audio para que a
        # experiencia seja simetrica ao canal por voz. Falha de TTS NAO derruba
        # a resposta — o texto e' o conteudo primario; o audio e' enriquecimento.
        # Se a sintese falhar (timeout, rate-limit, erro transitorio), o front
        # continua mostrando o balao de texto normalmente.
        tts_b64 = None
        try:
            tts = client.audio.speech.create(model="tts-1", voice=voice, input=answer)
            tts_b64 = base64.b64encode(tts.read()).decode("utf-8")
        except (APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError):
            logger.warning("chat_api TTS indisponivel slug=%s — devolvendo apenas texto", slug)
        except Exception:
            logger.exception("chat_api TTS falhou slug=%s — devolvendo apenas texto", slug)

        db.session.add(InteractionLog(
            institution_id=inst.id,
            input_text=user_text[:MAX_LOG_LEN],
            input_type="text",
            response_text=answer[:MAX_LOG_LEN],
        ))
        db.session.commit()

        payload = {"response": answer}
        if tts_b64:
            payload["tts_base64"] = tts_b64
        return jsonify(payload)

    except (APIConnectionError, APITimeoutError):
        logger.warning("chat_api offline/timeout for slug=%s", slug)
        return jsonify({"error": "offline", "message": _msg_offline()}), 503
    except RateLimitError:
        logger.warning("chat_api rate-limited for slug=%s", slug)
        return jsonify({"error": "rate_limit", "message": _msg_rate_limit()}), 429
    except AuthenticationError:
        logger.error("chat_api auth error for slug=%s (chave OpenAI invalida?)", slug)
        return jsonify({"error": "auth", "message": _msg_auth()}), 503
    except Exception:
        logger.exception("chat_api error for slug=%s", slug)
        return jsonify({"error": "generic", "message": _msg_generic()}), 500
