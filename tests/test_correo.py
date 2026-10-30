import pytest

from bot import correo


class SMTPFalso:
    ultimo = None

    def __init__(self, host, puerto, timeout):
        self.host, self.puerto = host, puerto

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, usuario, clave):
        self.credenciales = (usuario, clave)

    def send_message(self, msg):
        SMTPFalso.ultimo = (self, msg)


def test_envio(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "yo@gmail.com")
    monkeypatch.setenv("SMTP_PASS", "abcd efgh ijkl mnop")
    monkeypatch.setenv("EMAIL_TO", "destino@gmail.com")
    monkeypatch.setattr(correo.smtplib, "SMTP_SSL", SMTPFalso)
    correo.enviar("Asunto €", "Cuerpo")
    smtp, msg = SMTPFalso.ultimo
    assert (smtp.host, smtp.puerto) == ("smtp.gmail.com", 465)
    assert smtp.credenciales == ("yo@gmail.com", "abcdefghijklmnop")
    assert msg["To"] == "destino@gmail.com" and msg["Subject"] == "Asunto €"


def test_faltan_secretos(monkeypatch):
    for v in ("SMTP_USER", "SMTP_PASS", "EMAIL_TO"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(correo.ErrorCorreo):
        correo.enviar("a", "b")
