import psycopg2

def get_db_connection():
    conn = psycopg2.connect(
        host='localhost',
        database='insurance_management',
        user='postgres',
        password='postgres'
    )
    conn.autocommit = True
    return conn

def check_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Lista delle tabelle da verificare
    tables = [
        'users',
        'clienti_assicurativi',
        'template_pdf',
        'questionari_inviati',
        'questionari_interazioni',
        'questionari_reinvii'
    ]
    
    # Verifica l'esistenza di ogni tabella
    for table in tables:
        cur.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
            (table,)
        )
        exists = cur.fetchone()[0]
        print(f"Tabella {table}: {'Esiste' if exists else 'Non esiste'}")
    
    # Verifica la struttura della tabella template_pdf
    if 'template_pdf' in tables:
        try:
            cur.execute("SELECT id, nome, filename FROM template_pdf LIMIT 1")
            print("Struttura tabella template_pdf: OK")
        except psycopg2.Error as e:
            print(f"Errore nella struttura della tabella template_pdf: {e}")
    
    # Verifica la struttura della tabella clienti_assicurativi
    if 'clienti_assicurativi' in tables:
        try:
            cur.execute("SELECT id, nome, cognome, email FROM clienti_assicurativi LIMIT 1")
            print("Struttura tabella clienti_assicurativi: OK")
        except psycopg2.Error as e:
            print(f"Errore nella struttura della tabella clienti_assicurativi: {e}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_tables()