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
from app.services.i18n import get_locale, locale_display_name

logger = logging.getLogger(__name__)

voice_bp = Blueprint("voice", __name__)

VOZES_PERMITIDAS = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
MAX_CHAT_LEN = 500   # chars accepted from user text
MAX_LOG_LEN  = 1000  # chars stored in DB (response may be longer)

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
# mas o visitante sempre ve um texto simples e util.
MSG_OFFLINE      = "Estou sem conexão com o assistente no momento. Tente novamente em alguns instantes."
MSG_RATE_LIMIT   = "Muita gente conversando comigo agora. Aguarde alguns segundos e tente de novo."
MSG_AUTH_ERROR   = "O assistente está temporariamente indisponível. Um atendente foi avisado."
MSG_GENERIC      = "Não consegui processar sua mensagem agora. Tente novamente."
MSG_QUOTA_DIARIA = "O assistente atingiu o limite de uso previsto para hoje. Ele volta amanhã cedo."


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
        return jsonify({"error": "quota", "message": MSG_QUOTA_DIARIA}), 429
    tmp_path = None
    try:
        if "audio" not in request.files:
            return jsonify({"error": "Nenhum áudio enviado"}), 400

        audio_file = request.files["audio"]
        voice = request.form.get("voice", "nova")
        if voice not in VOZES_PERMITIDAS:
            voice = "nova"

        client = _get_client()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_file.save(tmp)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                model="whisper-1", file=f, language="pt"
            )
        user_text = transcription.text.strip()[:MAX_CHAT_LEN]

        # Anexa instrucao de idioma se nao for o default — assim a IA responde
        # em ingles quando o visitante selecionou EN no topbar (Trello: Modulo 3
        # Acessibilidade e Idiomas, criterio 3.7).
        system_prompt = build_ai_context(inst)
        locale = get_locale()
        if locale != "pt":
            system_prompt += (
                f"\n\nIMPORTANT: Respond in {locale_display_name(locale)}. "
                f"Translate proper nouns only when they have a widely accepted "
                f"equivalent. Keep tone friendly and concise."
            )

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
        return jsonify({"error": "offline", "message": MSG_OFFLINE}), 503
    except RateLimitError:
        logger.warning("voice_api rate-limited for slug=%s", slug)
        return jsonify({"error": "rate_limit", "message": MSG_RATE_LIMIT}), 429
    except AuthenticationError:
        logger.error("voice_api auth error for slug=%s (chave OpenAI invalida?)", slug)
        return jsonify({"error": "auth", "message": MSG_AUTH_ERROR}), 503
    except Exception:
        logger.exception("voice_api error for slug=%s", slug)
        return jsonify({"error": "generic", "message": MSG_GENERIC}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Saudacao proativa por sensor de proximidade ───────────────────────────────
#
# Disparada pelo front (templates/base.html) quando a maquina de estados sai de
# IDLE para INVITE ou ACTIVE — ou seja, quando o PIR/HC-SR04 detecta que alguem
# se aproximou. Difere do /api/voice tradicional porque NAO espera entrada de
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
        return jsonify({"error": "quota", "message": MSG_QUOTA_DIARIA, "text": text}), 429

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
        return jsonify({"error": "offline", "message": MSG_OFFLINE, "text": text}), 503
    except RateLimitError:
        logger.warning("voice_greeting rate-limited for slug=%s", slug)
        return jsonify({"error": "rate_limit", "message": MSG_RATE_LIMIT, "text": text}), 429
    except AuthenticationError:
        logger.error("voice_greeting auth error for slug=%s (chave OpenAI invalida?)", slug)
        return jsonify({"error": "auth", "message": MSG_AUTH_ERROR, "text": text}), 503
    except Exception:
        logger.exception("voice_greeting error for slug=%s", slug)
        return jsonify({"error": "generic", "message": MSG_GENERIC, "text": text}), 500


# ── Text chat endpoint ─────────────────────────────────────────────────────────

@voice_bp.route("/<slug>/api/chat", methods=["POST"])
@limiter.limit("20 per minute; 60 per hour")
def chat_api(slug):
    inst = load_institution(slug)
    if inst.ai_quota_exceeded():
        logger.warning("chat_api quota diaria atingida slug=%s", slug)
        return jsonify({"error": "quota", "message": MSG_QUOTA_DIARIA}), 429
    data = request.get_json(silent=True) or {}
    user_text = (data.get("message") or "").strip()[:MAX_CHAT_LEN]

    if not user_text:
        return jsonify({"error": "Mensagem vazia"}), 400

    try:
        client = _get_client()
        # Anexa instrucao de idioma se nao for o default — assim a IA responde
        # em ingles quando o visitante selecionou EN no topbar (Trello: Modulo 3
        # Acessibilidade e Idiomas, criterio 3.7).
        system_prompt = build_ai_context(inst)
        locale = get_locale()
        if locale != "pt":
            system_prompt += (
                f"\n\nIMPORTANT: Respond in {locale_display_name(locale)}. "
                f"Translate proper nouns only when they have a widely accepted "
                f"equivalent. Keep tone friendly and concise."
            )

        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            max_tokens=300,
        )
        answer = chat.choices[0].message.content.strip()

        db.session.add(InteractionLog(
            institution_id=inst.id,
            input_text=user_text[:MAX_LOG_LEN],
            input_type="text",
            response_text=answer[:MAX_LOG_LEN],
        ))
        db.session.commit()

        return jsonify({"response": answer})

    except (APIConnectionError, APITimeoutError):
        logger.warning("chat_api offline/timeout for slug=%s", slug)
        return jsonify({"error": "offline", "message": MSG_OFFLINE}), 503
    except RateLimitError:
        logger.warning("chat_api rate-limited for slug=%s", slug)
        return jsonify({"error": "rate_limit", "message": MSG_RATE_LIMIT}), 429
    except AuthenticationError:
        logger.error("chat_api auth error for slug=%s (chave OpenAI invalida?)", slug)
        return jsonify({"error": "auth", "message": MSG_AUTH_ERROR}), 503
    except Exception:
        logger.exception("chat_api error for slug=%s", slug)
        return jsonify({"error": "generic", "message": MSG_GENERIC}), 500
