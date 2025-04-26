import psycopg2
import psycopg2.extras

def get_db_connection():
    conn = psycopg2.connect(
        host='localhost',
        database='insurance_management',
        user='postgres',
        password='postgres'
    )
    conn.autocommit = True
    return conn

def check_table_exists(table_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
        (table_name,)
    )
    exists = cur.fetchone()[0]
    cur.close()
    conn.close()
    return exists

def create_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Crea la tabella questionari_inviati se non esiste
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questionari_inviati (
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER NOT NULL,
        template_id INTEGER,
        filename VARCHAR(255) NOT NULL,
        data_invio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        data_apertura TIMESTAMP,
        data_completamento TIMESTAMP,
        stato VARCHAR(50) NOT NULL DEFAULT 'inviato',
        numero_visualizzazioni INTEGER DEFAULT 0,
        inviato_da INTEGER,
        note TEXT,
        token VARCHAR(100) UNIQUE,
        scadenza TIMESTAMP,
        FOREIGN KEY (cliente_id) REFERENCES clienti_assicurativi(id) ON DELETE CASCADE,
        FOREIGN KEY (template_id) REFERENCES template_pdf(id) ON DELETE SET NULL,
        FOREIGN KEY (inviato_da) REFERENCES users(id) ON DELETE SET NULL
    )
    """)
    
    # Crea la tabella questionari_interazioni se non esiste
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questionari_interazioni (
        id SERIAL PRIMARY KEY,
        questionario_id INTEGER NOT NULL,
        tipo_interazione VARCHAR(50) NOT NULL,
        data_interazione TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        dettagli TEXT,
        ip_address VARCHAR(50),
        user_agent TEXT,
        FOREIGN KEY (questionario_id) REFERENCES questionari_inviati(id) ON DELETE CASCADE
    )
    """)
    
    # Crea la tabella questionari_reinvii se non esiste
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questionari_reinvii (
        id SERIAL PRIMARY KEY,
        questionario_originale_id INTEGER NOT NULL,
        questionario_nuovo_id INTEGER NOT NULL,
        data_reinvio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        motivo VARCHAR(100),
        note TEXT,
        inviato_da INTEGER,
        FOREIGN KEY (questionario_originale_id) REFERENCES questionari_inviati(id) ON DELETE CASCADE,
        FOREIGN KEY (questionario_nuovo_id) REFERENCES questionari_inviati(id) ON DELETE CASCADE,
        FOREIGN KEY (inviato_da) REFERENCES users(id) ON DELETE SET NULL
    )
    """)
    
    # Crea indici per migliorare le performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_questionari_cliente ON questionari_inviati(cliente_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_questionari_stato ON questionari_inviati(stato)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_questionari_data ON questionari_inviati(data_invio)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interazioni_questionario ON questionari_interazioni(questionario_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interazioni_tipo ON questionari_interazioni(tipo_interazione)")
    
    conn.commit()
    cur.close()
    conn.close()
    print("Tabelle create con successo!")

if __name__ == "__main__":
    # Verifica se le tabelle esistono
    tables = ['questionari_inviati', 'questionari_interazioni', 'questionari_reinvii']
    missing_tables = [table for table in tables if not check_table_exists(table)]
    
    if missing_tables:
        print(f"Tabelle mancanti: {', '.join(missing_tables)}")
        create_tables()
    else:
        print("Tutte le tabelle necessarie esistono già.")