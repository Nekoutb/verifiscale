"""Transactional email via MailerSend.

Reads MAILERSEND_API_KEY / MAIL_FROM_EMAIL / MAIL_FROM_NAME / APP_BASE_URL
from the environment (see app.config). Without an API key every send is a
graceful no-op returning False — the UI then falls back to copyable links,
so onboarding never blocks on email infrastructure.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

log = logging.getLogger("fiscaudit.mailer")
API_URL = "https://api.mailersend.com/v1/email"


def send_email(to_email: str, subject: str, html: str, text: str) -> bool:
    s = get_settings()
    if not s.mailersend_api_key:
        log.info("MailerSend non configuré — email « %s » non envoyé à %s", subject, to_email)
        return False
    try:
        r = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {s.mailersend_api_key}",
                     "Content-Type": "application/json"},
            json={
                "from": {"email": s.mail_from_email, "name": s.mail_from_name},
                "to": [{"email": to_email}],
                "subject": subject,
                "html": html,
                "text": text,
            },
            timeout=15,
        )
        if r.status_code in (200, 202):
            return True
        log.warning("MailerSend %s: %s", r.status_code, r.text[:300])
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("MailerSend erreur: %s", e)
        return False


def _shell(title: str, body_html: str) -> str:
    return f"""<div style="font-family:system-ui,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px">
  <div style="font-weight:800;font-size:18px;color:#111">VerifiScale</div>
  <div style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#777">Plateforme d'audit fiscal</div>
  <h2 style="font-size:16px;color:#111;margin-top:24px">{title}</h2>
  {body_html}
  <p style="font-size:11px;color:#999;margin-top:32px">Cet email a été envoyé par VerifiScale (CM-EA).
  Si vous n'êtes pas concerné, ignorez-le.</p>
</div>"""


def send_org_welcome(to_email: str, org_name: str, admin_email: str,
                     temp_password: str) -> bool:
    s = get_settings()
    url = f"{s.app_base_url}/login"
    html = _shell(
        f"Votre espace « {org_name} » est prêt",
        f"""<p style="font-size:14px;color:#333">Bonjour,</p>
<p style="font-size:14px;color:#333">Votre espace de travail VerifiScale a été créé.
Connectez-vous avec :</p>
<p style="font-size:14px;color:#111"><b>Adresse :</b> {admin_email}<br>
<b>Mot de passe provisoire :</b> {temp_password}</p>
<p><a href="{url}" style="display:inline-block;background:#111;color:#fff;padding:10px 22px;
border-radius:8px;text-decoration:none;font-size:14px;font-weight:600">Se connecter</a></p>
<p style="font-size:12px;color:#666">Changez ce mot de passe dès votre première connexion.
Un assistant de démarrage vous guidera : création du premier dossier, chargement des
données, invitation de votre équipe.</p>""",
    )
    text = (f"Votre espace VerifiScale « {org_name} » est prêt.\n"
            f"Connexion : {url}\nAdresse : {admin_email}\n"
            f"Mot de passe provisoire : {temp_password}\n"
            f"Changez-le dès la première connexion.")
    return send_email(to_email, f"Bienvenue sur VerifiScale — {org_name}", html, text)


def send_invitation(to_email: str, org_name: str, invite_path: str,
                    expires_iso: str) -> bool:
    s = get_settings()
    url = f"{s.app_base_url}{invite_path}"
    html = _shell(
        f"Rejoignez l'équipe « {org_name} »",
        f"""<p style="font-size:14px;color:#333">Vous êtes invité à rejoindre l'espace
<b>{org_name}</b> sur VerifiScale.</p>
<p><a href="{url}" style="display:inline-block;background:#111;color:#fff;padding:10px 22px;
border-radius:8px;text-decoration:none;font-size:14px;font-weight:600">Créer mon compte</a></p>
<p style="font-size:12px;color:#666">Ce lien expire le {expires_iso[:10]}. Vous choisirez
votre mot de passe à la première connexion.</p>""",
    )
    text = (f"Vous êtes invité à rejoindre « {org_name} » sur VerifiScale.\n"
            f"Créez votre compte : {url}\nLien valable jusqu'au {expires_iso[:10]}.")
    return send_email(to_email, f"Invitation — {org_name} sur VerifiScale", html, text)
