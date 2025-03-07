# utils/msg91_utils.py
import requests
import http.client
import logging
import json
from django.conf import settings

logger = logging.getLogger(__name__)

class MSG91Service:
    def __init__(self, auth_key):
        self.auth_key = auth_key
        self.base_url = "control.msg91.com"

    def send_otp(self, phone_number, otp):
        """
        Send OTP using MSG91 Flow API
        
        Args:
            phone_number (str): Phone number to send OTP to (10 digits)
            otp (str): The OTP code to be sent
            
        Returns:
            dict: Response with success status and message
        """
        try:
            # Ensure phone number is in correct format (add country code if needed)
            if phone_number.startswith('+'):
                mobile = phone_number.lstrip('+')
            elif phone_number.startswith('91'):
                mobile = phone_number
            else:
                mobile = '91' + phone_number  # Add India country code
                
            # Create connection
            conn = http.client.HTTPSConnection(self.base_url)
            
            # Prepare request payload according to MSG91 Flow API documentation
            payload = {
                "template_id": "67a6056bbee6b9298c1af3c4",  # Your template ID
                "short_url": "1",
                "short_url_expiry": "60Seconds",
                "realTimeResponse": "1",
                "recipients": [
                    {
                        "mobiles": mobile,
                        "number": otp,  # This will replace {{otp}} in your template
                        "VAR2": "VALUE 2"  # Additional variables if needed
                    }
                ]
            }
            
            # Set headers
            headers = {
                'authkey': self.auth_key,
                'accept': "application/json",
                'content-type': "application/json"
            }
            
            # Make the request
            conn.request("POST", "/api/v5/flow", json.dumps(payload), headers)
            
            # Get response
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            
            # Log response
            logger.info(f"OTP Send Response: {data}")
            
            # Parse response
            response_data = json.loads(data)
            
            if response.status == 200 and not response_data.get('type') == 'error':
                return {
                    'success': True,
                    'message': 'OTP sent successfully',
                    'response': response_data
                }
            else:
                error_msg = response_data.get('msg', 'Unknown error')
                logger.error(f"MSG91 API Error: {error_msg}")
                return {
                    'success': False,
                    'message': f'Failed to send OTP: {error_msg}',
                    'response': response_data
                }
                
        except Exception as e:
            logger.error(f"Error sending OTP: {str(e)}")
            return {
                'success': False,
                'message': f'Error sending OTP: {str(e)}'
            }
    
    def send_order_confirmation(self, phone_number, order_number ,date):
        """
        Send OTP using MSG91 Flow API
        
        Args:
            phone_number (str): Phone number to send OTP to (10 digits)
            otp (str): The OTP code to be sent
            
        Returns:
            dict: Response with success status and message
        """
        try:
            # Ensure phone number is in correct format (add country code if needed)
            if phone_number.startswith('+'):
                mobile = phone_number.lstrip('+')
            elif phone_number.startswith('91'):
                mobile = phone_number
            else:
                mobile = '91' + phone_number  # Add India country code
                
            # Create connection
            conn = http.client.HTTPSConnection(self.base_url)
            
            # Prepare request payload according to MSG91 Flow API documentation
            payload = {
                "template_id": "67a60681b5d8ab2c062cb683",  # Your template ID
                "short_url": "1",
                "short_url_expiry": "60Seconds",
                "realTimeResponse": "1",
                "recipients": [
                    {
                        "mobiles": mobile,
                        "number": order_number,  # This will replace {{otp}} in your template
                        "date": date  # Additional variables if needed
                    }
                ]
            }
            
            # Set headers
            headers = {
                'authkey': self.auth_key,
                'accept': "application/json",
                'content-type': "application/json"
            }
            
            # Make the request
            conn.request("POST", "/api/v5/flow", json.dumps(payload), headers)
            
            # Get response
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            
            # Log response
            logger.info(f"order confirmation Send Response: {data}")
            
            # Parse response
            response_data = json.loads(data)
            
            if response.status == 200 and not response_data.get('type') == 'error':
                return {
                    'success': True,
                    'message': 'Order confirmation sent successfully',
                    'response': response_data
                }
            else:
                error_msg = response_data.get('msg', 'Unknown error')
                logger.error(f"MSG91 API Error: {error_msg}")
                return {
                    'success': False,
                    'message': f'Failed to send OTP: {error_msg}',
                    'response': response_data
                }
                
        except Exception as e:
            logger.error(f"Error sending OTP: {str(e)}")
            return {
                'success': False,
                'message': f'Error sending OTP: {str(e)}'
            }
    
    def send_transactional_sms(self, phone_number, message):
        """
        Send transactional SMS using MSG91 API
        
        Args:
            phone_number (str): Phone number to send SMS to
            message (str): Message content
            
        Returns:
            dict: Response with success status and message
        """
        try:
            # Ensure phone number is in correct format (add country code if needed)
            if phone_number.startswith('+'):
                mobile = phone_number.lstrip('+')
            elif phone_number.startswith('91'):
                mobile = phone_number
            else:
                mobile = '91' + phone_number  # Add India country code
                
            # Create connection
            conn = http.client.HTTPSConnection(self.base_url)
            
            # Prepare request payload for SMS API
            payload = {
                "sender": "TXTLCL",  # Replace with your sender ID
                "route": "4",  # 4 for transactional, 1 for promotional
                "country": "91",
                "sms": [
                    {
                        "message": message,
                        "to": [mobile]
                    }
                ]
            }
            
            # Set headers
            headers = {
                'authkey': self.auth_key,
                'content-type': "application/json"
            }
            
            # Make the request
            conn.request("POST", "/api/v5/flow/", json.dumps(payload), headers)
            
            # Get response
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            
            # Log response
            logger.info(f"SMS Send Response: {data}")
            
            # Parse response
            response_data = json.loads(data)
            
            if response.status == 200 and not response_data.get('type') == 'error':
                return {
                    'success': True,
                    'message': 'SMS sent successfully',
                    'response': response_data
                }
            else:
                error_msg = response_data.get('msg', 'Unknown error')
                logger.error(f"MSG91 API Error: {error_msg}")
                return {
                    'success': False,
                    'message': f'Failed to send SMS: {error_msg}',
                    'response': response_data
                }
                
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            return {
                'success': False,
                'message': f'Error sending SMS: {str(e)}'
            }