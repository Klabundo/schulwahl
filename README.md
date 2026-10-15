# Abstimmungssystem für die Schule

Kleines Web-Abstimmungssystem für die Ökologie- & Demokratiewoche am
Käthe-Kollwitz-Gymnasium: Wahlen anlegen (z. B. Schülerrat oder
Klimaprojekt der Schule), jeder Person einen persönlichen Stimmcode
ausgeben und die Ergebnisse live auf dem Beamer mitlaufen lassen.

**Eine Person = ein Code = eine Stimme. Anonym.**

## Technologie

| Baustein            | Was                              |
|---------------------|----------------------------------|
| Backend             | Python + Flask                   |
| Datenbank           | SQLite (`schulwahl.db`, automatisch angelegt) |
| Frontend            | HTML/CSS/JavaScript, ohne Framework |
| Live-Ergebnisse     | Server-Sent Events (SSE)          |
| QR-Codes            | qrcode + Pillow                   |

Keine externen Dienste nötig – alles läuft lokal in einer Python-3-venv.

## Starten

```bash
./run.sh            # erzeugt venv + installiert + startet auf Port 8400
```

Manuell:

```bash
python3 -m venv venv
venv/bin/pip install flask qrcode pillow
PORT=8400 venv/bin/python app.py
```

Dann im Browser öffnen (in der Schule am besten über die IP des Rechners):

```
http://IP-DES-RECHNERS:8400/
```

## Standard-Passwort

