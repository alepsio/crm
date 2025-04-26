import psycopg2
import psycopg2.extras

def get_db_connection():
    conn = psycopg2.connect(
        host='dpg-d042mnbuibrs73amtn5g-a.frankfurt-postgres.render.com',
        database='crm_96md',
        user='crm_96md_user',
        password='JUXtm5gEKXkq03EYfpWntZT0QBbHaf2Z'
    )
    conn.autocommit = True
    return conn

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Aggiorna la tabella questionari_inviati con nuovi campi per lo storico invii
    cur.execute('''
        ALTER TABLE questionari_inviati 
        ADD COLUMN IF NOT EXISTS stato VARCHAR(50) DEFAULT 'inviato',
        ADD COLUMN IF NOT EXISTS data_apertura TIMESTAMP,
        ADD COLUMN IF NOT EXISTS data_completamento TIMESTAMP,
        ADD COLUMN IF NOT EXISTS numero_visualizzazioni INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS ip_apertura VARCHAR(50),
        ADD COLUMN IF NOT EXISTS user_agent TEXT,
        ADD COLUMN IF NOT EXISTS note TEXT,
        ADD COLUMN IF NOT EXISTS inviato_da INTEGER REFERENCES users(id)
    ''')
    
    # Crea una tabella per tracciare le interazioni con i questionari
    cur.execute('''
        CREATE TABLE IF NOT EXISTS questionari_interazioni (
            id SERIAL PRIMARY KEY,
            questionario_id INTEGER REFERENCES questionari_inviati(id) ON DELETE CASCADE,
            tipo_interazione VARCHAR(50) NOT NULL,
            data_interazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dettagli TEXT,
            ip_address VARCHAR(50),
            user_agent TEXT
        )
    ''')
    
    # Crea una tabella per i log di reinvio
    cur.execute('''
        CREATE TABLE IF NOT EXISTS questionari_reinvii (
            id SERIAL PRIMARY KEY,
            questionario_originale_id INTEGER REFERENCES questionari_inviati(id) ON DELETE CASCADE,
            questionario_nuovo_id INTEGER REFERENCES questionari_inviati(id) ON DELETE CASCADE,
            data_reinvio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            motivo TEXT,
            inviato_da INTEGER REFERENCES users(id)
        )
    ''')
    
    # Crea indici per migliorare le performance delle query
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_questionari_cliente_id ON questionari_inviati(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_questionari_data_invio ON questionari_inviati(data_invio);
        CREATE INDEX IF NOT EXISTS idx_questionari_stato ON questionari_inviati(stato);
        CREATE INDEX IF NOT EXISTS idx_interazioni_questionario_id ON questionari_interazioni(questionario_id);
        CREATE INDEX IF NOT EXISTS idx_interazioni_tipo ON questionari_interazioni(tipo_interazione);
    ''')
    
    print("Tabelle per lo Storico Invii create/aggiornate con successo!")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()