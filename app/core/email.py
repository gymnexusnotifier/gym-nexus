import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email(to_email: str, subject: str, body: str, is_html: bool = False, cc_emails: list[str] | None = None, attachments: list[tuple[str, bytes, str]] | None = None) -> bool:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        print(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD before sending email."
        )
        return False

    sender = settings.from_email or settings.smtp_user
    if not sender:
        print("SMTP sender is not configured. Set FROM_EMAIL or SMTP_USER.")
        return False

    recipients = [to_email]
    cc_list = [email.strip() for email in (cc_emails or []) if email and email.strip()]
    if cc_list:
        recipients.extend(cc_list)

    try:
        msg = EmailMessage()
        msg.set_content(body, subtype="html" if is_html else "plain")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        for filename, content, mimetype in attachments or []:
            maintype, subtype = mimetype.split("/", 1)
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(sender, recipients, msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False


def build_payment_confirmation_email(gym_name: str, member_name: str, amount, payment_date, plan_name: str, next_due_date=None, payment_method: str = "cash", transaction_id: str | None = None) -> tuple[str, str]:
        subject = f"Payment received - {gym_name}"
        due_line = f"Next renewal: {next_due_date}" if next_due_date else "No renewal date was set for this payment."
        transaction_line = f"Transaction ID: {transaction_id}" if transaction_id else ""
        body = f"""
        <html><body style="margin:0;background:#07111f;color:#edf6ff;font-family:Arial,Helvetica,sans-serif;padding:32px 16px;">
            <div style="max-width:600px;margin:auto;background:#0f172a;border:1px solid #334155;border-radius:18px;overflow:hidden;">
                <div style="padding:24px 28px;background:linear-gradient(135deg,#0e7490,#164e63);">
                    <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#cffafe;">Payment confirmed</div>
                    <h1 style="margin:8px 0 0;font-size:28px;color:#fff;">{gym_name}</h1>
                </div>
                <div style="padding:28px;">
                    <p style="font-size:16px;">Hi {member_name}, your payment has been recorded successfully.</p>
                    <div style="padding:18px;border:1px solid #334155;border-radius:12px;background:#111827;">
                        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;">Amount paid</div>
                        <div style="font-size:30px;font-weight:700;color:#67e8f9;margin:4px 0 16px;">Rs. {amount}</div>
                        <div><strong>Plan:</strong> {plan_name}</div>
                        <div><strong>Date:</strong> {payment_date}</div>
                            <div><strong>Payment method:</strong> {payment_method.replace('_', ' ').title()}</div>
                            <div><strong>{transaction_line}</strong></div>
                            <div><strong>{due_line}</strong></div>
                    </div>
                    <p style="color:#9eb4c8;margin-bottom:0;">Thank you for being part of {gym_name}.</p>
                </div>
            </div>
        </body></html>
        """
        return subject, body


def build_staff_invitation_email(gym_name: str, email: str, password: str, role: str) -> tuple[str, str]:
        subject = f"You have been invited to {gym_name}"
        body = f"""
        <html><body style="margin:0;background:#07111f;color:#edf6ff;font-family:Arial,Helvetica,sans-serif;padding:32px 16px;">
            <div style="max-width:600px;margin:auto;background:#0f172a;border:1px solid #334155;border-radius:18px;overflow:hidden;">
                <div style="padding:24px 28px;background:linear-gradient(135deg,#0e7490,#164e63);">
                    <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#cffafe;">Team invitation</div>
                    <h1 style="margin:8px 0 0;font-size:28px;color:#fff;">{gym_name}</h1>
                </div>
                <div style="padding:28px;">
                    <p style="font-size:16px;">You have been invited as a <strong>{role}</strong>.</p>
                    <div style="padding:18px;border:1px solid #334155;border-radius:12px;background:#111827;">
                        <div><strong>Login email:</strong> {email}</div>
                        <div style="margin-top:8px;"><strong>Temporary password:</strong> {password}</div>
                    </div>
                    <p style="color:#9eb4c8;">Use these details on the Gym Console login page. Change your password after signing in.</p>
                </div>
            </div>
        </body></html>
        """
        return subject, body


def build_gym_owner_welcome_email(gym_name: str, email: str, password: str, login_url: str = "") -> tuple[str, str]:
        subject = f"Welcome to GYM-NEXUS - your {gym_name} owner account is ready"
        login_link = f'<a href="{login_url}" style="color:#67e8f9;">Open the GYM-NEXUS login page</a>' if login_url else "Open the GYM-NEXUS login page"
        body = f"""
        <html><body style="margin:0;background:#07111f;color:#edf6ff;font-family:Arial,Helvetica,sans-serif;padding:32px 16px;">
            <div style="max-width:600px;margin:auto;background:#0f172a;border:1px solid #334155;border-radius:18px;overflow:hidden;">
                <div style="padding:28px;background:linear-gradient(135deg,#0e7490,#164e63);">
                    <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#cffafe;">Welcome to GYM-NEXUS</div>
                    <h1 style="margin:8px 0 0;font-size:28px;color:#fff;">Your gym is ready</h1>
                </div>
                <div style="padding:28px;">
                    <p style="font-size:16px;">Welcome. Your GYM-NEXUS owner account for <strong>{gym_name}</strong> has been created.</p>
                    <p>Use the credentials below to sign in and start managing your gym.</p>
                    <div style="padding:18px;border:1px solid #334155;border-radius:12px;background:#111827;">
                        <div><strong>Login email:</strong> {email}</div>
                        <div style="margin-top:8px;"><strong>Temporary password:</strong> {password}</div>
                    </div>
                    <p style="margin:24px 0 0;">{login_link}</p>
                    <p style="color:#9eb4c8;margin-bottom:0;">For your security, change your password after signing in. We look forward to supporting your gym.</p>
                </div>
            </div>
        </body></html>
        """
        return subject, body
