"""Built-in message templates per event (plain-text Jinja, sandboxed, StrictUndefined).

``stream`` decides compliance handling: ``reminders`` carry List-Unsubscribe (RFC 8058 one-click) and respect
the suppression list; ``transactional`` messages (a document the client asked for) are always sent unless the
address bounced or complained.
"""

from dataclasses import dataclass
from typing import Literal

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment

Stream = Literal["transactional", "reminders"]


@dataclass(frozen=True, slots=True)
class EventTemplate:
    event: str
    description: str
    stream: Stream
    subject: str
    body: str
    sample: dict[str, str]


CATALOG: dict[str, EventTemplate] = {
    t.event: t
    for t in [
        EventTemplate(
            event="document.shared",
            description="A document link sent to a client",
            stream="transactional",
            subject="{{ document_title }} from {{ tenant_name }}",
            body=(
                "Dear {{ recipient_name }},\n\n"
                "{% if message %}{{ message }}\n\n{% endif %}"
                "{{ sender_name }} at {{ tenant_name }} has shared {{ document_title }} with you.\n\n"
                "View it here: {{ link_url }}\n\n"
                "Kind regards,\n{{ sender_name }}\n{{ tenant_name }}"
            ),
            sample={
                "recipient_name": "Otieno",
                "tenant_name": "Wanjiku Insurance Agency",
                "sender_name": "Wanjiku",
                "document_title": "Quotation QT-2026-00042",
                "link_url": "https://app.example.com/d/abc",
                "message": "",
            },
        ),
        EventTemplate(
            event="document.expiring",
            description="Reminder that a client's document (ID, licence, logbook) is about to expire",
            stream="reminders",
            subject="Your {{ document_title }} expires on {{ expires_on }}",
            body=(
                "Dear {{ recipient_name }},\n\n"
                "Our records show that your {{ document_title }} expires on {{ expires_on }}. "
                "Please send us an updated copy so your cover stays in order.\n\n"
                "Kind regards,\n{{ tenant_name }}"
            ),
            sample={
                "recipient_name": "Otieno",
                "tenant_name": "Wanjiku Insurance Agency",
                "document_title": "driving licence",
                "expires_on": "30 Nov 2026",
            },
        ),
        EventTemplate(
            event="policy.renewal_due",
            description="Renewal reminder to a client before their policy expires",
            stream="reminders",
            subject="Your {{ policy_description }} cover expires on {{ expires_on }}",
            body=(
                "Dear {{ recipient_name }},\n\n"
                "{% if message %}{{ message }}\n\n{% endif %}"
                "Your {{ insurer_name }} cover for {{ policy_description }} expires on {{ expires_on }}. "
                "To stay covered without a gap, reply to this email or call us on {{ agent_phone }} "
                "and we will prepare your renewal.\n\n"
                "Kind regards,\n{{ agent_name }}\n{{ tenant_name }}"
            ),
            sample={
                "recipient_name": "Otieno",
                "tenant_name": "Wanjiku Insurance Agency",
                "agent_name": "Wanjiku",
                "agent_phone": "+254 711 000 000",
                "insurer_name": "Savanna General",
                "policy_description": "KDA 123A Toyota Axio",
                "expires_on": "30 Nov 2026",
                "message": "",
            },
        ),
        EventTemplate(
            event="notification.email",
            description="Email copy of an in-app notification (team members)",
            stream="transactional",
            subject="{{ title }}",
            body="{{ body }}\n\n{% if link_url %}Open: {{ link_url }}\n{% endif %}",
            sample={
                "title": "A client viewed your quotation",
                "body": "Otieno opened QT-2026-00042.",
                "link_url": "",
            },
        ),
        EventTemplate(
            event="test.email",
            description="Test message to check email delivery",
            stream="transactional",
            subject="Test email from {{ tenant_name }}",
            body="Hello {{ recipient_name }},\n\nEmail from {{ tenant_name }} is working.",
            sample={"recipient_name": "Wanjiku", "tenant_name": "Wanjiku Insurance Agency"},
        ),
    ]
}

_env = ImmutableSandboxedEnvironment(
    undefined=StrictUndefined, autoescape=False, keep_trailing_newline=False
)


class TemplateRenderError(ValueError):
    pass


def render(subject: str, body: str, context: dict[str, str]) -> tuple[str, str]:
    try:
        rendered_subject = _env.from_string(subject).render(context)
        rendered_body = _env.from_string(body).render(context)
    except TemplateError as exc:
        raise TemplateRenderError(str(exc)) from None
    # Header injection guard: subjects are single-line.
    return " ".join(rendered_subject.split())[:200], rendered_body
