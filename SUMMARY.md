# Tool di Gestione Consulenze Assicurative - Riepilogo

## Panoramica del Progetto
Abbiamo creato un'applicazione web professionale per la gestione di consulenze assicurative utilizzando Flask come backend, PostgreSQL come database e Bootstrap 5 per un'interfaccia utente moderna e responsive.

## Funzionalità Implementate

### 1. Sistema di Autenticazione
- Login con username e password
- Gestione sessioni utente
- Protezione delle rotte con decoratori personalizzati
- Pannello amministrativo per la gestione degli utenti

### 2. Dashboard Cliente
- Visualizzazione dei tool disponibili in base al pacchetto associato
- Interfaccia moderna con cards
- Accesso ai vari strumenti di gestione

### 3. Gestione Consulenze Assicurative
- **Anagrafica Clienti**: Form completo per l'inserimento dei dati cliente
- **Panoramica Clienti**: Tabella responsive con filtri avanzati e modifica inline
- **Questionari PDF**: Generazione di PDF precompilati e invio via email
- **Configurazione Email**: Impostazioni SMTP personalizzabili

### 4. Funzionalità Tecniche
- Compilazione automatica di PDF con PyPDF2
- Upload e gestione di file (documenti, polizze)
- Invio email con SMTP_SSL
- Interfaccia utente responsive con Bootstrap 5
- Feedback visivo con toast e SweetAlert2
- Dropdown avanzati con Select2

## Struttura del Database
- **users**: Gestione utenti e pacchetti
- **clienti_assicurativi**: Dati anagrafici e documenti dei clienti
- **template_pdf**: Template per i questionari
- **config_email**: Configurazione SMTP

## Tecnologie Utilizzate
- **Backend**: Flask (Python)
- **Database**: PostgreSQL
- **Frontend**: Bootstrap 5, jQuery, Select2
- **Notifiche**: SweetAlert2, Toast
- **PDF**: PyPDF2
- **Email**: smtplib, ssl

## Istruzioni per l'Uso
1. Avviare l'applicazione con `python run.py` o eseguendo `start.bat`
2. Accedere con le credenziali predefinite (admin/admin)
3. Configurare le impostazioni email
4. Iniziare ad aggiungere clienti e generare questionari

## Sviluppi Futuri
- Scadenze e notifiche automatiche
- Anagrafica assicurazioni
- Storico invii
- Testi email personalizzati