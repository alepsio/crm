# Tool di Gestione Consulenze Assicurative

Un'applicazione web professionale per la gestione di clienti, polizze, invii di questionari PDF e notifiche automatiche per consulenti assicurativi.

## Caratteristiche

- **Dashboard Cliente** con accesso a vari tool in base al pacchetto associato
- **Gestione Consulenze Assicurative**:
  - Anagrafica Clienti
  - Panoramica Clienti con filtri avanzati
  - Questionari PDF con compilazione automatica e invio email
  - Configurazione Email (SMTP)
- **Pannello Admin** per la gestione degli utenti e dei pacchetti
- **UI moderna e responsive** con Bootstrap 5

## Requisiti

- Python 3.8+
- PostgreSQL
- Librerie Python (vedi requirements.txt)

## Installazione

1. Clona il repository:
   ```
   git clone <repository-url>
   cd insurance-management-tool
   ```

2. Crea un ambiente virtuale e attivalo:
   ```
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

3. Installa le dipendenze:
   ```
   pip install -r requirements.txt
   ```

4. Configura il database PostgreSQL:
   - Crea un database chiamato `insurance_management`
   - Aggiorna le credenziali del database in `app.py` se necessario

5. Avvia l'applicazione:
   ```
   python app.py
   ```

6. Accedi all'applicazione:
   - URL: http://localhost:5000
   - Credenziali predefinite: username `admin`, password `admin`

## Struttura del Progetto

```
/app
  /static
    /css
    /js
    /pdf_templates    # Template PDF con campi compilabili
    /pdf_generati     # PDF generati dal sistema
    /upload_clienti   # File caricati dai clienti
  /templates
    /admin            # Template per il pannello admin
    /tools
      /consulenze     # Template per la gestione consulenze
app.py                # Applicazione Flask principale
requirements.txt      # Dipendenze Python
```

## Utilizzo

### Anagrafica Clienti
- Inserisci i dati completi del cliente
- Carica documenti (fronte/retro documento, polizza precedente)

### Panoramica Clienti
- Visualizza tutti i clienti in una tabella responsive
- Filtra per qualsiasi campo
- Modifica inline con doppio click sulle celle
- Visualizza PDF inviati direttamente nel browser

### Questionari PDF
- Seleziona cliente e template PDF
- Aggiungi flags opzionali
- Genera PDF precompilato con i dati del cliente
- Invia questionario via email

### Configurazione Email
- Configura le impostazioni SMTP per l'invio delle email
- Personalizza il testo predefinito delle email

## Licenza

Tutti i diritti riservati.