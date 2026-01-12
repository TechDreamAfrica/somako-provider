from django.db import models
from django.conf import settings
from django.utils import timezone


class Notification(models.Model):
    """General notification model for all apps"""

    NOTIFICATION_TYPES = [
        # Ride notifications
        ('ride_requested', 'Ride Requested'),
        ('ride_accepted', 'Ride Accepted'),
        ('ride_arrived', 'Driver Arrived'),
        ('ride_started', 'Ride Started'),
        ('ride_completed', 'Ride Completed'),
        ('ride_cancelled', 'Ride Cancelled'),

        # Food notifications
        ('food_order_placed', 'Food Order Placed'),
        ('food_order_confirmed', 'Food Order Confirmed'),
        ('food_preparing', 'Food Being Prepared'),
        ('food_ready', 'Food Ready for Pickup'),
        ('food_out_for_delivery', 'Food Out for Delivery'),
        ('food_delivered', 'Food Delivered'),

        # Shop notifications
        ('shop_order_placed', 'Shop Order Placed'),
        ('shop_order_confirmed', 'Shop Order Confirmed'),
        ('shop_order_shipped', 'Shop Order Shipped'),
        ('shop_order_delivered', 'Shop Order Delivered'),

        # Pharmacy notifications
        ('pharmacy_order_placed', 'Pharmacy Order Placed'),
        ('pharmacy_order_confirmed', 'Pharmacy Order Confirmed'),
        ('pharmacy_order_ready', 'Pharmacy Order Ready'),
        ('pharmacy_order_delivered', 'Pharmacy Order Delivered'),

        # Rental notifications
        ('rental_booked', 'Rental Booked'),
        ('rental_confirmed', 'Rental Confirmed'),
        ('rental_started', 'Rental Started'),
        ('rental_ended', 'Rental Ended'),
        ('rental_cancelled', 'Rental Cancelled'),

        # Subscription notifications
        ('subscription_created', 'Subscription Created'),
        ('subscription_renewed', 'Subscription Renewed'),
        ('subscription_expiring', 'Subscription Expiring Soon'),
        ('subscription_expired', 'Subscription Expired'),
        ('subscription_cancelled', 'Subscription Cancelled'),

        # General notifications
        ('payment_received', 'Payment Received'),
        ('payment_failed', 'Payment Failed'),
        ('message_received', 'New Message'),
        ('review_received', 'New Review'),
    ]

    CHANNELS = [
        ('in_app', 'In-App'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('email', 'Email'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    channel = models.CharField(max_length=20, choices=CHANNELS, default='in_app')

    title = models.CharField(max_length=200)
    message = models.TextField()

    # Optional reference to related objects
    reference_id = models.CharField(max_length=100, blank=True, help_text="ID of related object (order, ride, etc.)")
    reference_type = models.CharField(max_length=50, blank=True, help_text="Type of related object (Order, Ride, etc.)")

    # Metadata
    data = models.JSONField(null=True, blank=True, help_text="Additional data for the notification")

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # SMS/WhatsApp specific
    phone_number = models.CharField(max_length=20, blank=True)
    message_sid = models.CharField(max_length=100, blank=True, help_text="SMS provider message ID")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', 'channel']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_notification_type_display()} ({self.channel})"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.read_at:
            self.read_at = timezone.now()
            self.status = 'read'
            self.save(update_fields=['read_at', 'status', 'updated_at'])

    def mark_as_sent(self, message_sid=None):
        """Mark notification as sent"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        if message_sid:
            self.message_sid = message_sid
        self.save(update_fields=['status', 'sent_at', 'message_sid', 'updated_at'])

    def mark_as_failed(self):
        """Mark notification as failed"""
        self.status = 'failed'
        self.save(update_fields=['status', 'updated_at'])


class NotificationPreference(models.Model):
    """User preferences for notifications"""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')

    # Channel preferences
    enable_in_app = models.BooleanField(default=True)
    enable_sms = models.BooleanField(default=True)
    enable_whatsapp = models.BooleanField(default=True)
    enable_email = models.BooleanField(default=True)

    # Notification type preferences
    ride_notifications = models.BooleanField(default=True)
    food_notifications = models.BooleanField(default=True)
    shop_notifications = models.BooleanField(default=True)
    pharmacy_notifications = models.BooleanField(default=True)
    rental_notifications = models.BooleanField(default=True)
    subscription_notifications = models.BooleanField(default=True)

    # Marketing preferences
    promotional_notifications = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Notification Preferences"

    def get_enabled_channels(self):
        """Return list of enabled channels"""
        channels = []
        if self.enable_in_app:
            channels.append('in_app')
        if self.enable_sms:
            channels.append('sms')
        if self.enable_whatsapp:
            channels.append('whatsapp')
        if self.enable_email:
            channels.append('email')
        return channels
