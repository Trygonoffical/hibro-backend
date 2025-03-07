import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class MSG91EmailService:
    """
    Service class for sending emails using MSG91 API
    """
    
    def __init__(self, auth_key=None):
        """
        Initialize with the AUTH key for MSG91
        """
        self.auth_key = auth_key or settings.MSG91_EMAIL_AUTH_KEY
        self.base_url = "https://control.msg91.com/api/v5/email/send"
        self.headers = {
            'accept': 'application/json',
            'authkey': self.auth_key,
            'content-type': 'application/json'
        }
        
    def send_email(self, to_email, to_name, template_id, variables=None):
        """
        Send email using MSG91 API
        
        Args:
            to_email (str): Recipient email
            to_name (str): Recipient name
            template_id (str): MSG91 email template ID
            variables (dict): Variables to replace in the template
            
        Returns:
            dict: Response with success status and message
        """
        try:
            if not variables:
                variables = {}
                
            payload = {
                "recipients": [
                    {
                        "to": [
                            {
                                "name": to_name,
                                "email": to_email
                            }
                        ],
                        "variables": variables
                    }
                ],
                "from": {
                    "name": "Herbal Power Marketing Private Limited",
                    "email": "noreply@mail.herbalpowerindia.com"
                },
                "domain": "mail.herbalpowerindia.com",
                "template_id": template_id
            }
            
            logger.info(f"Sending email to {to_email} using template {template_id}")
            
            response = requests.post(
                self.base_url,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=10
            )
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Email sent successfully to {to_email}")
                return {
                    'success': True,
                    'message': 'Email sent successfully',
                    'data': response_data
                }
            else:
                logger.error(f"Failed to send email: {response.text}")
                return {
                    'success': False,
                    'message': f"Failed to send email: {response.text}"
                }
                
        except Exception as e:
            logger.error(f"Error sending email via MSG91: {str(e)}")
            return {
                'success': False,
                'message': f"Error sending email: {str(e)}"
            }
            
    def send_kyc_approved_email(self, member):
        """
        Send KYC approval notification email to MLM member
        
        Args:
            member (MLMMember): The MLM member whose KYC was approved
            
        Returns:
            dict: Response with success status and message
        """
        try:
            user = member.user
            if not user.email:
                logger.warning(f"Cannot send KYC approval email: No email for member {member.member_id}")
                return {
                    'success': False,
                    'message': 'Member has no email address'
                }
                
            variables = {
                "var1": user.first_name or user.username
            }
            
            return self.send_email(
                to_email=user.email,
                to_name=user.get_full_name() or user.username,
                template_id="kyc_approved_3",
                variables=variables
            )
            
        except Exception as e:
            logger.error(f"Error sending KYC approval email: {str(e)}")
            return {
                'success': False,
                'message': f"Error sending KYC approval email: {str(e)}"
            }