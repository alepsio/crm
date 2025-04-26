# Script per correggere i riferimenti a datetime.datetime.now()
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Sostituisci datetime.datetime.now() con datetime.now()
content = content.replace('datetime.datetime.now()', 'datetime.now()')

# Sostituisci datetime.datetime con datetime
content = content.replace('datetime.datetime', 'datetime')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Sostituzione completata!")