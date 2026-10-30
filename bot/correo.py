"""Envío de emails por SMTP de Gmail (contraseña de aplicación)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)


class ErrorCorreo(Exception):
    pass


def enviar(asunto: str, cuerpo: str) -> None:
    usuario = os.environ.get("SMTP_USER")
    clave = os.environ.get("SMTP_PASS")
    destino = os.environ.get("EMAIL_TO")
    if not (usuario and clave and destino):
        raise ErrorCorreo("Faltan SMTP_USER, SMTP_PASS o EMAIL_TO (.env o GitHub Secrets)")

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = usuario
    msg["To"] = destino
    msg.set_content(cuerpo)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(usuario, clave.replace(" ", ""))
        smtp.send_message(msg)
    log.info("Email enviado: %s", asunto)
