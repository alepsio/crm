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
DB_HOST = os.environ.get('DB_HOST', 'dpg-d042mnbuibrs73amtn5g-a.frankfurt-postgres.render.com')
DB_NAME = os.environ.get('DB_NAME', 'crm_96md')
DB_USER = os.environ.get('DB_USER', 'crm_96md_user')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'JUXtm5gEKXkq03EYfpWntZT0QBbHaf2Z')

# Configurazioni di logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')