`admin123` – **bitte sofort ändern** (im Admin-Panel unten links:
„Passwort ändern"), bevor die Woche losgeht.

## Ablauf an der Woche

### Vorbereitung (Verantwortliche/r):

1. `/admin` öffnen, mit Passwort anmelden.
2. **Neue Wahl anlegen**: Titel, Beschreibung, wie viele Optionen pro
   Stimmzettel gewählt werden dürfen (Standard: 1) und optional einen
   **Stichtag** (z. B. Freitag 12:00 Uhr) – danach beendet sich die
   Wahl automatisch. Einen Stichtag kann man später auch noch über den
   Button **„Stichtag"** in der Detailansicht setzen oder entfernen.
3. Im Tab **Kandidat:innen** alle Projekte / Kandidat:innen eintragen
   (Name + kurzer Slogan).
4. Im Tab **Stimmzettel** so viele Stimmzettel erzeugen wie
   stimmberechtigte Personen es gibt (z. B. 60 für eine Schule).
   Jede:r bekommt **einen** Code auf einem Zettel.
5. **Stimmzettel drucken**: Button **„Stimmzettel drucken"** öffnet die
   Druck-Ansicht (`/print/<id>`) – eine A4-Seite mit 25/50/100
   Code-Kästchen (wählbar), optional mit QR-Code auf jedem Zettel.
   *Wichtig: Nur bei reinem LAN-Betrieb die „QR-Link-Basis" auf die
   Server-IP setzen (z. B. `http://192.168.178.160:8400`), damit die
   Handys den Server erreichen. Bei nginx/HTTPS übernimmt das die App
   von allein.*
6. **Wahl starten** (blauer Button oben rechts in der Detailansicht).
   **Mehrere Wahlen dürfen parallel laufen** – auf Startseite,
   Stimmseite und Dashboard werden sie einzeln angezeigt.

### Während der Abstimmung:

- Schüler:innen: `/vote` öffnen (oder den QR scannen), Code eingeben,
  Option wählen, abstimmen. Mit Stichtag zeigt die Stimmseite, wie
  lange noch abgestimmt werden kann.
- Beamer im Raum: Öffnet `/dashboard` – dort laufen alle Stimmen live
  mit, bei mehreren Wahlen unten auswählbar.

### Danach:

- **Wahl beenden** (roter Button) oder per **Stichtag** automatisch –
  danach kann niemand mehr abstimmen.
- Tab **Ergebnisse** zeigt die Rangliste mit Stimmen und Beteiligung;
  per Button **„Als CSV laden"** kann das Ergebnis als Tabelle exportiert
  werden (z. B. für den Abschlussbericht).

### Finale (optional – zweite Runde)

Wenn Runde 1 beendet ist, erscheint in der Detailansicht der Button
**„Finale anlegen"**. Ein Klick fragt kurz, wie viele Kandidat:innen
ins Finale einziehen (Standard: 2), und legt automatisch eine neue
Wahl an:

- Titel: „<Originaltitel> – Finale"
- Kandidat:innen: die besten aus Runde 1 (Top-N, wie eingegeben)
- Status: „bereit" – Stimmzettel neu anlegen (drucken) und dann
  **Wahl starten**.

Die zweite Runde wird auf allen Seiten mit dem orangenen Badge
**„Finale · Runde 2"** gekennzeichnet.

## Seiten / API

| Pfad                            | Funktion                                   |
|---------------------------------|--------------------------------------------|
| `/`                             | Startseite                                  |
| `/vote?e=<id>&c=<code>`         | Stimmabgabe (URL aus QR-Zettel)            |
| `/dashboard?e=<id>`             | Live-Ergebnisse (Beamer)                   |
| `/admin`                        | Verwaltung (passwort-geschützt)            |
| `/print/<id>?per=50&qr=1`       | Stimmzettel-Druckansicht (nur mit Admin-Login) |
| `/api/elections/open`           | Laufende Wahlen (JSON)                      |
| `/api/election/<id>/public`     | Kandidat:innen einer Wahl (ohne Ergebnisse)|
| `/api/vote`                     | POST: Stimme abgeben                        |
| `/api/election/<id>/results`    | Ergebnisse (JSON)                           |
| `/stream/<id>`                  | SSE-Stream für Live-Ergebnisse             |
| `/api/admin/elections/<id>/results.csv` | Ergebnis-Export (CSV, Admin)        |
| `/api/admin/elections/<id>/deadline` | POST: Stichtag setzen/entfernen (Admin) |

## Betrieb über nginx + DuckDNS (HTTPS) – für die Schule

Ziel: Die Abstimmung läuft dauerhaft unter `https://kkgschule.duckdns.net/`
– die QR-Codes zeigen von selbst darauf.

### 1. DuckDNS

1. Konto auf duckdns.org anlegen, Subdomain z. B. `kkgschule`
   => FQDN `kkgschule.duckdns.net`.
2. **DNS aktuell halten**: Auf dem Schul-Server den Duckie-Client
   installieren (Token aus dem DuckDNS-Adminbereich):

   ```bash
   curl -O https://www.duckdns.org/duckie.sh && chmod +x duckie.sh
    sudo ./duckie.sh -o install -u kkgschule -p <TOKEN>   # Einrichtung + Autostart
   ```

   Der Client aktualisiert die Public-IP bei jedem IP-Wechsel automatisch.

3. **Firewall öffnen**:

   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

### 2. nginx als Reverse-Proxy

`/etc/nginx/sites-available/schulstimme`:

```nginx
server {
    server_name kkgschule.duckdns.net;

    # Let's Encrypt (webroot)
    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name kkgschule.duckdns.net;

    ssl_certificate     /etc/letsencrypt/live/kkgschule.duckdns.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kkgschule.duckdns.net/privkey.pem;

    client_max_body_size 5m;

    location / {
        proxy_pass http://127.0.0.1:8400;
        proxy_set_header Host $host;                 # wichtig: QR-URLs
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;  # wichtig: https statt http
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/schulstimme /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 3. Zertifikat (Let's Encrypt)

```bash
sudo mkdir -p /var/www/letsencrypt
sudo certbot certonly --webroot -w /var/www/letsencrypt -d kkgschule.duckdns.net
```

Certbot erneuert das Zertifikat automatisch (systemd-Timer). Alternativ:
DuckDNS bietet unter „Let's Encrypt" einen eingebauten
Zertifikat-Generator an.

### 4. App + QR-Codes

- Flask läuft weiter lokal: `PORT=8400 ./run.sh` (besser: als
  systemd-Service, damit es bei Neustart hochkommt).
- Ab sofort erzeugen **QR-Codes automatisch** Links wie
  `https://kkgschule.duckdns.net/vote?e=1&c=XXXX-XXXX` –
  die App übernimmt das über die `Host`/`X-Forwarded-Proto`-Header
  von nginx (ProxyFix). Die "QR-Link-Basis" im Admin-Panel braucht man
  dann nur noch, wenn nginx auf einer anderen Adresse läuft.
- **Niemals direkt `127.0.0.1:8400/` von außen freigeben** – immer über
  nginx.

### systemd-Service (optional)

`/etc/systemd/system/schulstimme.service`:

```ini
[Unit]
Description=Abstimmungssystem (KKG)
After=network.target

[Service]
WorkingDirectory=/home/jonathan/scratch_opencode/schulwahl
Environment=PORT=8400
ExecStart=/home/jonathan/scratch_opencode/schulwahl/venv/bin/python app.py
Restart=always
User=jonathan

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now schulstimme
```

## Datenschema (SQLite)

```
elections(id, title, description, max_votes, status, created_at, started_at, ended_at,
          ends_at, round, parent_id)
          -- round=1: Vorrunde, round=2: Finale (parent_id = ID der Vorrunde)
          -- ends_at: optionaler Stichtag (JJJJ-MM-TT HH:MM:SS) – danach wird
          -- die Wahl automatisch beendet
candidates(id, election_id, name, slogan, sort)
ballots(id, election_id, code UNIQUE, used_at)
votes(id, election_id, candidate_id, cast_at)
meta(key, value)            -- secret_key + gehashtes Admin-Passwort
```

## Sicherheit (für eine Schulwoche ausreichend)

- Admin-Panel nur mit Passwort (Session-Cookie, HttpOnly).
- Admin-Passwort wird als SHA-256-Hash mit Salt gespeichert.
- Ein Code kann nur **einmal** benutzt werden (doppelte Nutzung wird abgelehnt).
- Anonymität: Stimmen sind im `votes`-Table nicht an Codes geknüpft,
  Stimmzettel werden nur "verbraucht" – wer wen gewählt hat, lässt sich
  nicht mehr zurückverfolgen.
- `status`-Maschine: `draft` -> `running` -> `closed`; nur in `running`
  sind Stimmen möglich. Ein gesetzter Stichtag (`ends_at`) schließt die
  Wahl von selbst; Stimmen danach werden zusätzlich per Code-Check
  abgelehnt, falls der Auto-Beender noch nicht drüber war.

Für einen Einsatz über die Woche hinaus wäre zusätzlich sinnvoll:
ein Audit-Log (wer hat wann gestartet/beendet), eine Passwort-Richtlinie
und regelmäßige Backups der Datenbank.

## Ideen, wenn man mehr Zeit hat

- Fotos von Kandidat:innen / Projekten neben dem Namen
- Rundenergebnisse nebeneinander anzeigen (Vorrunde + Finale im selben Dashboard)
- "Ehrenwort-Modus" ohne Codes für kleine Klassen (nur 1 Code pro Klasse)
- Thematischer Look & Feel anpassen (CSS-Variablen in `static/style.css`)

## Tests

Automatisierte E2E-Tests (laufende Wahl, Stimmzettel, Stimmen, Finale,
Stichtag, CSV, Druck, parallele Wahlen) – laufen gegen eine eigene
Temp-DB und berühren `schulwahl.db` nicht:

```bash
venv/bin/python -m pytest
```

## Fehlerbehebung

- **Port belegt?** `PORT=8401 venv/bin/python app.py`
- **Server neu starten (Daten bleiben):** Altprozess per PID beenden –
  `ss -tlnp | grep 8400` zeigt die PID – dann neu starten.
- **Alles zurücksetzen:** Server stoppen, `schulwahl.db` löschen,
  neu starten (wird von vorn bespielt).
