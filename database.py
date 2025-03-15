import sqlite3
from dataclasses import dataclass
from sqlite3 import connect, OperationalError
import time
from datetime import datetime, timedelta

# Database file names
TEAMS_DATABASE = "raid_teams.db"
BOT_DATABASE = "raid_bot.db"

# Initialize databases
def init_db():
    # Initialize raid_teams.db
    conn_teams = sqlite3.connect(TEAMS_DATABASE)
    cursor_teams = conn_teams.cursor()

    # Create teams table
    cursor_teams.execute('''
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        leader_id INTEGER NOT NULL,
        verified INTEGER DEFAULT 0
    )
    ''')

    # Create team_members table
    cursor_teams.execute('''
    CREATE TABLE IF NOT EXISTS team_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        FOREIGN KEY (team_id) REFERENCES teams(id)
    )
    ''')

    # Create pending_raiders table
    cursor_teams.execute('''
    CREATE TABLE IF NOT EXISTS pending_raiders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        username TEXT NOT NULL,
        twitter_handle TEXT,
        team_id INTEGER NOT NULL,
        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    ''')

    # Create raiders table
    cursor_teams.execute('''
    CREATE TABLE IF NOT EXISTS raiders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        username TEXT,
        team_id INTEGER,
        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    ''')

    

    # Commit and close
    conn_teams.commit()
    conn_teams.close()

    # Initialize raid_bot.db
    conn_bot = sqlite3.connect(BOT_DATABASE)
    cursor_bot = conn_bot.cursor()
    

    # Create projects table
    cursor_bot.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        project_name TEXT NOT NULL,
        leads TEXT NOT NULL,
        raiders TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor_bot.execute('''
    CREATE TABLE IF NOT EXISTS reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        timestamp REAL NOT NULL
)
    ''')

    # Commit and close
    conn_bot.commit()
    conn_bot.close()

from sqlite3 import OperationalError
import time

def safe_db_operation(func):
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_delay = 0.5
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                raise
        return None
    return wrapper

# Helper function to open team database connection
def connect_teams_db():
    return sqlite3.connect(TEAMS_DATABASE)

# Helper function to open bot database connection
def connect_bot_db():
    return sqlite3.connect(BOT_DATABASE)

def save_project(chat_id, project_name, leads, raiders):
    conn = connect_bot_db()
    cursor = conn.cursor()
    
    # Convert lists to properly formatted strings
    leads_str = '\n'.join(leads) if leads else ''
    raiders_str = '\n'.join(raiders) if raiders else ''
    
    cursor.execute("""
        INSERT INTO projects (chat_id, project_name, leads, raiders)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id, project_name) DO UPDATE SET
            leads = excluded.leads,
            raiders = excluded.raiders
    """, (chat_id, project_name, leads_str, raiders_str))
    
    conn.commit()
    conn.close()

# Functions for managing teams and projects
def create_team(name, leader_id):
    conn = connect_teams_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO teams (name, leader_id) VALUES (?, ?)", (name, leader_id))
        conn.commit()
        return f"Team '{name}' created successfully."
    except sqlite3.IntegrityError:
        return f"Team '{name}' already exists."
    finally:
        conn.close()

@safe_db_operation
def connect_teams_db():
    return connect(
        "raid_teams.db",
        timeout=30,  # Increased timeout for busy operations
        check_same_thread=False,
        isolation_level=None  # Better concurrency control
    )

def with_retry(max_attempts=3, delay=0.5):
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "locked" in str(e):
                        attempts += 1
                        time.sleep(delay * attempts)
                        continue
                    raise
            return None
        return wrapper
    return decorator

