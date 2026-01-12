from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-your-secret-key-here')

# SECURITY WARNING: don't run with debug turned on in production!
# Default to True for local development, set DEBUG=False in production environment
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# For PythonAnywhere, you need to add your domain to ALLOWED_HOSTS
ALLOWED_HOSTS = [
    'somakoapp.pythonanywhere.com',
    'somako.org',
    'www.somako.org',
    'localhost', 
    '127.0.0.1',
]

# Site framework configuration
SITE_ID = 1


# Application definition

INSTALLED_APPS = [
    'jazzmin',  # Must be before django.contrib.admin
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Required for site domain URLs in notifications
    'core',
    'accounts',
    'messaging',  # Cross-app messaging system
    'rent',
    'pharmacy',
    'shop',
    'food',
    'ride',
    'payment',
    # PWA apps
    'food_pwa',
    'shop_pwa',
    'pharmacy_pwa',
    'rent_pwa',
    'ride_pwa',
    'express_pwa',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.PWAAccessMiddleware',  # PWA-only access enforcement
    'core.pwa_middleware.PWAAuthMiddleware',  # PWA authentication redirects
]

ROOT_URLCONF = 'somako.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.cart_counts',  # Cart counts for navbar
            ],
        },
    },
]

WSGI_APPLICATION = 'somako.wsgi.application'


# Database Configuration
if os.environ.get('USE_MYSQL', 'False').lower() == 'true':
    # MySQL configuration for PythonAnywhere
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            },
        }
    }
else:
    # SQLite configuration for local development
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Accra'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File serving configuration
import mimetypes
# Add APK MIME type for proper downloads
mimetypes.add_type('application/vnd.android.package-archive', '.apk')

# Google Drive Storage Configuration
USE_GOOGLE_DRIVE_STORAGE = os.environ.get('USE_GOOGLE_DRIVE_STORAGE', 'False').lower() == 'true'
GOOGLE_DRIVE_STORAGE_JSON_KEY_FILE = os.environ.get('GOOGLE_DRIVE_STORAGE_JSON_KEY_FILE', None)
GOOGLE_DRIVE_STORAGE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_STORAGE_FOLDER_ID', None)
GOOGLE_DRIVE_STORAGE_MAKE_PUBLIC = os.environ.get('GOOGLE_DRIVE_STORAGE_MAKE_PUBLIC', 'True').lower() == 'true'
GOOGLE_DRIVE_MEDIA_FOLDER_NAME = 'media'
GOOGLE_DRIVE_STATIC_FOLDER_NAME = 'static'

# Use Google Drive for media files if enabled
if USE_GOOGLE_DRIVE_STORAGE:
    DEFAULT_FILE_STORAGE = 'somako.storage_backends.GoogleDriveMediaStorage'
    # Optionally, use Google Drive for static files (not recommended)
    # STATICFILES_STORAGE = 'somako.storage_backends.GoogleDriveStaticStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Login/Logout URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Email Configuration
# Use console backend in DEBUG mode, SMTP otherwise
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'somakoapp@gmail.com')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', 'gdup jbcn youa kjtj')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

# Email Notification Settings
SEND_LOGIN_NOTIFICATION_EMAIL = os.environ.get('SEND_LOGIN_NOTIFICATION_EMAIL', 'False').lower() == 'true'
SEND_WELCOME_EMAIL = os.environ.get('SEND_WELCOME_EMAIL', 'True').lower() == 'true'
SEND_PASSWORD_CHANGE_EMAIL = os.environ.get('SEND_PASSWORD_CHANGE_EMAIL', 'True').lower() == 'true'

# Arkesel SMS Configuration
ARKESEL_API_KEY = os.environ.get('ARKESEL_API_KEY', "aGZPd0pPZ2xCdWpaS3BndmRka3o")
ARKESEL_SENDER_ID = os.environ.get('ARKESEL_SENDER_ID', "Soma Ko")
ARKESEL_URL = os.environ.get('ARKESEL_URL', "https://sms.arkesel.com/api/otp/generate")

# Site URL for links in SMS/Email
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Session Configuration
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Message Framework
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.DEBUG: 'debug',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Add file logging only if we can write to the logs directory
try:
    # Test if we can write to the logs directory
    test_file = LOGS_DIR / 'test.log'
    test_file.touch()
    test_file.unlink()
    
    # If successful, add file handler
    LOGGING['handlers']['file'] = {
        'level': 'INFO',
        'class': 'logging.FileHandler',
        'filename': LOGS_DIR / 'django.log',
        'formatter': 'verbose',
    }
    
    # Update loggers to include file handler
    for logger_name in ['django', 'core', 'accounts']:
        LOGGING['loggers'][logger_name]['handlers'] = ['file', 'console']
        
except (PermissionError, OSError):
    # If we can't write to logs directory, just use console logging
    pass


# Paystack Configuration
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '')

# ============================================================================
# JAZZMIN ADMIN THEME CONFIGURATION
# ============================================================================

