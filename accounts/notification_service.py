from django.conf import settings
import requests
import json
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via SMS (Arkeseel), WhatsApp, and in-app"""

    def __init__(self):
        # SMS will be handled by existing utils/sms_utils.py
        pass

    def create_notification(self, user, notification_type, title, message, channels=None,
                          reference_id=None, reference_type=None, data=None):
        """Create notification in database"""
        from .notification_models import Notification, NotificationPreference

        # Get user preferences
        try:
            prefs = user.notification_preferences
        except NotificationPreference.DoesNotExist:
            prefs = NotificationPreference.objects.create(user=user)

        # Default to in-app if no channels specified
        if channels is None:
            channels = prefs.get_enabled_channels()

        notifications_created = []

        for channel in channels:
            # Check if user has enabled this channel
            if channel == 'sms' and not prefs.enable_sms:
                continue
            if channel == 'whatsapp' and not prefs.enable_whatsapp:
                continue
            if channel == 'email' and not prefs.enable_email:
                continue

            notification = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                channel=channel,
                title=title,
                message=message,
                reference_id=reference_id,
                reference_type=reference_type,
                data=data,
                phone_number=user.phone_number if channel in ['sms', 'whatsapp'] else ''
            )
            notifications_created.append(notification)

        return notifications_created

    def send_sms(self, notification):
        """Send SMS via Arkesel using existing SMS utils"""
        if not notification.phone_number:
            logger.error(f"No phone number for user {notification.user.username}")
            notification.mark_as_failed()
            return False

        try:
            # Use existing SMS utils
            from utils.sms_utils import ArkeselSMS
            sms = ArkeselSMS()
            
            # Prepare SMS message
            message_text = f"{notification.title}\n\n{notification.message}"
            
            # Send SMS using existing utility
            result = sms.send_sms(notification.phone_number, message_text)
            
            if result.get('success'):
                message_id = result.get('data', {}).get('id', 'unknown') if result.get('data') else 'unknown'
                notification.mark_as_sent(message_sid=str(message_id))
                logger.info(f"SMS sent to {notification.phone_number} via Arkesel: {message_id}")
                return True
            else:
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"Arkesel SMS error: {error_msg}")
                notification.mark_as_failed()
                return False

        except ImportError:
            logger.error("SMS utils not available. Cannot send SMS.")
            notification.mark_as_failed()
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending SMS to {notification.phone_number}: {str(e)}")
            notification.mark_as_failed()
            return False

    def send_whatsapp(self, notification):
        """Send WhatsApp message - Currently disabled, falls back to SMS"""
        logger.warning("WhatsApp notifications are not configured. Falling back to SMS.")
        # Fall back to SMS for now
        return self.send_sms(notification)

    def send_notification(self, user, notification_type, title, message, channels=None,
                         reference_id=None, reference_type=None, data=None):
        """Create and send notifications across all specified channels"""

        # Create notifications
        notifications = self.create_notification(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            channels=channels,
            reference_id=reference_id,
            reference_type=reference_type,
            data=data
        )

        # Send via respective channels
        for notification in notifications:
            if notification.channel == 'sms':
                self.send_sms(notification)
            elif notification.channel == 'whatsapp':
                self.send_whatsapp(notification)
            elif notification.channel == 'in_app':
                # In-app notifications are already created, just mark as sent
                notification.mark_as_sent()
            elif notification.channel == 'email':
                # Email will be handled separately via Django's email system
                pass

        return notifications


# Convenience function
def send_notification(user, notification_type, title, message, channels=None,
                     reference_id=None, reference_type=None, data=None):
    """Shortcut function to send notification"""
    service = NotificationService()
    return service.send_notification(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        channels=channels,
        reference_id=reference_id,
        reference_type=reference_type,
        data=data
    )