@with_retry(max_attempts=5, delay=0.3)
def register_raider(user_id, username, twitter_handle, team_name):
    try:
        with connect_teams_db() as conn:
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")  # Explicit transaction start
            
            # Existing checks
            cursor.execute("SELECT 1 FROM raiders WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                return "✅ Already registered!"
                
            # Team check
            cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
            team = cursor.fetchone()
            if not team:
                return f"❌ Team {team_name} not found"
            
            # Format handle
            twitter_handle = twitter_handle.lstrip('@')
            
            # Insert with error handling
            cursor.execute("""
                INSERT INTO raiders 
                (user_id, username, twitter_handle, team_id)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, f"@{twitter_handle}", team[0]))
            
            conn.commit()
            return f"🎉 Registered in {team_name}!"
            
    except OperationalError as e:
        return f"🔒 Database busy - please try again in 10 seconds"
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"

def list_teams():
    conn = connect_teams_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM teams")
    teams = cursor.fetchall()
    conn.close()
    return "Teams:\n" + "\n".join(team[0] for team in teams) if teams else "No teams available."

def view_team(team_name):
    conn = connect_teams_db()
    cursor = conn.cursor()
    
    # Get team members
    cursor.execute("""
        SELECT username 
        FROM raiders 
        WHERE team_id = (
            SELECT id FROM teams WHERE name = ?
        )
    """, (team_name,))
    
    members = cursor.fetchall()
    conn.close()
    
    if not members:
        return f"No members in {team_name}"
    
    return "\n".join(member[0] for member in members)

# Add this function
def save_reaction(message_id, username):
    """Save a reaction to the database"""
    try:
        conn = connect_bot_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reactions (message_id, username, timestamp)
            VALUES (?, ?, ?)
        ''', (message_id, username, datetime.now().timestamp()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving reaction: {e}")
        return False

def create_project(team_name, project_name, leader_id):
    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    
    if not team:
        conn.close()
        return f"Team '{team_name}' does not exist."
    
    team_id = team[0]
    cursor.execute("INSERT INTO projects (name, team_id, leader_id) VALUES (?, ?, ?)", (project_name, team_id, leader_id))
    conn.commit()
    conn.close()
    return f"Project '{project_name}' created under team '{team_name}' successfully!"

def delete_project(chat_id: int, project_name: str) -> str:
    """
    Delete a project from the database.
    
    Args:
        chat_id (int): The chat ID where the project exists.
        project_name (str): The name of the project to delete.
    
    Returns:
        str: Success or error message.
    """
    conn = connect_bot_db()
    cursor = conn.cursor()
    
    try:
        # Check if the project exists
        cursor.execute('''
            SELECT id FROM projects 
            WHERE chat_id = ? AND project_name = ?
        ''', (chat_id, project_name))
        project = cursor.fetchone()
        
        if not project:
            return f"❌ Project '{project_name}' not found!"
        
        # Delete the project
        cursor.execute('''
            DELETE FROM projects 
            WHERE chat_id = ? AND project_name = ?
        ''', (chat_id, project_name))
        
        conn.commit()
        return f"✅ Project '{project_name}' deleted successfully!"
    except Exception as e:
        conn.rollback()
        return f"❌ Error deleting project: {str(e)}"
    finally:
        conn.close()

def list_projects(team_name):
    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    
    if not team:
        return f"Team '{team_name}' does not exist."
    
    team_id = team[0]
    cursor.execute("SELECT name FROM projects WHERE team_id = ?", (team_id,))
    projects = cursor.fetchall()
    conn.close()
    return f"Projects under '{team_name}':\n" + "\n".join(p[0] for p in projects) if projects else f"No projects found for team '{team_name}'."

def remove_team(team_name, leader_id):
    conn = connect_teams_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teams WHERE name = ? AND leader_id = ?", (team_name, leader_id))
    conn.commit()
    conn.close()
    return f"Team '{team_name}' removed successfully."

def leave_team(user_id):
    conn = connect_teams_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE raiders SET team_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return "You have left your team."

def remove_inactive():
    conn = connect_teams_db()
    cursor = conn.cursor()
    two_weeks_ago = datetime.now() - timedelta(weeks=2)
    cursor.execute("DELETE FROM raiders WHERE last_active < ?", (two_weeks_ago,))
    removed_count = cursor.rowcount
    conn.commit()
    conn.close()
    return f"Removed {removed_count} inactive members."

def leaderboard():
    conn = connect_teams_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM raiders ORDER BY last_active DESC LIMIT 10")
    top_raiders = cursor.fetchall()
    conn.close()
    return "🏆 Leaderboard 🏆\n" + "\n".join(raider[0] for raider in top_raiders) if top_raiders else "No active raiders."

def verify_team(team_name):
    conn = connect_teams_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    
    if not team:
        conn.close()
        return f"Team '{team_name}' does not exist."
    
    team_id = team[0]
    cursor.execute("SELECT COUNT(*) FROM raiders WHERE team_id = ?", (team_id,))
    member_count = cursor.fetchone()[0]
    
    if member_count >= 80:
        cursor.execute("UPDATE teams SET verified = 1 WHERE id = ?", (team_id,))
        conn.commit()
        conn.close()
        return f"Team '{team_name}' has been verified!"
    else:
        conn.close()
        return f"Team '{team_name}' does not have enough members for verification."
 

def init_db():
    conn = sqlite3.connect('raids.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS raids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            tweet_id TEXT NOT NULL,
            goals TEXT NOT NULL,
            progress TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def init_db():
    conn = sqlite3.connect('raids.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_balances (
            user_id INTEGER,
            username TEXT,
            project_name TEXT,
            balance INTEGER DEFAULT 0,
            week INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, project_name)
        )
    ''')
    conn.commit()
    conn.close()
