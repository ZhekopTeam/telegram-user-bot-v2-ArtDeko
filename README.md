# 🤖 Telegram Account Warmup Manager (V2)

An enterprise-grade Telegram automation solution designed to warm up multiple Telegram accounts simultaneously by simulating natural, human-like chat behaviors. Managed entirely through a secure Telegram Bot admin panel, it features encrypted SQLite session storage, scheduling algorithms, and automatic Google Sheets status synchronization.

## 🌟 Key Features

*   **Centralized Admin Control Bot** – A full-featured bot interface built using **Aiogram 3.x** allowing admins to control all account warmups, create chains, check statistics, and view queues.
*   **Secure Authentication Keypad** – Complete registration flow for new user-bots right within the admin Telegram chat, featuring a custom numeric keypad for entering 2FA/login codes safely.
*   **Encrypted Pyrogram Session Storage** – Eliminates standard plain-text `.session` files on disk. Pyrogram session strings are encrypted using **Fernet (AES-128 in CBC mode)** with a custom master key and stored securely in an SQLite database.
*   **Dynamic Chat Simulation** – Organizes user-bots into cyclic communication chains (e.g., Account A ➔ Account B ➔ Account C ➔ Account A) to chat naturally using randomized delays, text variations, and custom daily active hours.
*   **🌐 Proxy Management** – Register and manage SOCKS4/SOCKS5/HTTP proxies with built-in load balancing. You can assign one proxy to up to 6 warmup accounts to maintain safe network boundaries.
*   **✅ Completed Warmups Archive** – Warmup groups that complete all daily scheduled tasks by their end date are moved silently to a dedicated "Completed" (Завершено) screen. Admins can audit them and click "Finish" to release accounts for other tasks.
*   **Google Sheets Integration** – Automatically exports real-time status tables for registered accounts and active warmup tasks so project owners or clients can monitor progress externally.
*   **Docker & Docker-Compose Ready** – Packaged with a multi-stage Docker build for minimal image size and instant deployment.

## 🛠️ Architecture & Tech Stack

```mermaid
graph TD
    Admin[Admin Telegram Account] <-->|Command & Keypad UI| Bot[Aiogram Admin Bot]
    Bot <-->|Database Queries| SQLite[(Encrypted SQLite DB)]
    Bot -->|API Calls / Sync| GSheets[Google Sheets API]
    SQLite <-->|Loads Encrypted Sessions| CM[Pyrogram Client Manager]
    CM <-->|Simulates Conversations| TG[Telegram Servers]
```

*   **Telegram Bot API Framework**: `aiogram` (v3.x)
*   **Telegram Client Framework**: `pyrogram` (v2.x) with `TgCrypto` for maximum performance
*   **Database ORM**: `SQLAlchemy` (v2.x) with `aiosqlite` for asynchronous SQLite access
*   **Encryption Provider**: `cryptography` (Fernet)
*   **Google Sheets API**: `gspread` & `google-auth`
*   **Job Scheduler**: `APScheduler`

## 🔐 Admin Access & Security Model

The system enforces a strict security model to ensure that only authorized users can access the bot control panel and manage sensitive Telegram account sessions.

### Developer/Owner Setup (Configuration Process)
Admins are authorized by mapping their unique Telegram User IDs inside the `.env` configuration file. During deployment, the primary developer or server owner defines the `ADMINS` list.

### Multi-Admin Support
The primary owner can dynamically grant access to other administrators or clients:
1. Obtain the Telegram User ID of the new admin (e.g., via `@userinfobot`).
2. Edit the `.env` file on the hosting server.
3. Append the new ID to the comma-separated `ADMINS` variable.
4. Restart the bot container.

Example config allowing multiple administrators:
```env
ADMINS=123456789,987654321
```

*Note: Any message or callback query originating from a Telegram account whose ID is not explicitly listed in the config will be silently ignored.*

## ⚙️ Configuration Setup (`.env`)

To run the project, create a `.env` file in the root directory. You can copy the template from `.env.example`:

