import sqlite3
from datetime import datetime, timedelta

# Connect to the database
conn = sqlite3.connect("raid_teams.db")

cursor = conn.cursor()

# Create tables if they don't exist
cursor.execute('''
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    leader_id INTEGER NOT NULL,
    verified INTEGER DEFAULT 0
)
''')

cursor.execute('''
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


cursor.execute('''
CREATE TABLE IF NOT EXISTS raiders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    team_id INTEGER,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(team_id) REFERENCES teams(id)
)
''')



cursor.execute('''
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    leader_id INTEGER NOT NULL,
    FOREIGN KEY(team_id) REFERENCES teams(id)
)
''')

conn.commit()

# Ensure the raiders table has last_active column
try:
    cursor.execute("ALTER TABLE raiders ADD COLUMN last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    conn.commit()
except sqlite3.OperationalError:
    pass  # Column already exists, so we ignore the error

conn.close()

import sqlite3

conn = sqlite3.connect("raid_teams.db")
cursor = conn.cursor()

# Add the twitter_handle column if it doesn't exist
try:
    cursor.execute("ALTER TABLE raiders ADD COLUMN twitter_handle TEXT")
    conn.commit()
    print("Column 'twitter_handle' added successfully.")
except sqlite3.OperationalError:
    print("Column 'twitter_handle' already exists.")

conn.close()


# Helper function to open database connection
def connect_db():
    return sqlite3.connect("raid_teams.db")

# Functions for managing teams and projects
def create_team(name, leader_id):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO teams (name, leader_id) VALUES (?, ?)", (name, leader_id))
        conn.commit()
        return f"Team '{name}' created successfully."
    except sqlite3.IntegrityError:
        return f"Team '{name}' already exists."
    finally:
        conn.close()

def register_raider(user_id, username, twitter_handle, team_name):
    conn = connect_db()
    cursor = conn.cursor()

    # Get the team ID
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    if not team:
        return f"Team '{team_name}' does not exist."

    team_id = team[0]

    # Check if the user is already in raiders or pending_raiders
    cursor.execute("SELECT id FROM raiders WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        return "You are already a registered raider."

    cursor.execute("SELECT id FROM pending_raiders WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        return "Your registration is pending approval."

    # Insert into pending_raiders
    cursor.execute("INSERT INTO pending_raiders (user_id, username, twitter_handle, team_id) VALUES (?, ?, ?, ?)",
                   (user_id, username, twitter_handle, team_id))
    conn.commit()
    conn.close()
    return f"Registration request submitted for '{username}'. Waiting for team lead approval."


def approve_raider(user_id, leader_id):
    conn = connect_db()
    cursor = conn.cursor()

    # Check if the user is in pending_raiders
    cursor.execute("SELECT username, twitter_handle, team_id FROM pending_raiders WHERE user_id = ?", (user_id,))
    pending = cursor.fetchone()

    if not pending:
        return "No pending request found for this raider."

    username, twitter_handle, team_id = pending

    # Check if the leader is authorized to approve (must be leader of the team)
    cursor.execute("SELECT leader_id FROM teams WHERE id = ?", (team_id,))
    team_leader = cursor.fetchone()
    
    if not team_leader or team_leader[0] != leader_id:
        return "You are not authorized to approve raiders for this team."

    # Move raider from pending to raiders table
    cursor.execute("INSERT INTO raiders (user_id, username, twitter_handle, team_id) VALUES (?, ?, ?, ?)",
                   (user_id, username, twitter_handle, team_id))

    # Remove from pending
    cursor.execute("DELETE FROM pending_raiders WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()
    return f"Raider '{username}' has been approved and added to the team!"

    
def list_pending_raiders(team_name):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    
    if not team:
        return f"Team '{team_name}' does not exist."
    
    team_id = team[0]
    cursor.execute("SELECT username FROM pending_raiders WHERE team_id = ?", (team_id,))
    pending = cursor.fetchall()
    conn.close()
    
    return f"Pending Raiders for '{team_name}':\n" + "\n".join(p[0] for p in pending) if pending else "No pending raiders."

def reject_raider(user_id, leader_id):
    conn = connect_db()
    cursor = conn.cursor()

    # Check if the user is in pending_raiders
    cursor.execute("SELECT username, team_id FROM pending_raiders WHERE user_id = ?", (user_id,))
    pending = cursor.fetchone()

    if not pending:
        return "No pending request found for this raider."

    username, team_id = pending

    # Check if the leader is authorized to reject
    cursor.execute("SELECT leader_id FROM teams WHERE id = ?", (team_id,))
    team_leader = cursor.fetchone()
    
    if not team_leader or team_leader[0] != leader_id:
        return "You are not authorized to reject raiders for this team."

    # Remove from pending
    cursor.execute("DELETE FROM pending_raiders WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()
    return f"Raider '{username}' has been rejected."


def join_team(user_id, username, team_name):
    conn = connect_db()
    cursor = conn.cursor()
    
    # Check if team exists
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    if not team:
        conn.close()
        return f"Team '{team_name}' does not exist."

    team_id = team[0]

    # Check if user is approved
    cursor.execute("""
        SELECT status FROM raiders WHERE user_id = ? AND team_id = ?
    """, (user_id, team_id))
    status = cursor.fetchone()
    
    if not status or status[0] != "approved":
        conn.close()
        return "You have not been approved to join this team."

    # Add user to the team
    cursor.execute("""
        UPDATE raiders SET status = 'approved' WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()
    return f"User '{username}' has officially joined team '{team_name}'!"


def list_teams():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM teams")
    teams = cursor.fetchall()
    conn.close()
    return "Teams:\n" + "\n".join(team[0] for team in teams) if teams else "No teams available."

def view_team(team_name):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    team = cursor.fetchone()
    
    if not team:
        conn.close()
        return f"Team '{team_name}' does not exist."
    
    team_id = team[0]
    cursor.execute("SELECT username FROM raiders WHERE team_id = ?", (team_id,))
    members = cursor.fetchall()
    conn.close()
    return f"Members of '{team_name}':\n" + "\n".join(m[0] for m in members) if members else f"No members in '{team_name}'."

def create_project(team_name, project_name, leader_id):
    conn = connect_db()
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

def list_projects(team_name):
    conn = connect_db()
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
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teams WHERE name = ? AND leader_id = ?", (team_name, leader_id))
    conn.commit()
    conn.close()
    return f"Team '{team_name}' removed successfully."

def leave_team(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE raiders SET team_id = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return "You have left your team."


def remove_inactive():
    conn = connect_db()
    cursor = conn.cursor()
    two_weeks_ago = datetime.now() - timedelta(weeks=2)
    cursor.execute("DELETE FROM raiders WHERE last_active < ?", (two_weeks_ago,))
    removed_count = cursor.rowcount
    conn.commit()
    conn.close()
    return f"Removed {removed_count} inactive members."

def leaderboard():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM raiders ORDER BY last_active DESC LIMIT 10")
    top_raiders = cursor.fetchall()
    conn.close()
    return "Leaderboard:\n" + "\n".join(raider[0] for raider in top_raiders) if top_raiders else "No active raiders."

def swap_raiders(raider1, raider2):
    conn = connect_db()
    cursor = conn.cursor()
    
    # Get raider1's team
    cursor.execute("SELECT team_id FROM raiders WHERE username = ?", (raider1,))
    team1 = cursor.fetchone()
    
    # Get raider2's team
    cursor.execute("SELECT team_id FROM raiders WHERE username = ?", (raider2,))
    team2 = cursor.fetchone()
    
    if not team1 or not team2:
        conn.close()
        return "One or both raiders not found."
    
    # Swap teams
    cursor.execute("UPDATE raiders SET team_id = ? WHERE username = ?", (team2[0], raider1))
    cursor.execute("UPDATE raiders SET team_id = ? WHERE username = ?", (team1[0], raider2))
    
    conn.commit()
    conn.close()
    return f"Swapped {raider1} and {raider2}."

def verify_team(team_name):
    conn = connect_db()
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
