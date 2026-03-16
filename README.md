# ⚔️ SiegeSync: War Attendance Tracker

SiegeSync is a specialized Discord bot designed to manage attendance for guild wars and sieges, likely for games such as Black Desert Online. It provides an automated, interactive, and persistent system for players to sign up for various roles and classes.

The bot is built with `discord.py` and is designed for easy deployment using Docker.

##  Features

- **Automated Scheduling**: Automatically posts the next day's attendance sheet at a set time (10 PM GMT+8) and locks the current day's sheet at the event time (9 PM GMT+8).
- **Interactive UI**: Uses modern Discord UI components like Buttons and Select Menus for a smooth user experience.
- **Role-Based Sign-ups**: Players can sign up for specific roles: `Shot Caller`, `Main Ball`, `Flex`, `Def Team`, or mark themselves as `Absent`.
- **Class Selection**: After choosing a role, players select their specific class. The bot remembers a user's last-used class for faster sign-ups.
- **Dynamic Capping System**:
  - Manages different attendance caps for T1/T2 wars.
  - Automatically places users in a `Reserves` list when the main roster is full.
  - Enforces a unique `Shot Caller` and a fixed-size `Def Team`.
- **Persistent State**: The bot saves all attendance data to a `attendance_data.json` file and reloads its state on restart, meaning active attendance sheets remain fully functional even after bot downtime.
- **Dockerized**: Comes with a `Dockerfile` and `docker-compose.yml` for simple, one-command deployment.
- **Admin Commands**: Provides slash commands for administrators to manually post sheets, change tiers, and reset attendance.

---

##  Getting Started

The recommended way to run SiegeSync is with Docker and Docker Compose, as it handles all dependencies and ensures a consistent environment.

### Prerequisites

- **Git**: To clone the repository.
- **Docker Desktop**: To build and run the container.
- **Discord Bot Token**: You need to create a bot application in the Discord Developer Portal.

### Installation Steps

1.  **Clone the Repository**
    ```sh
    git clone https://github.com/your-username/War-Attendance-Tracker.git
    cd War-Attendance-Tracker
    ```

2.  **Create a Discord Bot**
    - Go to the Discord Developer Portal.
    - Create a new application.
    - Go to the "Bot" tab and click "Add Bot".
    - **Enable the `SERVER MEMBERS INTENT`** under "Privileged Gateway Intents". This is required for the bot to see member display names.
    - Reset and copy the **Bot Token**. You will need this in the next step.

3.  **Configure Environment Variables**
    - Create a new file named `.env` in the project directory.
    - Copy the contents of the example below into your `.env` file and fill in the values.

    ```env
    # .env file

    # Your Discord Bot Token from the developer portal
    DISCORD_BOT_TOKEN="your_bot_token_here"

    # The ID of the server (guild) where the bot will run
    GUILD_ID="your_server_id_here"

    # The ID of the channel where attendance sheets will be posted
    ANNOUNCE_CHANNEL_ID="your_announcement_channel_id_here"

    # The ID of the channel for posting daily summary logs
    LOG_CHANNEL_ID="your_log_channel_id_here"

    # The ID of your main guild chat for sending signup notifications
    GUILD_CHAT_ID="your_guild_chat_id_here"

    # The ID of the role to @mention when a new sheet is posted
    MENTION_ROLE_ID="your_mention_role_id_here"
    ```
    > **Tip**: To get IDs in Discord, enable Developer Mode in `User Settings > Advanced`, then right-click a server, channel, or role and select "Copy ID".

4.  **Build and Run the Bot**
    - Open a terminal in the project directory and run the following command:
    ```sh
    docker-compose up -d
    ```
    - This command will build the Docker image and start the bot container in the background.

5.  **Invite the Bot**
    - When the bot starts for the first time, it will print an invite link in the Docker logs. You can view the logs via Docker Desktop or by running `docker-compose logs`.
    - Use this link to add the bot to your server. The slash commands should appear shortly after.

---

## ⚙️ Usage

### Automated Flow

- **Daily Post**: At 10:00 PM (GMT+8), the bot posts the attendance sheet for the *next* day in the announcement channel.
- **Daily Lock**: At 9:00 PM (GMT+8), the bot locks the attendance sheet for the *current* day by removing the buttons, and posts a final summary in the log channel.

### Slash Commands

The bot is controlled via the following slash commands:

- `/post_now`
  - Manually posts the attendance sheet for the current day. Useful if the bot was offline during its scheduled post time.

- `/post_tomorrow`
  - Manually posts attendance sheet for the next day if the war ends early. 
  
- `/summary [date]`
  - Posts or updates the attendance summary for a specific date (defaults to today) in the log channel.

- `/change_tier <tier>`
  - Changes the attendance cap tier for the current day.
  - **Options**: `T1`, `T2`.

- `/reset_today`
  - **DANGER**: Completely clears all sign-ups for the current day. This is irreversible.

### Managing the Bot

- **To stop the bot**:
  ```sh
  docker-compose down
  ```
- **To view logs**:
  ```sh
  docker-compose logs -f
  ```
- **To update the bot after code changes**:
  ```sh
  docker-compose up -d --build
  ```

---

## 📁 Project Structure

```
├── .
├── bot.py                  # Main bot application logic
├── Dockerfile              # Instructions to build the Docker image
├── docker-compose.yml      # Defines the Docker service for easy management
├── requirements.txt        # Python package dependencies
├── .env                    # (You create this) Stores secrets and config
└── attendance_data.json    # (Auto-generated) The database file for all sign-ups
```