```env
# --- Telegram Bot Config ---
BOT_TOKEN=8030599139:AAHH...           # Admin control bot token from @BotFather
ADMINS=123456789,987654321             # Comma-separated list of admin Telegram IDs

# --- Pyrogram API Config ---
API_ID=1234567                         # Your Telegram developer API ID (from my.telegram.org)
API_HASH=f0e9eca21505c746d2be1cc2...  # Your Telegram developer API Hash

# --- Encryption ---
SESSION_MASTER_KEY=my-super-secret-32-char-key-string  # Secret key to encrypt session strings in DB

# --- Paths ---
DATABASE_PATH=/bot/data/accounts.db    # Path to SQLite database
SESSIONS_DIR=/bot/sessions             # Temp directory for session setup

# --- Google Sheets Integration ---
SPREADSHEET_ID=your_google_sheet_id    # ID of the Google Spreadsheet to sync stats
SERVICE_ACCOUNT_PATH=/bot/data/service_account.json # Path to Google service account credentials JSON

# --- Warmup Defaults ---
LOG_LEVEL=INFO
DB_ECHO=False
```

## 🚀 Installation & Running

### 🐳 Method 1: Using Docker-Compose (Recommended for Production)

Ensure you have **Docker** and **Docker Compose** installed, then:

1. Clone the repository and navigate to its root folder.
2. Put your Google Service Account key in `data/service_account.json` (if using sheets sync).
3. Create your `.env` file containing valid credentials.
4. Start the application in detached mode:
   ```bash
   docker compose up -d --build
   ```
5. To check the logs:
   ```bash
   docker compose logs -f
   ```

### 🐍 Method 2: Manual Installation (For Local Development)

1. Create a Python 3.12 virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python bot/main.py
   ```

---

## 📖 Step-by-Step Usage Guide

### Step 1: Open the Admin Panel
Once the bot is running, send the `/start` command from an authorized admin account. You will be greeted with the main menu:
*   **📱 Accounts** – Authorize and manage Telegram user-bots.
*   **🔥 Warmup** – Organize warmup groups and schedule conversations.

### Step 2: Authorize a New User-Bot Account
1. Click **📱 Accounts** ➔ **➕ Add Account**.
2. Enter the phone number of the Telegram account you want to warm up (e.g., `+79991234567`).
3. The bot will request a verification code sent to that Telegram account.
4. Enter the verification code using the **custom inline keyboard buttons** (do not write it as a chat message). Click **✓ OK**.
5. If the account has Two-Factor Authentication (2FA) enabled, enter the password as a normal text message.
6. The account is now authenticated. The bot will export its session token, encrypt it, save it to the SQLite database, and erase the temporary file from the disk.

### Step 3: Create a Warmup Group
1. Click **🔥 Warmup** ➔ **➕ Create Group**.
2. Enter a name for the group (e.g., "Main Warmup Group").
3. Select at least 2 active user-bot accounts to form the conversation chain. The order in which you pick them will determine the message flow (Account 1 ➔ Account 2 ➔ Account 3 ➔ Account 1).
4. Enter the **Start Date** in `DD.MM.YYYY` format.
5. Enter the **End Date** in `DD.MM.YYYY` format.
6. The bot will automatically generate daily schedules containing random message exchanges during active daytime hours (10:00 - 22:00 by default).
7. Messages are generated from the `data/sentences_list.json` text template database to simulate organic conversation.

### Step 4: Monitor and Manage
*   Inside the **Warmup Details** menu, admins can pause, resume, or delete warmup tasks.
*   Click **📋 Queue** to preview the next 15 scheduled messages, including the exact timestamps and participating accounts.
*   If configured, the bot will periodically export the list of active accounts and group stats to your Google Sheets tables.

### Step 5: Proxy Management
1. Click **🌐 Proxies** in the main menu to view active proxies and their status.
2. Click **➕ Add Proxy** and enter your connection string in any format (e.g. `socks5://user:pass@host:port` or `host:port:user:pass`).
3. Choose a friendly name for the proxy (e.g. `US-Proxy-1`).
4. To link a proxy to a warmup group, select it from the available lists. Proxies will show load indicators (e.g., `[3/6]`) and will automatically become unavailable when 6 accounts are assigned to them to prevent rate limiting.

### Step 6: Completed Warmups Archive
1. When all scheduled messages for a warmup group have run and the end date is reached, the group status changes to `"finished"`.
2. The group will disappear from the active warmup list and move silently to the **✅ Завершено** section.
3. Click **✅ Завершено** from the Warmup menu, select the finished group, and click **🏁 Завершить**. The group will be archived, and the accounts will be released and marked as available for other activities.

## 🔒 Security Practices

1.  **Never commit your `.env` file or `data/` folder.** They are explicitly included in `.gitignore`.
2.  Change your `SESSION_MASTER_KEY` to a random, secure string before starting the bot. If this key is lost, you will not be able to decrypt and load active sessions from the SQLite database.
3.  Keep your Google service account credentials file (`service_account.json`) secure.
