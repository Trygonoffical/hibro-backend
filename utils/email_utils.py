from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_welcome_email(user, password, sponsor=None):
    """
    Send welcome email to newly registered MLM member with their login credentials.
    
    Args:
        user: The User object for the new member
        password: The plain text password (only used for email, not stored)
        sponsor: The MLM member who sponsored this user (optional)
    """
    try:
        # Email subject
        subject = f'Welcome to {settings.SITE_NAME} - Your MLM Account Details'
        
        # Prepare context for email template
        context = {
            'site_name': settings.SITE_NAME,
            'user': user,
            'username': user.username,
            'password': password,
            'sponsor': sponsor,
            'login_url': f"{settings.SITE_URL}/login",
            'contact_email': settings.CONTACT_EMAIL,
            'site_url': settings.SITE_URL
        }
        
        # Render email templates
        html_message = render_to_string('emails/welcome_email.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Welcome email sent to {user.email} for user {user.username}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {str(e)}")
        return False