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

def check_users():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Ottieni tutti gli utenti
    cur.execute("SELECT id, username, ruolo, pacchetti FROM users")
    users = cur.fetchall()
    
    print("ID | Username | Ruolo | Pacchetti")
    print("-" * 60)
    
    for user in users:
        print(f"{user['id']} | {user['username']} | {user['ruolo']} | {user['pacchetti']}")
    
    # Verifica se almeno un utente ha il pacchetto manage_consulenze
    has_manage_consulenze = False
    for user in users:
        packages = user['pacchetti']
        if packages:
            if isinstance(packages, list) and 'manage_consulenze' in packages:
                has_manage_consulenze = True
                break
            elif isinstance(packages, str):
                if 'manage_consulenze' in packages:
                    has_manage_consulenze = True
                    break
    
    if not has_manage_consulenze:
        print("\nNessun utente ha il pacchetto 'manage_consulenze'")
        
        # Aggiungi il pacchetto all'utente admin
        cur.execute("UPDATE users SET pacchetti = ARRAY['manage_consulenze'] WHERE username = 'admin'")
        print("Pacchetto 'manage_consulenze' aggiunto all'utente admin")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_users()