JAZZMIN_SETTINGS = {
    # Title on the login screen & brand header
    "site_title": "Soma Ko Admin",
    "site_header": "Soma Ko",
    "site_brand": "Soma Ko Ghana",
    "site_logo": None,  # Add your logo path here if available
    "login_logo": None,  # Logo for login page
    "login_logo_dark": None,

    # Logo to use for your site, must be present in static files
    "site_logo_classes": "img-circle",

    # Relative path to a favicon for your site
    "site_icon": None,

    # Welcome text on the login screen
    "welcome_sign": "Welcome to Soma Ko Admin Panel",

    # Copyright on the footer
    "copyright": "Soma Ko Ghana - All Services in One Place",

    # Search model in the admin
    "search_model": ["auth.User", "shop.Product", "rent.Property", "food.Restaurant"],

    # Field name on user model that contains avatar ImageField/URLField/Charfield
    "user_avatar": None,

    ############
    # Top Menu #
    ############

    # Links to put along the top menu
    "topmenu_links": [
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "View Site", "url": "/", "new_window": True},
        {"name": "Support", "url": "/admin/support/", "new_window": False},
        {"model": "auth.User"},
    ],

    #############
    # User Menu #
    #############

    # Additional links to include in the user menu on the top right
    "usermenu_links": [
        {"name": "View Site", "url": "/", "new_window": True},
        {"model": "auth.user"}
    ],

    #############
    # Side Menu #
    #############

    # Whether to display the side menu
    "show_sidebar": True,

    # Whether to aut expand the menu
    "navigation_expanded": True,

    # Hide these apps when generating side menu
    "hide_apps": [],

    # Hide these models when generating side menu
    "hide_models": [],

    # List of apps (and/or models) to base side menu ordering off of
    "order_with_respect_to": [
        "auth",
        "accounts",
        "shop",
        "rent",
        "food",
        "pharmacy",
        "ride",
        "core",
    ],

    # Custom links to append to app groups, keyed on app name
    "custom_links": {
        "shop": [{
            "name": "Scrape Products",
            "url": "admin:shop_product_scrape",
            "icon": "fas fa-download",
            "permissions": ["shop.add_product"]
        }],
    },

    # Custom icons for side menu apps/models
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",

        # Accounts
        "accounts.User": "fas fa-user-circle",
        "accounts.UserProfile": "fas fa-id-card",

        # Shop
        "shop.Product": "fas fa-box",
        "shop.Category": "fas fa-tags",
        "shop.ProductVariant": "fas fa-boxes",
        "shop.ProductImage": "fas fa-images",
        "shop.Cart": "fas fa-shopping-cart",
        "shop.Order": "fas fa-receipt",
        "shop.Payment": "fas fa-credit-card",
        "shop.Review": "fas fa-star",
        "shop.Wishlist": "fas fa-heart",

        # Rent
        "rent.Property": "fas fa-home",
        "rent.Equipment": "fas fa-tools",
        "rent.PropertyCategory": "fas fa-th-large",
        "rent.EquipmentCategory": "fas fa-list",
        "rent.RentalBooking": "fas fa-calendar-check",
        "rent.RentalReview": "fas fa-comment",

        # Food
        "food.Restaurant": "fas fa-utensils",
        "food.MenuItem": "fas fa-hamburger",
        "food.FoodOrder": "fas fa-shopping-bag",
        "food.DeliveryAddress": "fas fa-map-marker-alt",

        # Pharmacy
        "pharmacy.Medicine": "fas fa-pills",
        "pharmacy.Prescription": "fas fa-file-prescription",
        "pharmacy.PharmacyOrder": "fas fa-prescription-bottle",

        # Ride
        "ride.Driver": "fas fa-car",
        "ride.Vehicle": "fas fa-taxi",
        "ride.Ride": "fas fa-route",
        "ride.RideBooking": "fas fa-calendar-alt",

        # Core
        "core.ContactMessage": "fas fa-envelope",
        "core.NewsletterSubscriber": "fas fa-newspaper",
    },

    # Icons that are used when one is not manually specified
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",

    #################
    # Related Modal #
    #################

    # Use modals instead of popups
    "related_modal_active": False,

    #############
    # UI Tweaks #
    #############

    # Relative paths to custom CSS/JS scripts (must be present in static files)
    "custom_css": None,
    "custom_js": None,

    # Whether to link font from fonts.googleapis.com
    "use_google_fonts_cdn": True,

    # Whether to show the UI customizer on the sidebar
    "show_ui_builder": True,

    ###############
    # Change view #
    ###############

    # Render out the change view as a single form, or in tabs
    "changeform_format": "horizontal_tabs",

    # Override the change form template
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },

    # Add a language dropdown into the admin
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-success",
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-success",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": True
}

# ============================================
# ARKESEL SMS API CONFIGURATION (matches utils/sms_utils.py)
# ============================================
ARKESEL_API_KEY = os.environ.get('ARKESEL_API_KEY', '')
ARKESEL_SENDER_ID = os.environ.get('ARKESEL_SENDER_ID', 'Soma Ko')

# ============================================
# PAYSTACK PAYMENT CONFIGURATION
# ============================================
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
PAYSTACK_BASE_URL = 'https://api.paystack.co'
PAYSTACK_CALLBACK_URL = os.environ.get('PAYSTACK_CALLBACK_URL', 'https://somako.org/payment/callback/')
PAYSTACK_WEBHOOK_SECRET = os.environ.get('PAYSTACK_WEBHOOK_SECRET', '')