from app import app, init_db

if __name__ == '__main__':
    print("Initializing database...")
    init_db()
    print("Starting application...")
    app.run(debug=True, host='0.0.0.0', port=5000)