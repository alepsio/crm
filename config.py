import os
import datetime

# Configurazioni di base
DEBUG = os.environ.get('FLASK_ENV') != 'production'
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24) if DEBUG else None)

# Configurazioni di sicurezza
SESSION_COOKIE_SECURE = not DEBUG  # Solo HTTPS in produzione
SESSION_COOKIE_HTTPONLY = True  # Impedisce l'accesso JavaScript ai cookie
SESSION_COOKIE_SAMESITE = 'Lax'  # Protezione CSRF aggiuntiva
PERMANENT_SESSION_LIFETIME = datetime.timedelta(hours=8)  # Durata sessione: 8 ore

# Configurazioni di upload
UPLOAD_FOLDER = 'app/static/upload_clienti'
PDF_TEMPLATES = 'app/static/pdf_templates'
PDF_GENERATI = 'app/static/pdf_generati'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload

# Configurazioni del database
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'insurance_management')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'admin')

# Configurazioni di logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')