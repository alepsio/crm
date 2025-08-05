import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import smtplib
import ssl
from email.message import EmailMessage
from functools import wraps
import PyPDF2
import uuid
import datetime
import pandas as pd
import json
import csv
from io import StringIO
from flask_wtf.csrf import CSRFProtect
import logging
import threading
import time

# Inizializza l'applicazione Flask
app = Flask(__name__, template_folder='app/templates', static_folder='app/static')

# Carica le configurazioni dal file config.py
app.config.from_pyfile('config.py')

# Assicurati che le cartelle necessarie esistano
upload_folder = os.path.join(app.static_folder, 'upload_clienti')
pdf_templates = os.path.join(app.static_folder, 'pdf_templates')
pdf_generati = os.path.join(app.static_folder, 'pdf_generati')

for folder in [upload_folder, pdf_templates, pdf_generati]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Configura il logging
logging.basicConfig(
    level=getattr(logging, app.config.get('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)

# Abilita l'escape automatico di Jinja2 per prevenire XSS
app.jinja_env.autoescape = True

# Inizializza la protezione CSRF
csrf = CSRFProtect(app)

# Configura le esenzioni CSRF per le richieste AJAX
@csrf.exempt
@app.route('/consulenze/cliente/<int:cliente_id>', methods=['PUT', 'DELETE'])
def csrf_exempt_route(cliente_id):
    return consulenze_cliente(cliente_id)

# Disabilita completamente la protezione CSRF per semplificare lo sviluppo
# Nota: in produzione, è consigliabile riabilitare la protezione CSRF
app.config['WTF_CSRF_ENABLED'] = False

# Route per servire i file caricati
@app.route('/static/upload_clienti/<path:filename>')
def serve_static_client_file(filename):
    # Gestisce i percorsi con sottocartelle
    parts = filename.split('/')
    if len(parts) > 1:
        # Se il percorso contiene sottocartelle
        subfolder = '/'.join(parts[:-1])
        filename = parts[-1]
        path = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    else:
        # Se il percorso è diretto
        path = app.config['UPLOAD_FOLDER']
    
    return send_from_directory(path, filename)

# Custom Jinja2 filters
@app.template_filter('count_users_with_package')
def count_users_with_package(users, package_name):
    count = 0
    for user in users:
        if 'pacchetti' in user and package_name in user['pacchetti']:
            count += 1
    return count

@app.template_filter('type')
def get_type(value):
    return str(type(value))

@app.template_filter('truncate')
def truncate_text(text, length=100, end='...'):
    """Truncate text to a specified length."""
    if text is None:
        return ""
    if len(text) <= length:
        return text
    return text[:length] + end

@app.template_filter('date')
def format_date(value, format='%d/%m/%Y'):
    """Format a date."""
    if value is None:
        return ""
    
    from datetime import datetime
    
    if isinstance(value, str):
        try:
            # Prova a convertire la stringa in datetime
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except:
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M')
            except:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d')
                except:
                    # Se non riesce a convertire, restituisci la stringa originale
                    return value
    
    # Se è una data senza ora, usa solo il formato della data
    if value.hour == 0 and value.minute == 0 and value.second == 0:
        return value.strftime('%d/%m/%Y')
    
    # Altrimenti, includi anche l'ora
    return value.strftime('%d/%m/%Y %H:%M')

# Database connection
def get_db_connection():
    conn = psycopg2.connect(
        host=app.config.get('DB_HOST', 'localhost'),
        database=app.config.get('DB_NAME', 'insurance_management'),
        user=app.config.get('DB_USER', 'postgres'),
        password=app.config.get('DB_PASSWORD', 'admin'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    conn.autocommit = True
    return conn

# Decorator to check if user is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Accesso negato. Effettua il login.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Funzione per verificare la complessità della password
def is_password_strong(password):
    """
    Verifica che la password soddisfi i requisiti minimi di sicurezza:
    - Almeno 8 caratteri
    - Almeno una lettera maiuscola
    - Almeno una lettera minuscola
    - Almeno un numero
    - Almeno un carattere speciale
    """
    if len(password) < 8:
        return False, "La password deve contenere almeno 8 caratteri"
    
    if not any(c.isupper() for c in password):
        return False, "La password deve contenere almeno una lettera maiuscola"
    
    if not any(c.islower() for c in password):
        return False, "La password deve contenere almeno una lettera minuscola"
    
    if not any(c.isdigit() for c in password):
        return False, "La password deve contenere almeno un numero"
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/" for c in password):
        return False, "La password deve contenere almeno un carattere speciale"
    
    return True, "Password valida"

# Funzione per verificare la validità del codice fiscale
def is_valid_codice_fiscale(cf):
    """
    Verifica che il codice fiscale abbia un formato valido:
    - 16 caratteri
    - I primi 6 sono lettere
    - I successivi 2 sono numeri
    - Il successivo è una lettera
    - I successivi 2 sono numeri
    - Il successivo è una lettera
    - I successivi 3 sono numeri
    - L'ultimo è una lettera
    """
    if not cf:
        return False, "Codice fiscale mancante"
    
    # Tronca il codice fiscale a 16 caratteri se è più lungo
    if len(cf) > 16:
        cf = cf[:16]
        
    if len(cf) != 16:
        return False, "Il codice fiscale deve essere di 16 caratteri"
    
    cf = cf.upper()
    
    # Verifica il pattern generale
    if not (
        all(c.isalpha() for c in cf[0:6]) and
        all(c.isdigit() for c in cf[6:8]) and
        cf[8].isalpha() and
        all(c.isdigit() for c in cf[9:11]) and
        cf[11].isalpha() and
        all(c.isdigit() for c in cf[12:15]) and
        cf[15].isalpha()
    ):
        return False, "Formato del codice fiscale non valido"
    
    return True, "Codice fiscale valido"

# Decorator to check if user has specific package
def has_package(package_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Accesso negato. Effettua il login.', 'danger')
                return redirect(url_for('login'))
            
            # Ottieni i pacchetti dalla sessione
            packages = session.get('packages', [])
            
            # Se i pacchetti non sono nella sessione, recuperali dal database
            if not packages:
                conn = get_db_connection()
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("SELECT pacchetti FROM users WHERE id = %s", (session['user_id'],))
                user = cur.fetchone()
                cur.close()
                conn.close()
                
                if user:
                    packages = user['pacchetti']
                    # Aggiorna la sessione con i pacchetti
                    session['packages'] = packages
            
            # Assicurati che i pacchetti siano una lista
            if packages is None:
                packages = []
            elif isinstance(packages, str):
                try:
                    # Prova a convertire la stringa in lista (se è in formato JSON)
                    import json
                    packages = json.loads(packages)
                except:
                    # Se non è in formato JSON, prova a convertirla in altro modo
                    if packages.startswith('{') and packages.endswith('}'):
                        # Formato PostgreSQL array
                        packages = packages.strip('{}').split(',')
                    else:
                        packages = [packages]
            
            # Debug: stampa i pacchetti nel log
            app.logger.info(f"has_package: Pacchetti per l'utente {session.get('username')}: {packages}, tipo: {type(packages)}")
            app.logger.info(f"has_package: Verifica se '{package_name}' è in {packages}: {package_name in packages}")
            
            # Aggiorna la sessione con i pacchetti convertiti
            session['packages'] = packages
            
            # Verifica se l'utente ha il pacchetto richiesto
            if package_name not in packages:
                flash('Non hai accesso a questa funzionalità.', 'danger')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Protezione contro attacchi di timing
        from time import sleep
        import random
        sleep(random.uniform(0.1, 0.3))  # Aggiunge un ritardo casuale per prevenire timing attacks
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Verifica se l'utente esiste
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        
        # Registra il tentativo di login
        client_ip = request.remote_addr
        login_success = False
        
        if user and check_password_hash(user['password'], password):
            login_success = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['ruolo']
            
            # Verifica se la colonna last_login esiste
            try:
                cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user['id'],))
            except psycopg2.Error:
                # Se la colonna non esiste, ignora l'errore
                conn.rollback()
            
            # Assicurati che i pacchetti siano una lista
            packages = user['pacchetti']
            if packages is None:
                packages = []
            # Se è una stringa (può succedere con alcuni driver di database), convertila in lista
            elif isinstance(packages, str):
                try:
                    # Prova a convertire la stringa in lista (se è in formato JSON)
                    import json
                    packages = json.loads(packages)
                except:
                    # Se non è in formato JSON, prova a convertirla in altro modo
                    if packages.startswith('{') and packages.endswith('}'):
                        # Formato PostgreSQL array
                        packages = packages.strip('{}').split(',')
                    else:
                        packages = [packages]
            
            session['packages'] = packages
            
            # Imposta la durata della sessione (8 ore)
            session.permanent = True
            app.permanent_session_lifetime = datetime.timedelta(hours=8)
            
            flash('Login effettuato con successo!', 'success')
            
            # Registra il login nel log
            app.logger.info(f"Login riuscito per l'utente {username} da IP {client_ip}")
            
            return redirect(url_for('dashboard'))
        else:
            # Registra il tentativo fallito nel log
            app.logger.warning(f"Tentativo di login fallito per l'utente {username} da IP {client_ip}")
            flash('Username o password non validi.', 'danger')
        
        cur.close()
        conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logout effettuato con successo.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Ottieni i pacchetti dalla sessione
    packages = session.get('packages', [])
    
    # Se i pacchetti non sono nella sessione, recuperali dal database
    if not packages:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT pacchetti FROM users WHERE id = %s", (session['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            packages = user['pacchetti']
            # Aggiorna la sessione con i pacchetti
            session['packages'] = packages
    
    # Assicurati che i pacchetti siano una lista
    if packages is None:
        packages = []
    elif isinstance(packages, str):
        try:
            # Prova a convertire la stringa in lista (se è in formato JSON)
            import json
            packages = json.loads(packages)
        except:
            # Se non è in formato JSON, prova a convertirla in altro modo
            if packages.startswith('{') and packages.endswith('}'):
                # Formato PostgreSQL array
                packages = packages.strip('{}').split(',')
            else:
                packages = [packages]
    
    # Debug: stampa i pacchetti nel log
    app.logger.info(f"Pacchetti per l'utente {session.get('username')}: {packages}, tipo: {type(packages)}")
    
    # Aggiorna la sessione con i pacchetti convertiti
    session['packages'] = packages
    
    return render_template('dashboard.html', packages=packages)

# Admin routes
@app.route('/admin')
@login_required
def admin():
    if session.get('role') != 'admin':
        flash('Accesso negato. Solo gli amministratori possono accedere a questa pagina.', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Get users
    cur.execute("SELECT * FROM users ORDER BY username")
    users = cur.fetchall()
    
    # Get PDF statistics
    cur.execute("SELECT COUNT(*) FROM template_pdf")
    questionari_count = cur.fetchone()[0]
    
    # Get sent questionnaires count
    try:
        cur.execute("SELECT COUNT(*) FROM questionari_inviati")
        questionari_inviati = cur.fetchone()[0]
    except:
        # If the table doesn't exist yet, fall back to the old method
        cur.execute("SELECT COUNT(*) FROM clienti_assicurativi WHERE questionario_inviato = TRUE AND (user_id = %s OR user_id IS NULL)",
                   (session.get('user_id'),))
        questionari_inviati = cur.fetchone()[0]
    
    # Check SMTP configuration
    cur.execute("SELECT * FROM config_email LIMIT 1")
    smtp_config = cur.fetchone()
    smtp_configured = 100 if smtp_config else 0
    
    # Get current date for the template
    now = datetime.datetime.now()
    
    cur.close()
    conn.close()
    
    return render_template('admin/index.html', 
                          users=users, 
                          questionari_count=questionari_count,
                          questionari_inviati=questionari_inviati,
                          smtp_configured=smtp_configured,
                          now=now)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    if session.get('role') != 'admin':
        flash('Accesso negato. Solo gli amministratori possono accedere a questa pagina.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        packages = request.form.getlist('packages')
        
        # Debug: stampa i pacchetti nel log
        app.logger.info(f"Pacchetti per il nuovo utente {username}: {packages}, tipo: {type(packages)}")
        
        # Verifica la complessità della password
        is_strong, message = is_password_strong(password)
        if not is_strong:
            flash(f'Password non sicura: {message}', 'danger')
            return render_template('admin/add_user.html')
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Verifica se l'username esiste già
            cur.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
            if cur.fetchone()[0] > 0:
                flash('Username già in uso. Scegli un altro username.', 'danger')
                return render_template('admin/add_user.html')
            
            # Assicurati che i pacchetti siano un array PostgreSQL
            if not packages:
                packages = []
                
            cur.execute(
                "INSERT INTO users (username, password, ruolo, pacchetti) VALUES (%s, %s, %s, %s)",
                (username, hashed_password, role, packages)
            )
            flash('Utente aggiunto con successo!', 'success')
            return redirect(url_for('admin'))
        except psycopg2.Error as e:
            flash(f'Errore durante l\'aggiunta dell\'utente: {e}', 'danger')
        finally:
            cur.close()
            conn.close()
    
    return render_template('admin/add_user.html')

@app.route('/admin/reset-smtp', methods=['POST'])
@login_required
def admin_reset_smtp():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Accesso negato'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM config_email")
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Configurazione SMTP resettata con successo'})

# Gestione Consulenze Assicurative routes
@app.route('/consulenze')
@login_required
@has_package('manage_consulenze')
def consulenze_index():
    # Debug: stampa i pacchetti nel log
    packages = session.get('packages', [])
    app.logger.info(f"consulenze_index: Pacchetti per l'utente {session.get('username')}: {packages}, tipo: {type(packages)}")
    app.logger.info(f"consulenze_index: Verifica se 'manage_consulenze' è in {packages}: {'manage_consulenze' in packages}")
    
    return render_template('tools/consulenze/index.html')

@app.route('/consulenze/import', methods=['GET', 'POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_import():
    if request.method == 'POST':
        if 'excelFile' not in request.files:
            flash('Nessun file selezionato', 'danger')
            return redirect(request.url)
        
        file = request.files['excelFile']
        if file.filename == '':
            flash('Nessun file selezionato', 'danger')
            return redirect(request.url)
        
        if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            # Salva il file temporaneamente
            filename = secure_filename(f"import_{uuid.uuid4()}.xlsx")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Leggi il file Excel
            try:
                skip_header = 'skipHeader' in request.form
                update_existing = 'updateExisting' in request.form
                
                if file.filename.endswith('.xlsx'):
                    df = pd.read_excel(file_path, header=0 if skip_header else None)
                else:
                    df = pd.read_excel(file_path, header=0 if skip_header else None, engine='xlrd')
                
                # Debug: stampa le colonne originali
                app.logger.info(f"Colonne originali: {df.columns.tolist()}")
                
                # Rinomina le colonne se necessario
                if skip_header:
                    # Assicurati che le colonne abbiano i nomi corretti
                    column_mapping = {
                        'Nome': 'nome',
                        'Cognome': 'cognome',
                        'Email': 'email',
                        'Codice Fiscale': 'codice_fiscale',
                        'Cellulare': 'cellulare',
                        'Partita IVA': 'partita_iva',
                        'PEC': 'pec',
                        'Codice Univoco': 'codice_univoco',
                        'Residenza': 'residenza',
                        'Domicilio Fiscale': 'domicilio_fiscale',
                        'Attività': 'attivita',
                        'Data Nascita': 'data_nascita',
                        'Luogo Nascita': 'luogo_nascita'
                    }
                    
                    # Normalizza i nomi delle colonne (rimuovi spazi extra, converti in minuscolo)
                    normalized_columns = {}
                    for col in df.columns:
                        if isinstance(col, str):
                            normalized_columns[col] = col.strip().lower().replace(' ', '_')
                        else:
                            normalized_columns[col] = col
                    
                    df = df.rename(columns=normalized_columns)
                    
                    # Applica il mapping standard
                    df = df.rename(columns=lambda x: column_mapping.get(x, x))
                    
                    # Debug: stampa le colonne rinominate
                    app.logger.info(f"Colonne rinominate: {df.columns.tolist()}")
                
                # Converti DataFrame in lista di dizionari
                preview_data = df.fillna('').to_dict('records')
                
                # Debug: stampa i primi record
                app.logger.info(f"Primi record: {preview_data[:2] if preview_data else 'Nessun dato'}")
                
                # Verifica se i campi obbligatori sono presenti
                required_fields = ['nome', 'cognome', 'email', 'codice_fiscale']
                missing_fields = [field for field in required_fields if field not in df.columns]
                
                if missing_fields:
                    app.logger.error(f"Campi obbligatori mancanti nel file: {missing_fields}")
                    flash(f"Campi obbligatori mancanti nel file: {', '.join(missing_fields)}. Assicurati che il file contenga le colonne: Nome, Cognome, Email, Codice Fiscale.", 'danger')
                    return redirect(request.url)
                
                # Verifica se i clienti esistono già e valida i dati
                conn = get_db_connection()
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                for i, row in enumerate(preview_data):
                    # Verifica se il cliente esiste già
                    if 'codice_fiscale' in row and row['codice_fiscale']:
                        # Valida il codice fiscale
                        is_valid, message = is_valid_codice_fiscale(row['codice_fiscale'])
                        preview_data[i]['cf_valid'] = is_valid
                        preview_data[i]['cf_message'] = message
                        
                        # Se il codice fiscale è valido, verifica se esiste già
                        if is_valid:
                            cur.execute("SELECT id FROM clienti_assicurativi WHERE codice_fiscale = %s AND (user_id = %s OR user_id IS NULL)", 
                                      (row['codice_fiscale'], session.get('user_id')))
                            result = cur.fetchone()
                            preview_data[i]['exists'] = result is not None
                        else:
                            preview_data[i]['exists'] = False
                    else:
                        preview_data[i]['cf_valid'] = False
                        preview_data[i]['cf_message'] = "Codice fiscale mancante"
                        preview_data[i]['exists'] = False
                    
                    # Verifica se i campi obbligatori sono presenti
                    required_fields = ['nome', 'cognome', 'email']
                    missing_fields = [field for field in required_fields if field not in row or not row[field]]
                    preview_data[i]['valid'] = len(missing_fields) == 0 and preview_data[i]['cf_valid']
                    preview_data[i]['missing_fields'] = missing_fields
                
                cur.close()
                conn.close()
                
                return render_template('tools/consulenze/import.html', 
                                      preview_data=preview_data, 
                                      file_path=file_path,
                                      update_existing=update_existing)
            
            except Exception as e:
                flash(f'Errore durante la lettura del file: {str(e)}', 'danger')
                return redirect(request.url)
        else:
            flash('Formato file non supportato. Utilizza .xlsx o .xls', 'danger')
            return redirect(request.url)
    
    return render_template('tools/consulenze/import.html')

@app.route('/consulenze/import-selected', methods=['POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_import_selected():
    file_path = request.form.get('file_path')
    update_existing = request.form.get('update_existing') == 'true'
    selected_rows = request.form.getlist('selected_rows')
    
    if not file_path or not selected_rows:
        flash('Dati mancanti', 'danger')
        return redirect(url_for('consulenze_import'))
    
    try:
        # Leggi il file Excel
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, header=0)
        else:
            df = pd.read_excel(file_path, header=0, engine='xlrd')
            
        # Debug: stampa le colonne
        app.logger.info(f"Colonne nel file di importazione: {df.columns.tolist()}")
        
        # Normalizza i nomi delle colonne
        column_mapping = {
            'Nome': 'nome',
            'Cognome': 'cognome',
            'Email': 'email',
            'Codice Fiscale': 'codice_fiscale',
            'Cellulare': 'cellulare',
            'Partita IVA': 'partita_iva',
            'PEC': 'pec',
            'Codice Univoco': 'codice_univoco',
            'Residenza': 'residenza',
            'Domicilio Fiscale': 'domicilio_fiscale',
            'Attività': 'attivita',
            'Data Nascita': 'data_nascita',
            'Luogo Nascita': 'luogo_nascita'
        }
        
        # Normalizza i nomi delle colonne (rimuovi spazi extra, converti in minuscolo)
        normalized_columns = {}
        for col in df.columns:
            if isinstance(col, str):
                normalized_columns[col] = col.strip().lower().replace(' ', '_')
            else:
                normalized_columns[col] = col
        
        df = df.rename(columns=normalized_columns)
        
        # Applica il mapping standard
        df = df.rename(columns=lambda x: column_mapping.get(x, x))
        
        # Debug: stampa le colonne rinominate
        app.logger.info(f"Colonne rinominate: {df.columns.tolist()}")
        
        # Converti DataFrame in lista di dizionari
        all_data = df.fillna('').to_dict('records')
        
        # Debug: stampa i primi record
        app.logger.info(f"Primi record: {all_data[:2] if all_data else 'Nessun dato'}")
        
        # Filtra solo le righe selezionate
        selected_data = [all_data[int(i)] for i in selected_rows if int(i) < len(all_data)]
        
        # Importa i dati nel database
        conn = get_db_connection()
        cur = conn.cursor()
        
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        error_log = []
        
        for i, row in enumerate(selected_data):
            # Debug: stampa il record corrente
            app.logger.info(f"Elaborazione record {i+1}: {row}")
            
            # Verifica se i campi obbligatori sono presenti
            required_fields = ['nome', 'cognome', 'email', 'codice_fiscale']
            missing_fields = []
            
            for field in required_fields:
                if field not in row:
                    missing_fields.append(field)
                elif not row[field]:
                    missing_fields.append(field)
                elif isinstance(row[field], float) and pd.isna(row[field]):
                    missing_fields.append(field)
            
            if missing_fields:
                app.logger.error(f"Campi mancanti nel record {i+1}: {missing_fields}")
                error_log.append({
                    'riga': i + 1,
                    'nome': row.get('nome', ''),
                    'cognome': row.get('cognome', ''),
                    'codice_fiscale': row.get('codice_fiscale', ''),
                    'errore': f"Campi obbligatori mancanti: {', '.join(missing_fields)}"
                })
                skipped_count += 1
                continue
                
            # Valida il codice fiscale
            is_valid, message = is_valid_codice_fiscale(row['codice_fiscale'])
            if not is_valid:
                error_log.append({
                    'riga': i + 1,
                    'nome': row.get('nome', ''),
                    'cognome': row.get('cognome', ''),
                    'codice_fiscale': row.get('codice_fiscale', ''),
                    'errore': f"Codice fiscale non valido: {message}"
                })
                skipped_count += 1
                continue
                
            # Verifica se il cliente esiste già (solo per l'utente corrente)
            if 'codice_fiscale' in row and row['codice_fiscale']:
                cur.execute("SELECT id FROM clienti_assicurativi WHERE codice_fiscale = %s AND (user_id = %s OR user_id IS NULL)", 
                           (row['codice_fiscale'], session.get('user_id')))
                existing = cur.fetchone()
                
                if existing and update_existing:
                    # Aggiorna il cliente esistente
                    update_fields = []
                    update_values = []
                    
                    # Definisci i limiti di lunghezza per i campi
                    field_limits = {
                        'nome': 100,
                        'cognome': 100,
                        'email': 100,
                        'cellulare': 20,
                        'partita_iva': 11,
                        'pec': 100,
                        'codice_univoco': 7,
                        'codice_fiscale': 16,
                        'attivita': 255,
                        'luogo_nascita': 100,
                        # I campi di tipo text non hanno limiti di lunghezza
                        'residenza': None,
                        'domicilio_fiscale': None,
                        'ubicazione_studio': None
                    }
                    
                    # Campi di testo standard
                    for key, value in row.items():
                        if key in [
                            'nome', 'cognome', 'email', 'cellulare', 'partita_iva', 
                            'pec', 'codice_univoco', 'residenza', 'domicilio_fiscale', 
                            'attivita', 'luogo_nascita'
                        ]:
                            update_fields.append(f"{key} = %s")
                            # Tronca il valore se necessario
                            if key in field_limits and field_limits[key] is not None:
                                update_values.append(str(value)[:field_limits[key]])
                            else:
                                update_values.append(str(value))
                    
                    # Gestisci i campi di tipo date
                    if 'data_nascita' in row and row['data_nascita']:
                        try:
                            # Converti la data dal formato GG/MM/AAAA a AAAA-MM-GG
                            date_parts = row['data_nascita'].split('/')
                            if len(date_parts) == 3:
                                formatted_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
                                update_fields.append("data_nascita = %s")
                                update_values.append(formatted_date)
                        except:
                            # Se la conversione fallisce, ignora il campo
                            pass
                    
                    if update_fields:
                        update_values.append(existing[0])  # ID del cliente
                        cur.execute(f"UPDATE clienti_assicurativi SET {', '.join(update_fields)} WHERE id = %s", update_values)
                        updated_count += 1
                
                elif not existing:
                    # Inserisci nuovo cliente
                    fields = ['nome', 'cognome', 'codice_fiscale', 'email', 'user_id']
                    values = [
                        str(row.get('nome', ''))[:100], 
                        str(row.get('cognome', ''))[:100], 
                        str(row.get('codice_fiscale', ''))[:16], 
                        str(row.get('email', ''))[:100], 
                        session.get('user_id')
                    ]
                    
                    # Aggiungi campi opzionali se presenti
                    optional_fields = [
                        'cellulare', 'partita_iva', 'pec', 'codice_univoco', 
                        'residenza', 'domicilio_fiscale', 'attivita'
                    ]
                    
                    # Definisci i limiti di lunghezza per i campi
                    field_limits = {
                        'cellulare': 20,
                        'partita_iva': 11,
                        'pec': 100,
                        'codice_univoco': 7,
                        'attivita': 255,
                        # I campi di tipo text non hanno limiti di lunghezza
                        'residenza': None,
                        'domicilio_fiscale': None
                    }
                    
                    for field in optional_fields:
                        if field in row and row[field]:
                            fields.append(field)
                            # Tronca il valore se necessario
                            if field in field_limits and field_limits[field] is not None:
                                values.append(str(row[field])[:field_limits[field]])
                            else:
                                values.append(str(row[field]))
                    
                    # Gestisci i campi di tipo date
                    date_fields = ['data_nascita']
                    for field in date_fields:
                        if field in row and row[field]:
                            try:
                                # Converti la data dal formato GG/MM/AAAA a AAAA-MM-GG
                                date_parts = row[field].split('/')
                                if len(date_parts) == 3:
                                    formatted_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
                                    fields.append(field)
                                    values.append(formatted_date)
                            except:
                                # Se la conversione fallisce, ignora il campo
                                pass
                    
                    # Aggiungi altri campi di testo
                    text_fields = ['luogo_nascita']
                    for field in text_fields:
                        if field in row and row[field]:
                            fields.append(field)
                            values.append(row[field])
                    
                    placeholders = ', '.join(['%s'] * len(fields))
                    cur.execute(
                        f"INSERT INTO clienti_assicurativi ({', '.join(fields)}) VALUES ({placeholders})",
                        values
                    )
                    imported_count += 1
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Elimina il file temporaneo
        if os.path.exists(file_path):
            os.remove(file_path)
        
        message_parts = []
        if imported_count > 0:
            message_parts.append(f"{imported_count} clienti importati")
        if updated_count > 0:
            message_parts.append(f"{updated_count} clienti aggiornati")
        if skipped_count > 0:
            message_parts.append(f"{skipped_count} clienti saltati per dati non validi")
            
        if message_parts:
            flash(f'Importazione completata: {", ".join(message_parts)}', 'success' if imported_count > 0 or updated_count > 0 else 'warning')
        else:
            flash('Nessun cliente importato o aggiornato', 'warning')
        
        # Se ci sono errori, salva il log in una sessione temporanea
        if error_log:
            session['import_error_log'] = error_log
            return redirect(url_for('consulenze_import_results'))
        
        return redirect(url_for('consulenze_panoramica'))
    
    except Exception as e:
        app.logger.error(f"Errore durante l'importazione: {str(e)}")
        flash(f'Errore durante l\'importazione: {str(e)}', 'danger')
        return redirect(url_for('consulenze_import'))

@app.route('/consulenze/debug-excel', methods=['POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_debug_excel():
    if 'excelFile' not in request.files:
        return jsonify({'success': False, 'message': 'Nessun file selezionato'})
    
    file = request.files['excelFile']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nessun file selezionato'})
    
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        # Salva il file temporaneamente
        filename = secure_filename(f"debug_{uuid.uuid4()}.xlsx")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Leggi il file Excel
        try:
            if file.filename.endswith('.xlsx'):
                df = pd.read_excel(file_path, header=0)
            else:
                df = pd.read_excel(file_path, header=0, engine='xlrd')
            
            # Ottieni informazioni sul file
            info = {
                'columns': df.columns.tolist(),
                'rows': len(df),
                'sample': df.head(3).fillna('').to_dict('records')
            }
            
            # Elimina il file temporaneo
            if os.path.exists(file_path):
                os.remove(file_path)
            
            return jsonify({'success': True, 'info': info})
        
        except Exception as e:
            app.logger.error(f"Errore durante il debug del file Excel: {str(e)}")
            return jsonify({'success': False, 'message': f'Errore durante la lettura del file: {str(e)}'})
    else:
        return jsonify({'success': False, 'message': 'Formato file non supportato. Utilizza .xlsx o .xls'})

@app.route('/consulenze/import-results', methods=['GET'])
@login_required
@has_package('manage_consulenze')
def consulenze_import_results():
    error_log = session.get('import_error_log', [])
    
    # Rimuovi il log dalla sessione
    if 'import_error_log' in session:
        del session['import_error_log']
    
    return render_template('tools/consulenze/import_results.html', error_log=error_log)

@app.route('/consulenze/import-error-log', methods=['GET'])
@login_required
@has_package('manage_consulenze')
def consulenze_import_error_log():
    error_log = session.get('import_error_log', [])
    
    # Crea un file CSV con gli errori
    output = StringIO()
    writer = csv.writer(output)
    
    # Intestazione
    writer.writerow(['Riga', 'Nome', 'Cognome', 'Codice Fiscale', 'Errore'])
    
    # Dati
    for error in error_log:
        writer.writerow([
            error.get('riga', ''),
            error.get('nome', ''),
            error.get('cognome', ''),
            error.get('codice_fiscale', ''),
            error.get('errore', '')
        ])
    
    # Prepara la risposta
    output.seek(0)
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    
    response = app.response_class(
        response=output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=errori_importazione_{timestamp}.csv'}
    )
    
    return response

@app.route('/consulenze/email-texts', methods=['GET', 'POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_email_texts():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'POST':
        text_id = request.form.get('textId')
        text_name = request.form.get('textName')
        text_content = request.form.get('textContent')
        
        try:
            if text_id:
                # Aggiorna testo esistente
                cur.execute(
                    "UPDATE email_texts SET nome = %s, testo = %s WHERE id = %s",
                    (text_name, text_content, text_id)
                )
                message = 'Testo email aggiornato con successo'
            else:
                # Crea nuovo testo
                cur.execute(
                    "INSERT INTO email_texts (nome, testo) VALUES (%s, %s)",
                    (text_name, text_content)
                )
                message = 'Testo email creato con successo'
            
            conn.commit()
            flash(message, 'success')
            
            # Se è una richiesta AJAX, restituisci JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': message})
                
        except Exception as e:
            conn.rollback()
            error_message = f'Errore durante il salvataggio: {str(e)}'
            flash(error_message, 'danger')
            
            # Se è una richiesta AJAX, restituisci JSON di errore
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': error_message})
    
    # Ottieni tutti i testi email
    cur.execute("""
        SELECT et.*, COUNT(q.id) as usage_count 
        FROM email_texts et
        LEFT JOIN questionari_inviati q ON q.email_text_id = et.id
        GROUP BY et.id
        ORDER BY et.nome
    """)
    email_texts = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/email_texts.html', email_texts=email_texts)

@app.route('/consulenze/email-texts/<int:text_id>', methods=['DELETE'])
@login_required
@has_package('manage_consulenze')
def delete_email_text(text_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Verifica se il testo è in uso
    cur.execute("SELECT COUNT(*) FROM questionari_inviati WHERE email_text_id = %s", (text_id,))
    usage_count = cur.fetchone()[0]
    
    if usage_count > 0:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'message': f'Impossibile eliminare: il testo è utilizzato in {usage_count} invii'}), 400
    
    # Elimina il testo
    cur.execute("DELETE FROM email_texts WHERE id = %s", (text_id,))
    conn.commit()
    
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Testo eliminato con successo'})

@app.route('/consulenze/calendar')
@login_required
@has_package('manage_consulenze')
def consulenze_calendar():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Ottieni tutti i clienti per il filtro (solo per l'utente corrente)
    cur.execute("SELECT id, nome, cognome FROM clienti_assicurativi WHERE user_id = %s OR user_id IS NULL ORDER BY cognome, nome",
                (session.get('user_id'),))
    clients = cur.fetchall()
    
    # Ottieni eventi imminenti (prossimi 7 giorni)
    cur.execute("""
        SELECT e.*, 
               c.nome || ' ' || c.cognome as client_name,
               CASE 
                   WHEN e.start_time IS NOT NULL THEN 
                       e.start_date || ' ' || e.start_time
                   ELSE 
                       e.start_date::text
               END as start,
               CASE
                   WHEN e.type = 'appointment' THEN 'Appuntamento'
                   WHEN e.type = 'deadline' THEN 'Scadenza'
                   WHEN e.type = 'reminder' THEN 'Promemoria'
                   ELSE e.type
               END as type_label
        FROM eventi e
        LEFT JOIN clienti_assicurativi c ON e.client_id = c.id
        WHERE e.start_date >= CURRENT_DATE AND e.start_date <= CURRENT_DATE + INTERVAL '7 days'
        ORDER BY e.start_date, e.start_time
    """)
    upcoming_events = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/calendar.html', 
                          clients=clients, 
                          upcoming_events=upcoming_events)

@app.route('/consulenze/events', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
@has_package('manage_consulenze')
def manage_events():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'GET':
        # Ottieni tutti gli eventi o filtra per data/cliente
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        client_id = request.args.get('client_id')
        event_type = request.args.get('type')
        
        query = "SELECT * FROM eventi WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND start_date >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND start_date <= %s"
            params.append(end_date)
        
        if client_id:
            query += " AND client_id = %s"
            params.append(client_id)
        
        if event_type:
            query += " AND type = %s"
            params.append(event_type)
        
        cur.execute(query, params)
        events = cur.fetchall()
        
        # Formatta gli eventi per FullCalendar
        formatted_events = []
        for event in events:
            formatted_event = {
                'id': event['id'],
                'title': event['title'],
                'start': event['start_date'].isoformat(),
                'allDay': event['all_day'],
                'classNames': [f"event-type-{event['type']}"],
                'extendedProps': {
                    'type': event['type'],
                    'description': event['description'],
                    'client_id': event['client_id']
                }
            }
            
            if not event['all_day'] and event['start_time']:
                formatted_event['start'] += f"T{event['start_time'].isoformat()}"
            
            if event['end_date']:
                formatted_event['end'] = event['end_date'].isoformat()
                if not event['all_day'] and event['end_time']:
                    formatted_event['end'] += f"T{event['end_time'].isoformat()}"
            
            formatted_events.append(formatted_event)
        
        cur.close()
        conn.close()
        
        return jsonify(formatted_events)
    
    elif request.method == 'POST':
        # Crea nuovo evento
        data = request.json
        
        title = data.get('title')
        event_type = data.get('type')
        start_date = data.get('start_date')
        start_time = data.get('start_time')
        end_date = data.get('end_date')
        end_time = data.get('end_time')
        all_day = data.get('all_day', True)
        client_id = data.get('client_id')
        description = data.get('description', '')
        notify = data.get('notify', False)
        notify_days = data.get('notify_days', 0)
        notify_email = data.get('notify_email', '')
        
        cur.execute("""
            INSERT INTO eventi (
                title, type, start_date, start_time, end_date, end_time, 
                all_day, client_id, description, notify, notify_days, notify_email
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            title, event_type, start_date, start_time, end_date, end_time,
            all_day, client_id, description, notify, notify_days, notify_email
        ))
        
        event_id = cur.fetchone()[0]
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'id': event_id})
    
    elif request.method == 'PUT':
        # Aggiorna evento esistente
        event_id = request.view_args.get('event_id')
        data = request.json
        
        title = data.get('title')
        event_type = data.get('type')
        start_date = data.get('start_date')
        start_time = data.get('start_time')
        end_date = data.get('end_date')
        end_time = data.get('end_time')
        all_day = data.get('all_day', True)
        client_id = data.get('client_id')
        description = data.get('description', '')
        notify = data.get('notify', False)
        notify_days = data.get('notify_days', 0)
        notify_email = data.get('notify_email', '')
        
        cur.execute("""
            UPDATE eventi SET
                title = %s, type = %s, start_date = %s, start_time = %s,
                end_date = %s, end_time = %s, all_day = %s, client_id = %s,
                description = %s, notify = %s, notify_days = %s, notify_email = %s
            WHERE id = %s
        """, (
            title, event_type, start_date, start_time, end_date, end_time,
            all_day, client_id, description, notify, notify_days, notify_email,
            event_id
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True})
    
    elif request.method == 'DELETE':
        # Elimina evento
        event_id = request.view_args.get('event_id')
        
        cur.execute("DELETE FROM eventi WHERE id = %s", (event_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Metodo non supportato'}), 405

@app.route('/consulenze/history')
@login_required
@has_package('manage_consulenze')
def consulenze_history():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Ottieni parametri di filtro
    cliente_id = request.args.get('cliente')
    template_id = request.args.get('template')
    data_da = request.args.get('data_da')
    data_a = request.args.get('data_a')
    page = int(request.args.get('page', 1))
    per_page = 20
    
    # Costruisci query con filtri
    query = """
        SELECT qi.*, c.nome as cliente_nome, c.cognome as cliente_cognome, 
               c.email, t.nome as template_nome
        FROM questionari_inviati qi
        JOIN clienti_assicurativi c ON qi.cliente_id = c.id
        JOIN template_pdf t ON qi.template_id = t.id
        WHERE 1=1
    """
    
    params = []
    filters = {}
    
    if cliente_id:
        query += " AND qi.cliente_id = %s"
        params.append(cliente_id)
        filters['cliente'] = cliente_id
    
    if template_id:
        query += " AND qi.template_id = %s"
        params.append(template_id)
        filters['template'] = template_id
    
    if data_da:
        query += " AND qi.data_invio >= %s"
        params.append(data_da)
        filters['data_da'] = data_da
    
    if data_a:
        query += " AND qi.data_invio <= %s"
        params.append(data_a)
        filters['data_a'] = data_a
    
    # Aggiungi ordinamento
    query += " ORDER BY qi.data_invio DESC"
    
    # Esegui query per conteggio totale
    count_query = f"SELECT COUNT(*) FROM ({query}) as count_query"
    cur.execute(count_query, params)
    total_count = cur.fetchone()[0]
    
    # Aggiungi paginazione
    query += " LIMIT %s OFFSET %s"
    offset = (page - 1) * per_page
    params.extend([per_page, offset])
    
    # Esegui query principale
    cur.execute(query, params)
    history = cur.fetchall()
    
    # Ottieni clienti e template per i filtri (solo per l'utente corrente)
    cur.execute("SELECT id, nome, cognome FROM clienti_assicurativi WHERE user_id = %s OR user_id IS NULL ORDER BY cognome, nome",
                (session.get('user_id'),))
    clienti = cur.fetchall()
    
    cur.execute("SELECT id, nome FROM template_pdf ORDER BY nome")
    templates = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Calcola informazioni di paginazione
    total_pages = (total_count + per_page - 1) // per_page
    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'total_count': total_count,
        'per_page': per_page
    }
    
    return render_template('tools/consulenze/history.html',
                          history=history,
                          clienti=clienti,
                          templates=templates,
                          filters=filters,
                          pagination=pagination if total_pages > 1 else None)

@app.route('/consulenze/export-history')
@login_required
@has_package('manage_consulenze')
def export_history():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Ottieni parametri di filtro
    cliente_id = request.args.get('cliente')
    template_id = request.args.get('template')
    data_da = request.args.get('data_da')
    data_a = request.args.get('data_a')
    
    # Costruisci query con filtri
    query = """
        SELECT qi.data_invio, c.nome as cliente_nome, c.cognome as cliente_cognome, 
               c.email, t.nome as template_nome, qi.flags, qi.filename
        FROM questionari_inviati qi
        JOIN clienti_assicurativi c ON qi.cliente_id = c.id
        JOIN template_pdf t ON qi.template_id = t.id
        WHERE 1=1
    """
    
    params = []
    
    if cliente_id:
        query += " AND qi.cliente_id = %s"
        params.append(cliente_id)
    
    if template_id:
        query += " AND qi.template_id = %s"
        params.append(template_id)
    
    if data_da:
        query += " AND qi.data_invio >= %s"
        params.append(data_da)
    
    if data_a:
        query += " AND qi.data_invio <= %s"
        params.append(data_a)
    
    # Aggiungi ordinamento
    query += " ORDER BY qi.data_invio DESC"
    
    # Esegui query
    cur.execute(query, params)
    results = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Crea CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Intestazioni
    writer.writerow(['Data Invio', 'Nome', 'Cognome', 'Email', 'Template', 'Flags', 'Filename'])
    
    # Dati
    for row in results:
        writer.writerow([
            row['data_invio'].strftime('%d/%m/%Y %H:%M'),
            row['cliente_nome'],
            row['cliente_cognome'],
            row['email'],
            row['template_nome'],
            ', '.join(row['flags']) if row['flags'] else '',
            row['filename']
        ])
    
    # Prepara la risposta
    output.seek(0)
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    
    return jsonify({
        'success': True,
        'data': output.getvalue(),
        'filename': f'storico_invii_{timestamp}.csv'
    })

@app.route('/consulenze/anagrafica', methods=['GET', 'POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_anagrafica():
    if request.method == 'POST':
        # Raccolta dati dal form
        nome = request.form['nome']
        cognome = request.form['cognome']
        data_nascita = request.form['data_nascita'] if request.form['data_nascita'] else None
        luogo_nascita = request.form['luogo_nascita']
        codice_fiscale = request.form['codice_fiscale']
        partita_iva = request.form.get('partita_iva', '')
        email = request.form['email']
        pec = request.form.get('pec', '')
        codice_univoco = request.form.get('codice_univoco', '')
        cellulare = request.form['cellulare']
        attivita = request.form.get('attivita', '')
        data_inizio_attivita = request.form.get('data_inizio_attivita') if request.form.get('data_inizio_attivita') else None
        iscrizione_albo_data = request.form.get('iscrizione_albo_data') if request.form.get('iscrizione_albo_data') else None
        iscrizione_albo_numero = request.form.get('iscrizione_albo_numero', '')
        residenza = request.form.get('residenza', '')
        domicilio_fiscale = request.form.get('domicilio_fiscale', '')
        ubicazione_studio = request.form.get('ubicazione_studio', '')
        
        # Gestisci i campi numerici
        fatturato_2024 = request.form.get('fatturato_2024')
        if fatturato_2024 == '' or fatturato_2024 is None:
            fatturato_2024 = None
        else:
            try:
                fatturato_2024 = float(fatturato_2024)
            except ValueError:
                fatturato_2024 = 0
                
        stima_2025 = request.form.get('stima_2025')
        if stima_2025 == '' or stima_2025 is None:
            stima_2025 = None
        else:
            try:
                stima_2025 = float(stima_2025)
            except ValueError:
                stima_2025 = 0
        
        # Flag
        dipendenti = 'dipendenti' in request.form
        addetti = 'addetti' in request.form
        subappaltatori = 'subappaltatori' in request.form
        
        # Nuovi campi polizza
        compagnia_assicurativa = request.form.get('compagnia_assicurativa', '')
        numero_polizza = request.form.get('numero_polizza', '')
        tipo_polizza = request.form.get('tipo_polizza', '')
        data_scadenza_polizza = request.form.get('data_scadenza_polizza') if request.form.get('data_scadenza_polizza') else None
        
        # Gestione upload file
        documento_fronte = None
        documento_retro = None
        polizza_precedente = None
        
        # Crea la cartella del cliente
        nome_cliente = secure_filename(f"{nome}_{cognome}_{codice_fiscale}")
        cliente_folder = os.path.join(app.config['UPLOAD_FOLDER'], nome_cliente)
        if not os.path.exists(cliente_folder):
            os.makedirs(cliente_folder)
        
        if 'documento_fronte' in request.files and request.files['documento_fronte'].filename:
            file = request.files['documento_fronte']
            filename = secure_filename(f"documento_fronte_{uuid.uuid4()}.{file.filename.split('.')[-1]}")
            file_path = os.path.join(cliente_folder, filename)
            file.save(file_path)
            documento_fronte = f"{nome_cliente}/{filename}"
            
        if 'documento_retro' in request.files and request.files['documento_retro'].filename:
            file = request.files['documento_retro']
            filename = secure_filename(f"documento_retro_{uuid.uuid4()}.{file.filename.split('.')[-1]}")
            file_path = os.path.join(cliente_folder, filename)
            file.save(file_path)
            documento_retro = f"{nome_cliente}/{filename}"
            
        if 'polizza_precedente' in request.files and request.files['polizza_precedente'].filename:
            file = request.files['polizza_precedente']
            filename = secure_filename(f"polizza_precedente_{uuid.uuid4()}.{file.filename.split('.')[-1]}")
            file_path = os.path.join(cliente_folder, filename)
            file.save(file_path)
            polizza_precedente = f"{nome_cliente}/{filename}"
        
        # Salvataggio nel database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO clienti_assicurativi (
                nome, cognome, data_nascita, luogo_nascita, codice_fiscale, partita_iva,
                email, pec, codice_univoco, cellulare, attivita, data_inizio_attivita,
                iscrizione_albo_data, iscrizione_albo_numero, residenza, domicilio_fiscale,
                ubicazione_studio, fatturato_2024, stima_2025, dipendenti, addetti,
                subappaltatori, documento_fronte, documento_retro, polizza_precedente,
                questionario_inviato, nome_questionario_inviato, user_id,
                compagnia_assicurativa, numero_polizza, tipo_polizza, data_scadenza_polizza
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            nome, cognome, data_nascita, luogo_nascita, codice_fiscale, partita_iva,
            email, pec, codice_univoco, cellulare, attivita, data_inizio_attivita,
            iscrizione_albo_data, iscrizione_albo_numero, residenza, domicilio_fiscale,
            ubicazione_studio, fatturato_2024, stima_2025, dipendenti, addetti,
            subappaltatori, documento_fronte, documento_retro, polizza_precedente,
            False, None, session.get('user_id'),
            compagnia_assicurativa, numero_polizza, tipo_polizza, data_scadenza_polizza
        ))
        
        cliente_id = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        flash('Cliente aggiunto con successo!', 'success')
        return redirect(url_for('consulenze_panoramica'))
    
    return render_template('tools/consulenze/anagrafica.html')

@app.route('/consulenze/panoramica')
@login_required
@has_package('manage_consulenze')
def consulenze_panoramica():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Filtri
    filters = {}
    where_clauses = []
    params = []
    
    for key, value in request.args.items():
        if value and key != 'questionario_inviato':
            filters[key] = value
            where_clauses.append(f"{key} ILIKE %s")
            params.append(f"%{value}%")
    
    if 'questionario_inviato' in request.args:
        filters['questionario_inviato'] = request.args.get('questionario_inviato')
        where_clauses.append("questionario_inviato = %s")
        params.append(request.args.get('questionario_inviato') == 'true')
    
    # Aggiungi filtro per user_id
    where_clauses.append("(user_id = %s OR user_id IS NULL)")
    params.append(session.get('user_id'))
    
    query = "SELECT * FROM clienti_assicurativi"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY cognome, nome"
    
    cur.execute(query, params)
    clienti = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/panoramica.html', clienti=clienti, filters=filters)

@app.route('/consulenze/cliente/upload-document', methods=['POST'])
@login_required
@has_package('manage_consulenze')
@csrf.exempt  # Esenzione CSRF per upload file
def upload_cliente_document():
    if 'document_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nessun file caricato'}), 400
    
    file = request.files['document_file']
    cliente_id = request.form.get('cliente_id')
    document_type = request.form.get('document_type')
    
    if not cliente_id or not document_type:
        return jsonify({'success': False, 'message': 'Parametri mancanti'}), 400
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nessun file selezionato'}), 400
    
    # Verifica che l'utente abbia accesso a questo cliente
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("SELECT user_id FROM clienti_assicurativi WHERE id = %s", (cliente_id,))
        cliente = cur.fetchone()
        
        if not cliente:
            return jsonify({'success': False, 'message': 'Cliente non trovato'}), 404
        
        if cliente['user_id'] and cliente['user_id'] != session.get('user_id'):
            return jsonify({'success': False, 'message': 'Non hai accesso a questo cliente'}), 403
        
        # Ottieni nome e cognome del cliente per creare la cartella
        cur.execute("SELECT nome, cognome FROM clienti_assicurativi WHERE id = %s", (cliente_id,))
        cliente_info = cur.fetchone()
        nome_cliente = secure_filename(f"{cliente_info['nome']}_{cliente_info['cognome']}_{cliente_id}")
        
        # Crea la cartella del cliente se non esiste
        cliente_folder = os.path.join(app.config['UPLOAD_FOLDER'], nome_cliente)
        if not os.path.exists(cliente_folder):
            os.makedirs(cliente_folder)
        
        # Salva il file nella cartella del cliente
        filename = secure_filename(f"{document_type}_{uuid.uuid4()}_{file.filename}")
        file_path = os.path.join(cliente_folder, filename)
        file.save(file_path)
        
        # Percorso relativo per il database (nome_cliente/filename)
        db_path = f"{nome_cliente}/{filename}"
        
        # Aggiorna il campo nel database
        cur.execute(f"UPDATE clienti_assicurativi SET {document_type} = %s WHERE id = %s", (db_path, cliente_id))
        
        return jsonify({'success': True, 'message': 'Documento caricato con successo', 'filename': filename})
    except Exception as e:
        app.logger.error(f"Errore durante il caricamento del documento: {str(e)}")
        return jsonify({'success': False, 'message': f'Errore durante il caricamento: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/consulenze/cliente/<int:cliente_id>/details', methods=['GET'])
@login_required
@has_package('manage_consulenze')
def get_cliente_details(cliente_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Verifica che l'utente abbia accesso a questo cliente
        cur.execute("SELECT * FROM clienti_assicurativi WHERE id = %s AND (user_id = %s OR user_id IS NULL)", 
                   (cliente_id, session.get('user_id')))
        cliente = cur.fetchone()
        
        if not cliente:
            return jsonify({'success': False, 'message': 'Cliente non trovato'}), 404
        
        # Converti il record in un dizionario
        cliente_dict = dict(cliente)
        
        # Converti le date in stringhe ISO per JSON
        for key, value in cliente_dict.items():
            if isinstance(value, datetime.date) or isinstance(value, datetime.datetime):
                cliente_dict[key] = value.isoformat()
        
        return jsonify({'success': True, 'cliente': cliente_dict})
    except Exception as e:
        app.logger.error(f"Errore durante il recupero dei dettagli del cliente: {str(e)}")
        return jsonify({'success': False, 'message': f'Errore durante il recupero dei dettagli: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/consulenze/cliente/<int:cliente_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@has_package('manage_consulenze')
def consulenze_cliente(cliente_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'DELETE':
        # Verifica che il cliente appartenga all'utente corrente
        cur.execute("SELECT user_id FROM clienti_assicurativi WHERE id = %s", (cliente_id,))
        result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Cliente non trovato'}), 404
            
        if result['user_id'] and result['user_id'] != session.get('user_id'):
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Non hai i permessi per eliminare questo cliente'}), 403
            
        cur.execute("DELETE FROM clienti_assicurativi WHERE id = %s", (cliente_id,))
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Cliente eliminato con successo'})
    
    if request.method == 'PUT':
        data = request.json
        field = data.get('field')
        value = data.get('value')
        
        if field and value is not None:
            # Verifica che il cliente appartenga all'utente corrente
            cur.execute("SELECT user_id FROM clienti_assicurativi WHERE id = %s", (cliente_id,))
            result = cur.fetchone()
            
            if not result:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'message': 'Cliente non trovato'}), 404
                
            if result['user_id'] and result['user_id'] != session.get('user_id'):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'message': 'Non hai i permessi per modificare questo cliente'}), 403
                
            # Gestisci i campi di tipo date
            if field in ['data_nascita', 'data_inizio_attivita', 'iscrizione_albo_data'] and value == '':
                value = None
                
            # Gestisci i campi di tipo numeric
            if field in ['fatturato_2024', 'stima_2025'] and (value == '' or value is None):
                value = None
            elif field in ['fatturato_2024', 'stima_2025']:
                try:
                    value = float(value)
                except ValueError:
                    value = 0
                
            cur.execute(f"UPDATE clienti_assicurativi SET {field} = %s WHERE id = %s", (value, cliente_id))
            cur.close()
            conn.close()
            return jsonify({'success': True, 'message': 'Campo aggiornato con successo'})
        else:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Dati mancanti'}), 400
    
    cur.execute("SELECT * FROM clienti_assicurativi WHERE id = %s AND (user_id = %s OR user_id IS NULL)", 
              (cliente_id, session.get('user_id')))
    cliente = cur.fetchone()
    cur.close()
    conn.close()
    
    if not cliente:
        flash('Cliente non trovato o non hai i permessi per visualizzarlo.', 'danger')
        return redirect(url_for('consulenze_panoramica'))
    
    return jsonify(dict(cliente))

@app.route('/consulenze/questionari', methods=['GET', 'POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_questionari():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Get all clients for dropdown (only for current user)
    cur.execute("SELECT id, nome, cognome, codice_fiscale FROM clienti_assicurativi WHERE user_id = %s OR user_id IS NULL ORDER BY cognome, nome", 
                (session.get('user_id'),))
    clienti = cur.fetchall()
    
    # Get all PDF templates
    cur.execute("SELECT * FROM template_pdf")
    templates = cur.fetchall()
    
    # Get all email templates
    cur.execute("SELECT * FROM email_texts ORDER BY nome")
    email_templates = cur.fetchall()
    
    # Get sent questionnaires for current user
    cur.execute("""
        SELECT qi.*, c.nome as cliente_nome, c.cognome as cliente_cognome, 
               c.email as cliente_email, c.codice_fiscale, t.nome as template_nome,
               et.nome as email_template_nome
        FROM questionari_inviati qi
        JOIN clienti_assicurativi c ON qi.cliente_id = c.id
        JOIN template_pdf t ON qi.template_id = t.id
        LEFT JOIN email_texts et ON qi.email_text_id = et.id
        WHERE qi.user_id = %s OR qi.user_id IS NULL
        ORDER BY qi.data_invio DESC
    """, (session.get('user_id'),))
    questionari_inviati = cur.fetchall()
    
    if request.method == 'POST':
        cliente_id = request.form['cliente_id']
        template_id = request.form['template_id']
        email_template_id = request.form.get('email_template_id')
        flags = request.form.getlist('flags')
        
        # Get client and template info (solo per l'utente corrente)
        cur.execute("SELECT * FROM clienti_assicurativi WHERE id = %s AND (user_id = %s OR user_id IS NULL)", 
                   (cliente_id, session.get('user_id')))
        cliente = cur.fetchone()
        
        cur.execute("SELECT * FROM template_pdf WHERE id = %s", (template_id,))
        template = cur.fetchone()
        
        if cliente and template:
            # Generate PDF with PyPDF2
            template_path = os.path.join(app.config['PDF_TEMPLATES'], template['filename'])
            output_filename = f"{cliente['codice_fiscale']}_{template['nome']}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            output_path = os.path.join(app.config['PDF_GENERATI'], output_filename)
            
            # Fill PDF form fields
            reader = PyPDF2.PdfReader(template_path)
            writer = PyPDF2.PdfWriter()
            
            # Aggiungi tutte le pagine del PDF
            for page in reader.pages:
                writer.add_page(page)
            
            # Funzioni di supporto per estrarre informazioni
            def determina_sesso_da_cf(cf):
                """Determina il sesso dal codice fiscale"""
                if not cf or len(cf) < 12:
                    return ""
                # Il 15° carattere del CF indica il sesso: dispari per M, pari per F
                try:
                    giorno_nascita = int(cf[9:11])
                    return "F" if giorno_nascita > 40 else "M"
                except:
                    return ""
            
            def estrai_provincia_da_luogo(luogo):
                """Estrae la provincia dal luogo di nascita"""
                if not luogo:
                    return ""
                
                # Formato tipico: "Roma (RM)" o "Roma"
                import re
                
                # Cerca la provincia tra parentesi (es. (RM))
                prov_match = re.search(r'\(([A-Z]{2})\)', luogo)
                if prov_match:
                    return prov_match.group(1)
                
                # Se non c'è la provincia tra parentesi, prova a estrarla dal nome della città
                # Dizionario delle principali città italiane e relative province
                citta_province = {
                    "roma": "RM", "milano": "MI", "napoli": "NA", "torino": "TO", "palermo": "PA",
                    "genova": "GE", "bologna": "BO", "firenze": "FI", "bari": "BA", "catania": "CT",
                    "venezia": "VE", "verona": "VR", "messina": "ME", "padova": "PD", "trieste": "TS",
                    "brescia": "BS", "parma": "PR", "taranto": "TA", "prato": "PO", "modena": "MO",
                    "reggio calabria": "RC", "reggio emilia": "RE", "perugia": "PG", "livorno": "LI",
                    "cagliari": "CA", "foggia": "FG", "rimini": "RN", "salerno": "SA", "ferrara": "FE",
                    "sassari": "SS", "latina": "LT", "giugliano in campania": "NA", "monza": "MB",
                    "siracusa": "SR", "pescara": "PE", "bergamo": "BG", "forlì": "FC", "trento": "TN",
                    "vicenza": "VI", "terni": "TR", "bolzano": "BZ", "novara": "NO", "piacenza": "PC",
                    "ancona": "AN", "andria": "BT", "arezzo": "AR", "udine": "UD", "cesena": "FC",
                    "lecce": "LE", "pesaro": "PU", "barletta": "BT", "alessandria": "AL", "catanzaro": "CZ"
                }
                
                # Normalizza il nome della città (minuscolo e senza spazi extra)
                citta_norm = re.sub(r'\s+', ' ', luogo.lower().strip())
                
                # Cerca la città nel dizionario
                for citta, prov in citta_province.items():
                    if citta in citta_norm or citta_norm in citta:
                        return prov
                
                return ""
            
            def estrai_info_da_indirizzo(indirizzo):
                """Estrae comune, CAP e provincia da un indirizzo"""
                if not indirizzo:
                    return {"comune": "", "cap": "", "provincia": ""}
                
                # Formato tipico: Via Roma 1, 00100 Roma (RM)
                parti = indirizzo.split(',')
                
                comune = ""
                cap = ""
                provincia = ""
                
                if len(parti) > 1:
                    # Prova a estrarre CAP e comune dalla seconda parte
                    seconda_parte = parti[1].strip()
                    
                    # Cerca il CAP (5 cifre consecutive)
                    import re
                    cap_match = re.search(r'\b\d{5}\b', seconda_parte)
                    if cap_match:
                        cap = cap_match.group(0)
                    
                    # Cerca la provincia tra parentesi (es. (RM))
                    prov_match = re.search(r'\(([A-Z]{2})\)', seconda_parte)
                    if prov_match:
                        provincia = prov_match.group(1)
                    
                    # Estrai il comune rimuovendo CAP e provincia
                    comune_temp = seconda_parte
                    if cap:
                        comune_temp = comune_temp.replace(cap, "")
                    if provincia:
                        comune_temp = comune_temp.replace(f"({provincia})", "")
                    comune = comune_temp.strip()
                
                return {"comune": comune, "cap": cap, "provincia": provincia}
            
            # Estrai informazioni dagli indirizzi
            info_residenza = estrai_info_da_indirizzo(cliente['residenza'])
            info_domicilio = estrai_info_da_indirizzo(cliente['domicilio_fiscale'])
            info_studio = estrai_info_da_indirizzo(cliente['ubicazione_studio'])
            
            # Determina il sesso dal codice fiscale
            sesso = determina_sesso_da_cf(cliente['codice_fiscale'])
            
            # Estrai la provincia dal luogo di nascita
            provincia_nascita = estrai_provincia_da_luogo(cliente['luogo_nascita'])
            
            # Update form fields with all available client data
            form_data = {
                # Dati personali
                "nome": cliente['nome'],
                "cognome": cliente['cognome'],
                "cf": cliente['codice_fiscale'],
                "data_nascita": cliente['data_nascita'].strftime('%d/%m/%Y') if cliente['data_nascita'] else "",
                "luogo_nascita": cliente['luogo_nascita'] or "",
                "sesso": sesso,  # Determinato automaticamente dal CF
                
                # Contatti personali
                "email": cliente['email'] or "",
                "pec": cliente['pec'] or "",
                "telefono": "",  # Non presente nel database
                "cellulare": cliente['cellulare'] or "",
                
                # Dati professionali
                "att_prof": cliente['attivita'] or "",
                "ambito_prof": "",  # Non presente nel database
                "univoco": cliente['codice_univoco'] or "",
                
                # Dati aziendali
                "denominazione": "",  # Non presente nel database
                "piva_azienda": cliente['partita_iva'] or "",
                
                # Indirizzo residenza
                "indirizzo_residenza": cliente['residenza'] or "",
                "comune_residenza": info_residenza["comune"],
                "cap_residenza": info_residenza["cap"],
                "prov_residenza": info_residenza["provincia"],
                
                # Indirizzo domicilio fiscale
                "indirizzo_domicilio": cliente['domicilio_fiscale'] or "",
                "comune_domicilio": info_domicilio["comune"],
                "cap_domicilio": info_domicilio["cap"],
                "prov_domicilio": info_domicilio["provincia"],
                
                # Indirizzo studio/azienda
                "indirizzo_azienda": cliente['ubicazione_studio'] or "",
                "citta_azienda": info_studio["comune"],
                "cap_azienda": info_studio["cap"],
                "prov_azienda": info_studio["provincia"],
                
                # Data compilazione
                "data": datetime.datetime.now().strftime('%d/%m/%Y'),
                
                # Altri campi che potrebbero essere presenti nel PDF
                "prov_nascita": provincia_nascita,  # Estratto dal luogo di nascita
                "nazione": "ITALIA",
                
                # Campi aziendali aggiuntivi
                "telefono_azienda": "",
                "cellulare_azienda": cliente['cellulare'] or "",
                "email_azienda": cliente['email'] or "",
                "pec_azienda": cliente['pec'] or "",
                "attivita_azienda": cliente['attivita'] or "",
                "ambito_azienda": "",
                "univoco_azienda": cliente['codice_univoco'] or ""
            }
            
            # Aggiungi mappature alternative per i campi del PDF
            # Alcuni PDF potrebbero usare nomi di campi diversi per gli stessi dati
            alternative_mappings = {
                # Dati personali
                "cognome": cliente['cognome'],
                "nome": cliente['nome'],
                "codice_fiscale": cliente['codice_fiscale'],
                "cf": cliente['codice_fiscale'],
                "data_di_nascita": cliente['data_nascita'].strftime('%d/%m/%Y') if cliente['data_nascita'] else "",
                "luogo_di_nascita": cliente['luogo_nascita'] or "",
                "sesso": sesso,
                "m": "X" if sesso == "M" else "",
                "f": "X" if sesso == "F" else "",
                
                # Indirizzi
                "residenza": cliente['residenza'] or "",
                "domicilio": cliente['domicilio_fiscale'] or "",
                "studio": cliente['ubicazione_studio'] or "",
                
                # Contatti
                "telefono_cellulare": cliente['cellulare'] or "",
                "mail": cliente['email'] or "",
                "email_pec": cliente['pec'] or "",
                
                # Dati professionali
                "partita_iva": cliente['partita_iva'] or "",
                "piva": cliente['partita_iva'] or "",
                "attivita": cliente['attivita'] or "",
                "professione": cliente['attivita'] or "",
                "codice_univoco": cliente['codice_univoco'] or "",
                
                # Date
                "data_compilazione": datetime.datetime.now().strftime('%d/%m/%Y'),
            }
            
            # Aggiungi le mappature alternative al form_data
            for key, value in alternative_mappings.items():
                if value and key not in form_data:
                    form_data[key] = value
            
            # Rimuovi i campi vuoti per evitare errori
            form_data = {k: v for k, v in form_data.items() if v}
            
            # Aggiorna i campi del PDF in tutte le pagine
            for page_num in range(len(writer.pages)):
                try:
                    writer.update_page_form_field_values(writer.pages[page_num], form_data)
                except Exception as e:
                    app.logger.warning(f"Errore nell'aggiornamento dei campi nella pagina {page_num+1}: {str(e)}")
            
            # Gestione speciale per i campi checkbox del sesso (se presenti)
            if sesso:
                try:
                    if sesso == "M":
                        writer.update_page_form_field_values(writer.pages[0], {"sesso_m": True, "sesso_f": False})
                    else:
                        writer.update_page_form_field_values(writer.pages[0], {"sesso_m": False, "sesso_f": True})
                except:
                    pass
            
            # Add flags - applica i flag a tutte le pagine
            for i, flag in enumerate(flags, 1):
                if i <= 10:  # Aumentato a 10 flag massimi
                    flag_data = {f"flag{i}": "Yes"}
                    # Prova ad applicare il flag a tutte le pagine
                    for page_num in range(len(writer.pages)):
                        try:
                            writer.update_page_form_field_values(
                                writer.pages[page_num], flag_data
                            )
                        except:
                            # Se il campo non esiste in questa pagina, ignora l'errore
                            pass
            
            # Save the filled PDF
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            
            # If "Invia questionario" was clicked
            if 'send_email' in request.form:
                # Get SMTP configuration
                cur.execute("SELECT * FROM config_email LIMIT 1")
                smtp_config = cur.fetchone()
                
                if smtp_config:
                    # Get email template
                    email_text = ""
                    if email_template_id:
                        cur.execute("SELECT testo FROM email_texts WHERE id = %s", (email_template_id,))
                        email_template = cur.fetchone()
                        if email_template:
                            email_text = email_template['testo']
                    
                    # If no template selected or found, use default
                    if not email_text:
                        cur.execute("SELECT testo FROM email_texts WHERE nome = 'Default' LIMIT 1")
                        default_template = cur.fetchone()
                        if default_template:
                            email_text = default_template['testo']
                        else:
                            email_text = "Gentile {nome} {cognome},\n\nIn allegato il questionario assicurativo da compilare.\n\nCordiali saluti,\nIl tuo Consulente Assicurativo"
                    
                    # Replace placeholders with client data
                    email_text = email_text.replace('{nome}', cliente['nome'] or '')
                    email_text = email_text.replace('{cognome}', cliente['cognome'] or '')
                    email_text = email_text.replace('{email}', cliente['email'] or '')
                    email_text = email_text.replace('{codice_fiscale}', cliente['codice_fiscale'] or '')
                    email_text = email_text.replace('{data_invio}', datetime.datetime.now().strftime('%d/%m/%Y'))
                    email_text = email_text.replace('{mittente}', smtp_config['email'] or 'Consulente Assicurativo')
                    
                    # Send email
                    msg = EmailMessage()
                    msg['Subject'] = f"Questionario Assicurativo - {cliente['nome']} {cliente['cognome']}"
                    msg['From'] = smtp_config['email']
                    msg['To'] = cliente['email']
                    msg.set_content(email_text)
                    
                    # Attach PDF
                    with open(output_path, 'rb') as f:
                        file_data = f.read()
                    msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=output_filename)
                    
                    # Send email
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(smtp_config['smtp_server'], smtp_config['porta'], context=context) as server:
                        server.login(smtp_config['email'], smtp_config['password'])
                        server.send_message(msg)
                    
                    # Update client record
                    cur.execute(
                        "UPDATE clienti_assicurativi SET questionario_inviato = TRUE, nome_questionario_inviato = %s WHERE id = %s",
                        (output_filename, cliente_id)
                    )
                    
                    # Register the sent questionnaire
                    cur.execute(
                        """INSERT INTO questionari_inviati 
                           (cliente_id, template_id, email_text_id, filename, flags, data_invio, user_id) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (cliente_id, template_id, email_template_id, output_filename, 
                         ','.join(flags) if flags else None, datetime.datetime.now(), session.get('user_id'))
                    )
                    
                    # Commit the transaction
                    conn.commit()
                    
                    flash('Email inviata con successo!', 'success')
                    
                    # Return success response with email sent info
                    return jsonify({
                        'success': True,
                        'pdf_path': f"/pdf_preview/{output_filename}",
                        'pdf_name': output_filename,
                        'email_sent': True,
                        'message': 'PDF generato e questionario inviato con successo!'
                    })
                else:
                    flash('Configurazione SMTP non trovata. Configura prima le impostazioni email.', 'danger')
                    return jsonify({
                        'success': False,
                        'message': 'Configurazione SMTP non trovata. Configura prima le impostazioni email.'
                    })
            
            # Return PDF path for preview (only PDF generation, no email)
            return jsonify({
                'success': True,
                'pdf_path': f"/pdf_preview/{output_filename}",
                'pdf_name': output_filename,
                'email_sent': False,
                'message': 'PDF generato con successo!'
            })
        
        else:
            return jsonify({'success': False, 'message': 'Cliente o template non trovato'}), 404
    
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/questionari.html', 
                          clienti=clienti, 
                          templates=templates, 
                          email_templates=email_templates,
                          questionari_inviati=questionari_inviati)

@app.route('/consulenze/questionari/resend/<int:questionario_id>', methods=['POST'])
@login_required
@has_package('manage_consulenze')
def resend_questionario(questionario_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get questionnaire details
        cur.execute("""
            SELECT qi.*, c.nome as cliente_nome, c.cognome as cliente_cognome, 
                   c.email as cliente_email, t.nome as template_nome,
                   et.testo as email_text
            FROM questionari_inviati qi
            JOIN clienti_assicurativi c ON qi.cliente_id = c.id
            JOIN template_pdf t ON qi.template_id = t.id
            LEFT JOIN email_texts et ON qi.email_text_id = et.id
            WHERE qi.id = %s AND (qi.user_id = %s OR qi.user_id IS NULL)
        """, (questionario_id, session.get('user_id')))
        
        questionario = cur.fetchone()
        
        if not questionario:
            return jsonify({'success': False, 'message': 'Questionario non trovato'}), 404
        
        # Get SMTP configuration
        cur.execute("SELECT * FROM config_email LIMIT 1")
        smtp_config = cur.fetchone()
        
        if not smtp_config:
            return jsonify({'success': False, 'message': 'Configurazione SMTP non trovata'}), 400
        
        # Prepare email text
        email_text = questionario['email_text'] or "Gentile {nome} {cognome},\n\nIn allegato il questionario assicurativo da compilare.\n\nCordiali saluti,\nIl tuo Consulente Assicurativo"
        
        # Replace placeholders
        email_text = email_text.replace('{nome}', questionario['cliente_nome'] or '')
        email_text = email_text.replace('{cognome}', questionario['cliente_cognome'] or '')
        email_text = email_text.replace('{email}', questionario['cliente_email'] or '')
        email_text = email_text.replace('{data_invio}', datetime.datetime.now().strftime('%d/%m/%Y'))
        email_text = email_text.replace('{mittente}', smtp_config['email'] or 'Consulente Assicurativo')
        
        # Check if PDF file exists
        pdf_path = os.path.join(app.config['PDF_GENERATI'], questionario['filename'])
        if not os.path.exists(pdf_path):
            return jsonify({'success': False, 'message': 'File PDF non trovato'}), 404
        
        # Send email
        msg = EmailMessage()
        msg['Subject'] = f"Questionario Assicurativo - {questionario['cliente_nome']} {questionario['cliente_cognome']}"
        msg['From'] = smtp_config['email']
        msg['To'] = questionario['cliente_email']
        msg.set_content(email_text)
        
        # Attach PDF
        with open(pdf_path, 'rb') as f:
            file_data = f.read()
        msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=questionario['filename'])
        
        # Send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_config['smtp_server'], smtp_config['porta'], context=context) as server:
            server.login(smtp_config['email'], smtp_config['password'])
            server.send_message(msg)
        
        # Register the resend
        cur.execute(
            """INSERT INTO questionari_inviati 
               (cliente_id, template_id, email_text_id, filename, flags, data_invio, user_id) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (questionario['cliente_id'], questionario['template_id'], questionario['email_text_id'], 
             questionario['filename'], questionario['flags'], datetime.datetime.now(), session.get('user_id'))
        )
        
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Questionario reinviato con successo!'
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Errore durante il reinvio: {str(e)}'}), 500
    
    finally:
        cur.close()
        conn.close()

@app.route('/consulenze/email', methods=['GET', 'POST'])
@login_required
@has_package('manage_consulenze')
def consulenze_email():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Get current SMTP configuration
    cur.execute("SELECT * FROM config_email LIMIT 1")
    config = cur.fetchone()
    
    if request.method == 'POST':
        smtp_server = request.form['smtp_server']
        porta = request.form['porta']
        email = request.form['email']
        password = request.form['password']
        testo = request.form['testo']
        
        if config:
            # Update existing configuration
            cur.execute(
                "UPDATE config_email SET smtp_server = %s, porta = %s, email = %s, password = %s, testo = %s WHERE id = %s",
                (smtp_server, porta, email, password, testo, config['id'])
            )
        else:
            # Create new configuration
            cur.execute(
                "INSERT INTO config_email (smtp_server, porta, email, password, testo) VALUES (%s, %s, %s, %s, %s)",
                (smtp_server, porta, email, password, testo)
            )
        
        flash('Configurazione SMTP salvata con successo!', 'success')
        
        # Refresh configuration
        cur.execute("SELECT * FROM config_email LIMIT 1")
        config = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/email.html', config=config)

@app.route('/pdf_preview/<filename>')
@login_required
@has_package('manage_consulenze')
def pdf_preview(filename):
    return send_from_directory(app.config['PDF_GENERATI'], filename)

@app.route('/upload/<filename>')
@login_required
@has_package('manage_consulenze')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/consulenze/automazioni')
@login_required
@has_package('manage_consulenze')
def consulenze_automazioni():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Recupera tutte le automazioni dell'utente
    cur.execute("""
        SELECT a.*, 
               COUNT(CASE WHEN ae.stato = 'attivo' THEN 1 END) as invii_attivi,
               COUNT(ae.id) as invii_totali,
               MAX(ae.prossimo_invio) as prossimo_invio_globale
        FROM automazioni a
        LEFT JOIN automazioni_esecuzioni ae ON a.id = ae.automazione_id
        WHERE a.user_id = %s
        GROUP BY a.id
        ORDER BY a.created_at DESC
    """, (session['user_id'],))
    automazioni = cur.fetchall()
    
    # Recupera i template PDF disponibili per l'utente
    cur.execute("SELECT * FROM template_pdf WHERE user_id = %s ORDER BY nome", (session['user_id'],))
    templates = cur.fetchall()
    
    # Recupera i template email disponibili per l'utente
    cur.execute("SELECT * FROM email_texts WHERE user_id = %s ORDER BY nome", (session['user_id'],))
    email_templates = cur.fetchall()
    
    # Recupera i clienti per il dropdown - usa DictCursor per avere i dati come dizionari
    cur.execute("""
        SELECT id, nome, cognome, email, codice_fiscale 
        FROM clienti_assicurativi 
        WHERE user_id = %s
        ORDER BY cognome, nome
    """, (session['user_id'],))
    clienti = cur.fetchall()
    
    # Debug: stampa i clienti trovati nella route principale
    print(f"DEBUG MAIN: Trovati {len(clienti)} clienti per user_id {session['user_id']}")
    for i, cliente in enumerate(clienti):
        print(f"DEBUG MAIN: Cliente {i+1} RAW: {cliente}")
        print(f"DEBUG MAIN: Cliente {i+1} TYPE: {type(cliente)}")
        if hasattr(cliente, 'keys'):
            print(f"DEBUG MAIN: Cliente {i+1} KEYS: {list(cliente.keys())}")
        else:
            print(f"DEBUG MAIN: Cliente {i+1} è una tupla, non un dizionario")
    
    # Se non ci sono clienti con user_id specifico, prova anche con user_id NULL
    if len(clienti) == 0:
        print("DEBUG MAIN: Nessun cliente con user_id specifico, provo anche con user_id NULL")
        cur.execute("""
            SELECT id, nome, cognome, email, codice_fiscale 
            FROM clienti_assicurativi 
            WHERE user_id IS NULL
            ORDER BY cognome, nome
        """)
        clienti_null = cur.fetchall()
        print(f"DEBUG MAIN: Trovati {len(clienti_null)} clienti con user_id NULL")
        clienti = clienti_null
    
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/automazioni.html', 
                         automazioni=automazioni, 
                         templates=templates,
                         email_templates=email_templates,
                         clienti=clienti)

@app.route('/consulenze/automazioni/crea')
@login_required
@has_package('manage_consulenze')
def consulenze_automazioni_crea():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Recupera i template PDF disponibili per l'utente
    cur.execute("SELECT * FROM template_pdf WHERE user_id = %s ORDER BY nome", (session['user_id'],))
    templates = cur.fetchall()
    
    # Recupera i template email disponibili per l'utente
    cur.execute("SELECT * FROM email_texts WHERE user_id = %s ORDER BY nome", (session['user_id'],))
    email_templates = cur.fetchall()
    
    # Recupera i clienti per il dropdown
    cur.execute("""
        SELECT id, nome, cognome, email, codice_fiscale 
        FROM clienti_assicurativi 
        WHERE user_id = %s OR user_id IS NULL
        ORDER BY cognome, nome
    """, (session['user_id'],))
    clienti = cur.fetchall()
    
    # Debug: stampa i clienti trovati
    print(f"DEBUG: Trovati {len(clienti)} clienti per user_id {session['user_id']}")
    for i, cliente in enumerate(clienti):
        print(f"DEBUG: Cliente {i+1} RAW: {cliente}")
        print(f"DEBUG: Cliente {i+1} FIELDS: ID={cliente[0]}, NOME={cliente[1]}, COGNOME={cliente[2]}, EMAIL={cliente[3]}, CF={cliente[4]}")
    
    cur.close()
    conn.close()
    
    return render_template('tools/consulenze/crea_automazione.html', 
                         templates=templates,
                         email_templates=email_templates,
                         clienti=clienti)

@app.route('/consulenze/automazioni/create', methods=['POST'])
@login_required
@has_package('manage_consulenze')
def create_automazione():
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Gestisci i campi in base al tipo di programmazione
        tipo_programmazione = data.get('tipo_programmazione', 'frequenza')
        frequenza_giorni = None
        giorni_prima_scadenza = None
        ora_invio = data['ora_invio']
        
        if tipo_programmazione == 'frequenza':
            freq_val = data.get('frequenza_giorni')
            frequenza_giorni = int(freq_val) if freq_val and freq_val != '' else None
        else:
            giorni_val = data.get('giorni_prima_scadenza')
            giorni_prima_scadenza = int(giorni_val) if giorni_val and giorni_val != '' else None
            ora_invio = data.get('ora_invio_scadenza', data['ora_invio'])
        
        # Gestisci i template ID (converti stringhe vuote in NULL)
        template_pdf_id = data.get('template_pdf_id')
        template_pdf_id = int(template_pdf_id) if template_pdf_id and template_pdf_id != '' else None
        
        email_template_id = data.get('email_template_id')
        email_template_id = int(email_template_id) if email_template_id and email_template_id != '' else None
        
        # Inserisci la nuova automazione
        cur.execute("""
            INSERT INTO automazioni (
                user_id, nome, descrizione, tipo_contenuto, template_pdf_id, 
                email_template_id, testo_personalizzato, tipo_programmazione,
                frequenza_giorni, giorni_prima_scadenza, ora_invio, 
                ripeti_promemoria, attiva, target_clienti
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            session['user_id'],
            data['nome'],
            data.get('descrizione', ''),
            data['tipo_contenuto'],
            template_pdf_id,
            email_template_id,
            data.get('testo_personalizzato'),
            tipo_programmazione,
            frequenza_giorni,
            giorni_prima_scadenza,
            ora_invio,
            data.get('ripeti_promemoria', False),
            data.get('attiva', False),
            data.get('target_clienti', 'tutti')
        ))
        
        automazione_id = cur.fetchone()['id']
        
        # Se sono specificati clienti specifici, inseriscili
        if data.get('target_clienti') == 'specifici' and data.get('clienti_selezionati'):
            for cliente_id in data['clienti_selezionati']:
                cur.execute("""
                    INSERT INTO automazioni_clienti (automazione_id, cliente_id)
                    VALUES (%s, %s)
                """, (automazione_id, cliente_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Automazione creata con successo!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore: {str(e)}'})

@app.route('/consulenze/automazioni/<int:automazione_id>/toggle', methods=['POST'])
@login_required
@has_package('manage_consulenze')
def toggle_automazione(automazione_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica che l'automazione appartenga all'utente
        cur.execute("""
            SELECT attiva FROM automazioni 
            WHERE id = %s AND user_id = %s
        """, (automazione_id, session['user_id']))
        
        result = cur.fetchone()
        if not result:
            return jsonify({'success': False, 'message': 'Automazione non trovata'})
        
        nuovo_stato = not result[0]
        
        # Aggiorna lo stato
        cur.execute("""
            UPDATE automazioni 
            SET attiva = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
        """, (nuovo_stato, automazione_id, session['user_id']))
        
        # Se viene attivata, crea le esecuzioni per i clienti target
        if nuovo_stato:
            # Prima rimuovi eventuali esecuzioni esistenti
            cur.execute("""
                DELETE FROM automazioni_esecuzioni 
                WHERE automazione_id = %s
            """, (automazione_id,))
            
            # Recupera i dettagli dell'automazione
            cur.execute("""
                SELECT target_clienti, frequenza_giorni, ora_invio, tipo_programmazione, giorni_prima_scadenza
                FROM automazioni 
                WHERE id = %s
            """, (automazione_id,))
            
            automazione = cur.fetchone()
            
            # Determina i clienti target
            if automazione[0] == 'tutti':
                if automazione[3] == 'scadenza_polizza':
                    # Per promemoria scadenza, considera solo clienti con data scadenza
                    cur.execute("""
                        SELECT id, data_scadenza_polizza FROM clienti_assicurativi 
                        WHERE user_id = %s AND data_scadenza_polizza IS NOT NULL
                    """, (session['user_id'],))
                else:
                    cur.execute("""
                        SELECT id, NULL as data_scadenza_polizza FROM clienti_assicurativi 
                        WHERE user_id = %s
                    """, (session['user_id'],))
            else:
                if automazione[3] == 'scadenza_polizza':
                    cur.execute("""
                        SELECT ac.cliente_id, ca.data_scadenza_polizza 
                        FROM automazioni_clienti ac
                        JOIN clienti_assicurativi ca ON ac.cliente_id = ca.id
                        WHERE ac.automazione_id = %s AND ca.data_scadenza_polizza IS NOT NULL
                    """, (automazione_id,))
                else:
                    cur.execute("""
                        SELECT ac.cliente_id, NULL as data_scadenza_polizza 
                        FROM automazioni_clienti ac
                        WHERE ac.automazione_id = %s
                    """, (automazione_id,))
            
            clienti_target = cur.fetchall()
            
            # Calcola il prossimo invio
            from datetime import datetime, timedelta
            ora_invio = datetime.strptime(str(automazione[2]), '%H:%M:%S').time()
            
            # Crea le esecuzioni per ogni cliente
            for cliente in clienti_target:
                if automazione[3] == 'scadenza_polizza':
                    # Calcola la data di invio basata sulla scadenza polizza
                    data_scadenza = cliente[1]
                    giorni_prima = automazione[4] or 30
                    data_invio = data_scadenza - timedelta(days=giorni_prima)
                    prossimo_invio = datetime.combine(data_invio, ora_invio)
                    
                    # Se la data è nel passato, salta questo cliente
                    if prossimo_invio <= datetime.now():
                        continue
                else:
                    # Calcola la data di invio basata sulla frequenza
                    prossimo_invio = datetime.combine(datetime.now().date(), ora_invio)
                    
                    # Se l'ora è già passata oggi, programma per domani
                    if prossimo_invio <= datetime.now():
                        prossimo_invio += timedelta(days=1)
                
                cur.execute("""
                    INSERT INTO automazioni_esecuzioni (
                        automazione_id, cliente_id, prossimo_invio, stato
                    ) VALUES (%s, %s, %s, 'attivo')
                """, (automazione_id, cliente[0], prossimo_invio))
        
        conn.commit()
        cur.close()
        conn.close()
        
        stato_text = 'attivata' if nuovo_stato else 'disattivata'
        return jsonify({'success': True, 'message': f'Automazione {stato_text} con successo!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore: {str(e)}'})

@app.route('/consulenze/automazioni/<int:automazione_id>/delete', methods=['DELETE'])
@login_required
@has_package('manage_consulenze')
def delete_automazione(automazione_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica che l'automazione appartenga all'utente
        cur.execute("""
            SELECT id FROM automazioni 
            WHERE id = %s AND user_id = %s
        """, (automazione_id, session['user_id']))
        
        if not cur.fetchone():
            return jsonify({'success': False, 'message': 'Automazione non trovata'})
        
        # Elimina l'automazione (le esecuzioni e clienti associati verranno eliminati per CASCADE)
        cur.execute("""
            DELETE FROM automazioni 
            WHERE id = %s AND user_id = %s
        """, (automazione_id, session['user_id']))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Automazione eliminata con successo!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore: {str(e)}'})

@app.route('/template/add', methods=['POST'])
@login_required
@has_package('manage_consulenze')
@csrf.exempt  # Esenzione CSRF per upload file
def add_template():
    if 'template_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nessun file caricato'}), 400
    
    file = request.files['template_file']
    nome = request.form['template_name']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nessun file selezionato'}), 400
    
    if file and nome:
        filename = secure_filename(f"{nome}_{uuid.uuid4()}.pdf")
        file.save(os.path.join(app.config['PDF_TEMPLATES'], filename))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO template_pdf (nome, filename) VALUES (%s, %s) RETURNING id",
            (nome, filename)
        )
        template_id = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Template aggiunto con successo',
            'template': {
                'id': template_id,
                'nome': nome,
                'filename': filename
            }
        })
    
    return jsonify({'success': False, 'message': 'Errore durante il salvataggio del template'}), 500

# Funzione per inviare email automatiche
def check_and_send_automated_emails():
    """Controlla e invia le email automatiche programmate"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Trova tutte le esecuzioni programmate che devono essere inviate ora
        cur.execute("""
            SELECT ae.id, ae.automazione_id, ae.cliente_id, ae.prossimo_invio,
                   a.nome as automazione_nome, a.tipo_contenuto, a.template_pdf_id, 
                   a.email_template_id, a.testo_personalizzato, a.tipo_programmazione,
                   a.frequenza_giorni, a.giorni_prima_scadenza, a.ripeti_promemoria,
                   c.nome, c.cognome, c.email, c.codice_fiscale
            FROM automazioni_esecuzioni ae
            JOIN automazioni a ON ae.automazione_id = a.id
            JOIN clienti_assicurativi c ON ae.cliente_id = c.id
            WHERE ae.stato = 'attivo' 
            AND ae.prossimo_invio <= NOW()
            AND a.attiva = true
        """)
        
        esecuzioni = cur.fetchall()
        
        for esecuzione in esecuzioni:
            try:
                # Prepara i dati per l'email
                cliente_nome = esecuzione['nome']
                cliente_cognome = esecuzione['cognome']
                cliente_email = esecuzione['email']
                
                # Determina il contenuto dell'email
                if esecuzione['tipo_contenuto'] == 'template_email':
                    # Usa template email
                    cur.execute("SELECT testo FROM email_texts WHERE id = %s", (esecuzione['email_template_id'],))
                    template_result = cur.fetchone()
                    if template_result:
                        testo_email = template_result['testo']
                    else:
                        testo_email = "Email automatica"
                else:
                    # Usa testo personalizzato
                    testo_email = esecuzione['testo_personalizzato'] or "Email automatica"
                
                # Sostituisci i placeholder
                testo_email = testo_email.replace('{nome}', cliente_nome or '')
                testo_email = testo_email.replace('{cognome}', cliente_cognome or '')
                testo_email = testo_email.replace('{codice_fiscale}', esecuzione['codice_fiscale'] or '')
                
                # Prepara l'email
                subject = f"Promemoria automatico - {esecuzione['automazione_nome']}"
                
                # Ottieni configurazione SMTP dalla tabella config_email
                cur.execute("SELECT * FROM config_email LIMIT 1")
                smtp_config = cur.fetchone()
                
                if not smtp_config:
                    print(f"ERRORE: Configurazione SMTP non trovata nel database")
                    continue
                
                smtp_server = smtp_config['smtp_server']
                smtp_port = smtp_config['porta']
                smtp_username = smtp_config['email']
                smtp_password = smtp_config['password']
                
                # Invia l'email
                context = ssl.create_default_context()
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls(context=context)
                    server.login(smtp_username, smtp_password)
                    
                    msg = EmailMessage()
                    msg['Subject'] = subject
                    msg['From'] = smtp_username
                    msg['To'] = cliente_email
                    msg.set_content(testo_email)
                    
                    server.send_message(msg)
                
                print(f"Email inviata con successo a {cliente_email} per automazione {esecuzione['automazione_nome']}")
                
                # Aggiorna l'esecuzione
                cur.execute("""
                    UPDATE automazioni_esecuzioni 
                    SET ultimo_invio = NOW(), tentativi_falliti = 0
                    WHERE id = %s
                """, (esecuzione['id'],))
                
                # Calcola il prossimo invio se necessario
                if esecuzione['ripeti_promemoria'] and esecuzione['tipo_programmazione'] == 'frequenza':
                    # Per automazioni con frequenza, calcola il prossimo invio
                    frequenza_giorni = esecuzione['frequenza_giorni'] or 30
                    prossimo_invio = esecuzione['prossimo_invio'] + timedelta(days=frequenza_giorni)
                    
                    cur.execute("""
                        UPDATE automazioni_esecuzioni 
                        SET prossimo_invio = %s
                        WHERE id = %s
                    """, (prossimo_invio, esecuzione['id']))
                else:
                    # Per promemoria scadenza, marca come completato
                    cur.execute("""
                        UPDATE automazioni_esecuzioni 
                        SET stato = 'completato'
                        WHERE id = %s
                    """, (esecuzione['id'],))
                
            except Exception as e:
                print(f"Errore nell'invio email per esecuzione {esecuzione['id']}: {str(e)}")
                
                # Incrementa i tentativi falliti
                cur.execute("""
                    UPDATE automazioni_esecuzioni 
                    SET tentativi_falliti = tentativi_falliti + 1
                    WHERE id = %s
                """, (esecuzione['id'],))
                
                # Se troppi tentativi falliti, metti in errore
                if esecuzione.get('tentativi_falliti', 0) >= 3:
                    cur.execute("""
                        UPDATE automazioni_esecuzioni 
                        SET stato = 'errore'
                        WHERE id = %s
                    """, (esecuzione['id'],))
        
        conn.commit()
        cur.close()
        conn.close()
        
        if esecuzioni:
            print(f"Processate {len(esecuzioni)} esecuzioni automatiche")
        
    except Exception as e:
        print(f"Errore nel controllo email automatiche: {str(e)}")

# Endpoint per testare manualmente l'invio automatico
@app.route('/test-automated-emails')
@login_required
def test_automated_emails():
    """Endpoint per testare manualmente l'invio delle email automatiche"""
    check_and_send_automated_emails()
    return jsonify({'success': True, 'message': 'Controllo email automatiche eseguito'})

# Endpoint per verificare lo stato delle automazioni
@app.route('/debug-automazioni')
@login_required
def debug_automazioni():
    """Endpoint per verificare lo stato delle automazioni e esecuzioni"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Verifica automazioni attive
    cur.execute("""
        SELECT id, nome, attiva, tipo_programmazione, giorni_prima_scadenza, 
               frequenza_giorni, ora_invio, created_at
        FROM automazioni 
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session['user_id'],))
    automazioni = cur.fetchall()
    
    # Verifica esecuzioni programmate
    cur.execute("""
        SELECT ae.id, ae.automazione_id, ae.cliente_id, ae.prossimo_invio, 
               ae.ultimo_invio, ae.stato, ae.tentativi_falliti,
               a.nome as automazione_nome,
               c.nome as cliente_nome, c.cognome as cliente_cognome, c.email as cliente_email
        FROM automazioni_esecuzioni ae
        JOIN automazioni a ON ae.automazione_id = a.id
        JOIN clienti_assicurativi c ON ae.cliente_id = c.id
        WHERE a.user_id = %s
        ORDER BY ae.prossimo_invio ASC
    """, (session['user_id'],))
    esecuzioni = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return jsonify({
        'automazioni': [dict(a) for a in automazioni],
        'esecuzioni': [dict(e) for e in esecuzioni],
        'ora_attuale': datetime.now().isoformat()
    })

# Initialize database tables
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Funzione di utilità per verificare se una colonna esiste
    def column_exists(table, column):
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table, column))
        return cur.fetchone() is not None
    
    # Funzione di utilità per aggiungere una colonna se non esiste
    def add_column_if_not_exists(table, column, definition):
        if not column_exists(table, column):
            print(f"Aggiunta della colonna {column} alla tabella {table}...")
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                print(f"Colonna {column} aggiunta con successo.")
            except Exception as e:
                print(f"Errore durante l'aggiunta della colonna {column}: {str(e)}")
                # Se c'è un errore, potrebbe essere perché la tabella non esiste ancora
                conn.rollback()
    
    # Verifica se la colonna user_id esiste già nella tabella clienti_assicurativi
    if not column_exists('clienti_assicurativi', 'user_id'):
        print("Aggiunta della colonna user_id alla tabella clienti_assicurativi...")
        try:
            cur.execute("""
                ALTER TABLE clienti_assicurativi 
                ADD COLUMN user_id INTEGER REFERENCES users(id)
            """)
            print("Colonna user_id aggiunta con successo.")
        except Exception as e:
            print(f"Errore durante l'aggiunta della colonna user_id: {str(e)}")
            # Se c'è un errore, potrebbe essere perché la tabella non esiste ancora
            conn.rollback()
    
    # Create users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            ruolo VARCHAR(50) NOT NULL,
            pacchetti TEXT[] NOT NULL
        )
    ''')
    
    # Aggiungi le nuove colonne alla tabella users se non esistono
    add_column_if_not_exists('users', 'active', 'BOOLEAN DEFAULT TRUE')
    add_column_if_not_exists('users', 'last_login', 'TIMESTAMP')
    add_column_if_not_exists('users', 'created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    add_column_if_not_exists('users', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    
    # Create clienti_assicurativi table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clienti_assicurativi (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            cognome VARCHAR(100) NOT NULL,
            data_nascita DATE,
            luogo_nascita VARCHAR(100),
            codice_fiscale VARCHAR(16) NOT NULL,
            user_id INTEGER REFERENCES users(id),
            partita_iva VARCHAR(11),
            email VARCHAR(100),
            pec VARCHAR(100),
            codice_univoco VARCHAR(7),
            cellulare VARCHAR(20),
            attivita VARCHAR(255),
            data_inizio_attivita DATE,
            iscrizione_albo_data DATE,
            iscrizione_albo_numero VARCHAR(50),
            residenza TEXT,
            domicilio_fiscale TEXT,
            ubicazione_studio TEXT,
            fatturato_2024 NUMERIC(15,2),
            stima_2025 NUMERIC(15,2),
            dipendenti BOOLEAN DEFAULT FALSE,
            addetti BOOLEAN DEFAULT FALSE,
            subappaltatori BOOLEAN DEFAULT FALSE,
            documento_fronte VARCHAR(255),
            documento_retro VARCHAR(255),
            polizza_precedente VARCHAR(255),
            questionario_inviato BOOLEAN DEFAULT FALSE,
            nome_questionario_inviato VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Aggiungi il campo data_scadenza_polizza se non esiste
    add_column_if_not_exists('clienti_assicurativi', 'data_scadenza_polizza', 'DATE')
    add_column_if_not_exists('clienti_assicurativi', 'compagnia_assicurativa', 'VARCHAR(255)')
    add_column_if_not_exists('clienti_assicurativi', 'numero_polizza', 'VARCHAR(100)')
    add_column_if_not_exists('clienti_assicurativi', 'tipo_polizza', 'VARCHAR(100)')
    
    # Create template_pdf table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS template_pdf (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Aggiungi user_id alla tabella template_pdf se non esiste
    add_column_if_not_exists('template_pdf', 'user_id', 'INTEGER REFERENCES users(id)')
    
    # Create config_email table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS config_email (
            id SERIAL PRIMARY KEY,
            smtp_server VARCHAR(100) NOT NULL,
            porta INTEGER NOT NULL,
            email VARCHAR(100) NOT NULL,
            password VARCHAR(255) NOT NULL,
            testo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create email_texts table for custom email templates
    cur.execute('''
        CREATE TABLE IF NOT EXISTS email_texts (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            testo TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Aggiungi user_id alla tabella email_texts se non esiste
    add_column_if_not_exists('email_texts', 'user_id', 'INTEGER REFERENCES users(id)')
    
    # Create questionari_inviati table for tracking sent questionnaires
    cur.execute('''
        CREATE TABLE IF NOT EXISTS questionari_inviati (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER REFERENCES clienti_assicurativi(id),
            template_id INTEGER REFERENCES template_pdf(id),
            filename VARCHAR(255) NOT NULL,
            data_invio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            flags TEXT,
            email_text_id INTEGER REFERENCES email_texts(id),
            testo_email TEXT,
            user_id INTEGER REFERENCES users(id)
        )
    ''')
    
    # Add user_id column to questionari_inviati if it doesn't exist
    add_column_if_not_exists('questionari_inviati', 'user_id', 'INTEGER REFERENCES users(id)')
    
    # Change flags column from TEXT[] to TEXT if needed
    try:
        cur.execute("ALTER TABLE questionari_inviati ALTER COLUMN flags TYPE TEXT")
    except:
        # Column might already be TEXT or table might not exist yet
        pass
    
    # Create automazioni table for email automation
    cur.execute('''
        CREATE TABLE IF NOT EXISTS automazioni (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) NOT NULL,
            nome VARCHAR(255) NOT NULL,
            descrizione TEXT,
            tipo_contenuto VARCHAR(50) NOT NULL CHECK (tipo_contenuto IN ('email_semplice', 'questionario_pdf', 'testo_personalizzato')),
            template_pdf_id INTEGER REFERENCES template_pdf(id),
            email_template_id INTEGER REFERENCES email_texts(id),
            testo_personalizzato TEXT,
            tipo_programmazione VARCHAR(20) DEFAULT 'frequenza' CHECK (tipo_programmazione IN ('frequenza', 'scadenza_polizza')),
            frequenza_giorni INTEGER,
            giorni_prima_scadenza INTEGER,
            ora_invio TIME NOT NULL,
            ripeti_promemoria BOOLEAN DEFAULT FALSE,
            attiva BOOLEAN DEFAULT FALSE,
            target_clienti VARCHAR(20) DEFAULT 'tutti' CHECK (target_clienti IN ('tutti', 'specifici')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Aggiungi le nuove colonne se non esistono
    add_column_if_not_exists('automazioni', 'tipo_programmazione', "VARCHAR(20) DEFAULT 'frequenza' CHECK (tipo_programmazione IN ('frequenza', 'scadenza_polizza'))")
    add_column_if_not_exists('automazioni', 'giorni_prima_scadenza', 'INTEGER')
    add_column_if_not_exists('automazioni', 'ripeti_promemoria', 'BOOLEAN DEFAULT FALSE')
    
    # Rimuovi il constraint NOT NULL da frequenza_giorni se esiste
    try:
        cur.execute("ALTER TABLE automazioni ALTER COLUMN frequenza_giorni DROP NOT NULL")
    except:
        pass
    
    # Create automazioni_clienti table for specific client targeting
    cur.execute('''
        CREATE TABLE IF NOT EXISTS automazioni_clienti (
            id SERIAL PRIMARY KEY,
            automazione_id INTEGER REFERENCES automazioni(id) ON DELETE CASCADE,
            cliente_id INTEGER REFERENCES clienti_assicurativi(id) ON DELETE CASCADE,
            UNIQUE(automazione_id, cliente_id)
        )
    ''')
    
    # Create automazioni_esecuzioni table for tracking automation executions
    cur.execute('''
        CREATE TABLE IF NOT EXISTS automazioni_esecuzioni (
            id SERIAL PRIMARY KEY,
            automazione_id INTEGER REFERENCES automazioni(id) ON DELETE CASCADE,
            cliente_id INTEGER REFERENCES clienti_assicurativi(id) ON DELETE CASCADE,
            prossimo_invio TIMESTAMP NOT NULL,
            ultimo_invio TIMESTAMP,
            stato VARCHAR(20) DEFAULT 'attivo' CHECK (stato IN ('attivo', 'pausa', 'completato', 'errore')),
            tentativi_falliti INTEGER DEFAULT 0,
            messaggio_errore TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create automazioni_log table for logging automation activities
    cur.execute('''
        CREATE TABLE IF NOT EXISTS automazioni_log (
            id SERIAL PRIMARY KEY,
            automazione_id INTEGER REFERENCES automazioni(id) ON DELETE CASCADE,
            cliente_id INTEGER REFERENCES clienti_assicurativi(id) ON DELETE CASCADE,
            azione VARCHAR(50) NOT NULL,
            dettagli TEXT,
            esito VARCHAR(20) NOT NULL CHECK (esito IN ('successo', 'errore')),
            messaggio_errore TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create eventi table for calendar events
    cur.execute('''
        CREATE TABLE IF NOT EXISTS eventi (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            type VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            start_time TIME,
            end_date DATE,
            end_time TIME,
            all_day BOOLEAN DEFAULT TRUE,
            client_id INTEGER REFERENCES clienti_assicurativi(id),
            description TEXT,
            notify BOOLEAN DEFAULT FALSE,
            notify_days INTEGER DEFAULT 0,
            notify_email VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if admin user exists, if not create one
    cur.execute("SELECT COUNT(*) as count FROM users WHERE ruolo = 'admin'")
    if cur.fetchone()['count'] == 0:
        admin_password = generate_password_hash('admin')
        cur.execute(
            "INSERT INTO users (username, password, ruolo, pacchetti) VALUES (%s, %s, %s, %s)",
            ('admin', admin_password, 'admin', ['manage_consulenze', 'manage_drivers'])
        )
    
    # Create default email text if none exists
    cur.execute("SELECT COUNT(*) as count FROM email_texts")
    if cur.fetchone()['count'] == 0:
        cur.execute(
            "INSERT INTO email_texts (nome, testo) VALUES (%s, %s)",
            ('Default', 'Gentile {nome} {cognome},\n\nIn allegato il questionario assicurativo da compilare.\n\nCordiali saluti,\nIl tuo Consulente Assicurativo')
        )
    
    # Create sample template PDF if none exists
    cur.execute("SELECT COUNT(*) as count FROM template_pdf")
    if cur.fetchone()['count'] == 0:
        cur.execute(
            "INSERT INTO template_pdf (nome, filename) VALUES (%s, %s)",
            ('Questionario Base', 'template_base.pdf')
        )
    
    cur.close()
    conn.close()

# Thread per il controllo automatico delle email
def email_scheduler():
    """Thread che controlla ogni minuto se ci sono email da inviare"""
    while True:
        try:
            check_and_send_automated_emails()
        except Exception as e:
            print(f"Errore nel thread email scheduler: {str(e)}")
        time.sleep(60)  # Controlla ogni minuto

if __name__ == '__main__':
    init_db()
    
    # Avvia il thread per il controllo automatico delle email
    email_thread = threading.Thread(target=email_scheduler, daemon=True)
    email_thread.start()
    print("Thread email scheduler avviato")
    
    app.run(debug=True)