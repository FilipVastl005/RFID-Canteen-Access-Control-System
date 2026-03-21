# RFID Canteen Access Control System

A distributed access control system for a school/university canteen built with two ESP32/ESP8266 nodes and a Python Flask backend. Students scan RFID cards at the entrance and exit. The backend tracks occupancy in real time and serves a live dashboard for admins and a clean occupancy view for students.

---

## Architecture

```
┌─────────────────┐        POST /rfid        ┌──────────────────────┐
│  ESP Entry Node │ ───────────────────────► │                      │
│  (esp_code.ino) │      X-API-Key header    │   Flask Server       │
└─────────────────┘                          │   (app.py)           │
                                             │                      │
┌─────────────────┐        POST /unlog       │   SQLite DB          │
│  ESP Exit Node  │ ───────────────────────► │   rfid_system.db     │
│  (esp_exit.ino) │      X-API-Key header    │                      │
└─────────────────┘                          └──────────┬───────────┘
                                                        │
                                             ┌──────────▼───────────┐
                                             │  Web Interface       │
                                             │                      │
                                             │  /login   — role     │
                                             │  /canteen — students │
                                             │  /dashboard — admin  │
                                             │  /manage  — admin    │
                                             └──────────────────────┘
```

---

## Features

- **Dual ESP node setup** — one reader at the entrance logs entries, one at the exit logs departures
- **Real-time occupancy tracking** — live canteen fill percentage updated every 500ms
- **Role-based access** — students see a clean occupancy page with charts, admins see the full dashboard
- **Admin dashboard** — live log of all scans split by Granted / Denied / Unknown
- **User management** — add, block, delete, or bulk import users via CSV/XLSX
- **Unknown card registration** — unknown cards appear instantly and can be registered with one click
- **Occupancy charts** — hourly bar chart for today and 7-day peak chart, rendered with Canvas (no library)
- **API key authentication** — all ESP requests are verified server-side
- **Responsive UI** — works on desktop, tablet, and mobile with hamburger nav

---

## Project Structure

```
├── app.py                  Flask backend
├── esp_code.ino            Entry node firmware (Arduino)
├── esp_exit.ino            Exit node firmware (Arduino)
├── rfid_system.db          SQLite database (auto-created)
└── templates/
    ├── login.html          Role selection page
    ├── canteen.html        Student occupancy view
    ├── index.html          Admin live log dashboard
    └── manage.html         Admin user management
```

---

## Hardware Required

| Component | Quantity |
|---|---|
| ESP32 or ESP8266 | 2 |
| MFRC522 RFID reader | 2 |
| RFID cards / fobs | As needed |
| Jumper wires | — |

### Wiring (MFRC522 → ESP32)

| MFRC522 | ESP32 |
|---|---|
| SDA | GPIO 5 |
| SCK | GPIO 18 |
| MOSI | GPIO 23 |
| MISO | GPIO 19 |
| RST | GPIO 22 |
| 3.3V | 3.3V |
| GND | GND |

For ESP8266: SDA → D8, RST → D3, standard SPI pins.

---

## Setup

### 1. Flask Server

```bash
pip install flask pandas openpyxl
python app.py
```

The server starts on `0.0.0.0:5000` and auto-creates the database on first run.

### 2. Configuration (app.py)

```python
ADMIN_PASSWORD   = "admin"        # Web dashboard password
API_KEY          = "mysecretkey123"  # Shared key with ESP nodes
CANTEEN_CAPACITY = 45             # Maximum occupancy
```

### 3. ESP Firmware

Open `esp_code.ino` or `esp_exit.ino` in Arduino IDE.

**Required libraries** (install via Library Manager):
- `MFRC522` by GithubCommunity

Edit the top of each file:

```cpp
#define USE_ESP32          // comment out for ESP8266

const char* SSID        = "YOUR_SSID";
const char* WIFI_PASS   = "YOUR_PASSWORD";
const char* SERVER_IP   = "192.168.1.100";  // your Flask server IP
const char* API_KEY     = "mysecretkey123"; // must match app.py
```

Flash `esp_code.ino` to the entry node and `esp_exit.ino` to the exit node.

---

## Serial Commands

### Entry Node (`esp_code.ino`)

| Command | Action |
|---|---|
| `add-Test` | Register test card (TEST001) in the database |
| `log-Test` | Simulate a scan with test card |
| `add-name:Bob_isicid:abc123_isallowed:1` | Register a user |
| `log-name:Bob_isicid:abc123_isallowed:1` | Simulate a scan |

### Exit Node (`esp_exit.ino`)

| Command | Action |
|---|---|
| `unlog-<cardId>` | Check out a specific card e.g. `unlog-A1B2C3` |
| `unlog-Test` | Check out the test card |
| `status` | Print WiFi connection status and IP |

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/rfid` | API key | Card scan event from entry node |
| `POST` | `/unlog` | API key | Card exit event from exit node |
| `GET` | `/api/canteen` | None | Current occupancy (used by student view) |
| `GET` | `/api/canteen/history` | None | Hourly + weekly chart data |
| `GET` | `/api/logs` | Session | Last 40 log entries (admin) |
| `GET` | `/api/users` | Session | All users in allowed list (admin) |
| `POST` | `/login` | — | Admin login |
| `GET` | `/logout` | — | Clear session |
| `GET/POST` | `/manage` | Session | User management |
| `POST` | `/import` | Session | Bulk CSV/XLSX import |
| `GET` | `/toggle/<id>` | Session | Flip user allow/block status |
| `GET` | `/delete/<id>` | Session | Delete user |
| `GET` | `/clear` | Session | Wipe all logs and exits |

### ESP Payload Format (`POST /rfid`)

```json
{
  "id": "A1B2C3",
  "name": "CARD_SCAN",
  "is_allowed": 0,
  "is_test": false
}
```

Set `is_test: true` to register/update a user instead of logging a scan.

### Exit Payload Format (`POST /unlog`)

```json
{
  "id": "A1B2C3"
}
```

### CSV Import Format

```csv
isic_id,name,is_allowed
A1B2C3,Jane Smith,1
B2C3D4,John Doe,0
```

`is_allowed` is optional and defaults to `1`.

---

## Database Schema

```sql
allowed_list (isic_id TEXT PRIMARY KEY, name TEXT, is_allowed INTEGER)
logs         (id, isic_id, timestamp, status)   -- ALLOWED / DENIED / UNKNOWN
exits        (id, isic_id, timestamp)           -- checkout events
```

Occupancy = `COUNT(logs WHERE status=ALLOWED today)` − `COUNT(exits today)`, clamped to `[0, CANTEEN_CAPACITY]`.

---

## Switching Between ESP32 and ESP8266

At the top of either `.ino` file, comment out the define to target ESP8266:

```cpp
// #define USE_ESP32   ← comment out for ESP8266
```

---

## License

MIT
