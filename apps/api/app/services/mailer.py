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
        payload = {
            "from": {"email": s.mail_from_email, "name": s.mail_from_name},
            "to": [{"email": to_email}],
            "subject": subject,
            "html": html,
            "text": text,
            # Aucune image ni réécriture de lien : MailerSend injecte sinon un
            # pixel de suivi (open tracking) et fait passer les liens par son
            # domaine de tracking — deux signaux classiques de spam.
            "settings": {"track_opens": False, "track_clicks": False,
                         "track_content": False},
        }
        if s.mail_reply_to:
            payload["reply_to"] = {"email": s.mail_reply_to, "name": s.mail_from_name}
        r = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {s.mailersend_api_key}",
                     "Content-Type": "application/json"},
            json=payload,
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
        f"Bienvenue — votre espace « {org_name} » est prêt",
        f"""<p style="font-size:14px;color:#333">Bonjour,</p>
<p style="font-size:14px;color:#333;line-height:1.6">Je suis <b>Fri</b>, de l'équipe
VerifiScale. Votre espace de travail sécurisé vient d'être provisionné : vous y menez
vos vérifications fiscales (balance, grand-livre, contrôles CGI, rapprochements) dans
un environnement entièrement isolé, réservé à votre cabinet.</p>

<div style="background:#f6f6f6;border:1px solid #e5e5e5;border-radius:10px;padding:16px 18px;margin:18px 0">
  <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#888;margin-bottom:6px">Vos identifiants de connexion</div>
  <div style="font-size:14px;color:#111;line-height:1.8">
    <b>Espace :</b> {org_name}<br>
    <b>Adresse :</b> {admin_email}<br>
    <b>Mot de passe provisoire :</b> <code style="background:#fff;border:1px solid #ddd;border-radius:4px;padding:1px 6px">{temp_password}</code>
  </div>
</div>

<p style="text-align:center;margin:24px 0">
  <a href="{url}" style="display:inline-block;background:#111;color:#fff;padding:12px 32px;
  border-radius:8px;text-decoration:none;font-size:15px;font-weight:700">Accéder à mon espace</a>
</p>

<p style="font-size:13px;color:#b45309;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px">
  <b>Important :</b> ce mot de passe est provisoire — changez-le dès votre première
  connexion (menu Utilisateurs &rarr; votre profil).</p>

<p style="font-size:13px;color:#333;line-height:1.7"><b>Vos premières étapes</b> (un
assistant vous guide à l'écran) :<br>
&nbsp;&nbsp;1. Créez votre premier dossier de vérification (contribuable, exercices)<br>
&nbsp;&nbsp;2. Chargez la balance et le grand-livre — le mapping se confirme en un clic<br>
&nbsp;&nbsp;3. Invitez votre équipe — chaque membre reçoit son lien personnel</p>

<p style="font-size:13px;color:#333">Une question, un blocage ? Répondez simplement à
cet email — il arrive directement chez nous.</p>
<p style="font-size:13px;color:#333">Bonne vérification,<br><b>Fri</b> — VerifiScale (CM-EA)</p>""",
    )
    text = (f"Bonjour,\n\nJe suis Fri, de l'équipe VerifiScale. Votre espace « {org_name} » est prêt.\n\n"
            f"Connexion : {url}\nEspace : {org_name}\nAdresse : {admin_email}\n"
            f"Mot de passe provisoire : {temp_password}\n\n"
            f"IMPORTANT : changez ce mot de passe dès votre première connexion.\n\n"
            f"Premières étapes : 1) créez votre premier dossier 2) chargez balance et grand-livre "
            f"3) invitez votre équipe.\n\nUne question ? Répondez à cet email.\n\nFri — VerifiScale (CM-EA)")
    return send_email(to_email, f"Bienvenue sur VerifiScale — votre espace {org_name} est prêt",
                      html, text)


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
