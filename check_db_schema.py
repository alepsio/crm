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
    
    # Ottieni tutte le tabelle
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = cur.fetchall()
    
    print("Tabelle nel database:")
    for table in tables:
        print(f"- {table[0]}")
    
    # Ottieni la struttura di tutte le tabelle
    for table in tables:
        table_name = table[0]
        print(f"\nStruttura della tabella {table_name}:")
        cur.execute("""
            SELECT column_name, data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
    
    columns = cur.fetchall()
    print("Colonna | Tipo | Lunghezza massima")
    print("-" * 60)
    for col in columns:
        print(f"{col[0]} | {col[1]} | {col[2]}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()