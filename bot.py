import os
import logging
import sqlite3  
import random
from collections import defaultdict
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMember
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ChatMemberHandler
from database import (
    connect_teams_db, connect_bot_db, create_team, list_teams, view_team, create_project, list_projects,
    remove_team, leave_team, remove_inactive, leaderboard, verify_team, register_raider, save_reaction
)

# Configuration
TOKEN = "7846706967:AAFuL6C3XHqhr6d7UZ-3BKb80AJruEjHgsA"

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Save project to database
def save_project(chat_id, project_name, leads, raiders):
    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO projects (chat_id, project_name, leads, raiders)
        VALUES (?, ?, ?, ?)
    """, (chat_id, project_name, "\n".join(leads), "\n".join(raiders)))
    conn.commit()
    conn.close()

# Check if user is admin
async def is_admin(chat_id: int, user_id: int, bot) -> bool:
    """
    Check if a user is an admin or owner in a specific chat.

    Args:
        chat_id (int): The ID of the chat (group or supergroup).
        user_id (int): The ID of the user to check.
        bot: The bot instance.

    Returns:
        bool: True if the user is an admin or owner, False otherwise.
    """
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ["administrator", "creator"]
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False

# Send a message to the chat and return the Message object
async def send_message(update: Update, text: str, reply_markup=None):
    """
    Send a message to the chat and return the Message object.

    Args:
        update (Update): The update object from Telegram.
        text (str): The text to send.
        reply_markup (Optional): InlineKeyboardMarkup or ReplyKeyboardMarkup.

    Returns:
        Message: The sent message object.
    """
    return await update.message.reply_text(text, reply_markup=reply_markup)

# Handle project list messages
async def handle_project_list(update: Update, context: CallbackContext):
    # Check if the user is an admin
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if not await is_admin(chat_id, user_id, context.bot):
        await send_message(update, "❌ Only admins can post project lists.")
        return

    # Parse the message
    message_text = update.message.text
    
    # Extract project name, leads, and raiders
    try:
        lines = message_text.split("\n")
        project_name = lines[0].replace("/CP", "").strip()
        leads = [line.strip() for line in lines[2:6]]  # Lines 2 and 3 are leads
        raiders = [line.strip() for line in lines[7:]]  # Lines 5 onwards are raiders
    except Exception as e:
        await send_message(update, f"❌ Error parsing the message: {e}")
        return

    # Save to database
    save_project(chat_id, project_name, leads, raiders)

    # Format the output message
    leads_str = '\n'.join(leads)
    raiders_str = '\n'.join(raiders)
    formatted_message = (
        f"/CP {project_name}\n\n"
        f"LEADS\n"
        f"{leads_str}\n\n"
        f"RAIDERS\n"
        f"{raiders_str}"
    )

    # Repost the message and get the Message object
    sent_message = await send_message(update, formatted_message)

    # Pin the message
    await context.bot.pin_chat_message(chat_id, sent_message.message_id)

# View projects in the group
async def view_project_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    # Fetch projects for the current group
    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT project_name, leads, raiders FROM projects WHERE chat_id = ?", (chat_id,))
    projects = cursor.fetchall()
    conn.close()

    if not projects:
        await send_message(update, "No projects found for this group.")
        return

    # Format the projects into a message
    projects_message = "📋 Projects in this group:\n\n"
    for project in projects:
        project_name, leads, raiders = project
        projects_message += (
            f"🟥🟥 {project_name} 🟥🟥\n"
            f"LEADS\n{leads}\n\n"
            f"RAIDERS\n{raiders}\n\n"
        )

    await send_message(update, projects_message)

# Update a project
async def swap_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is an admin
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if not await is_admin(chat_id, user_id, context.bot):
        await send_message(update, "❌ Only admins can update projects.")
        return

    # Debug: Print the arguments
    print(f"Arguments: {context.args}")

    # Check if the command has the correct number of arguments
    if len(context.args) < 3 or len(context.args) % 2 != 1:
        await send_message(update, "Usage: /swap <project_name> <old_raider/lead> <new_raider/lead> [<old_raider/lead> <new_raider/lead> ...]")
        return

    # Parse the arguments
    project_name = " ".join(context.args[:-len(context.args) + 1])  # Join all arguments except the last pairs
    swap_pairs = list(zip(context.args[-len(context.args) + 1::2], context.args[-len(context.args) + 2::2]))  # Pair old and new members

    # Debug: Print the parsed arguments
    print(f"Project Name: {project_name}")
    print(f"Swap Pairs: {swap_pairs}")

    # Fetch the project from the database
    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT leads, raiders FROM projects WHERE chat_id = ? AND project_name = ?", (chat_id, project_name))
    project = cursor.fetchone()

    if not project:
        await send_message(update, f"❌ Project '{project_name}' not found.")
        conn.close()
        return

    leads, raiders = project

    # Update leads or raiders
    leads_list = leads.split("\n")
    raiders_list = raiders.split("\n")

    for old_member, new_member in swap_pairs:
        if old_member in leads_list:
            # Update leads
            leads_list = [new_member if member == old_member else member for member in leads_list]
        elif old_member in raiders_list:
            # Update raiders
            raiders_list = [new_member if member == old_member else member for member in raiders_list]
        else:
            await send_message(update, f"❌ Member '{old_member}' not found in project '{project_name}'.")
            conn.close()
            return

    # Save the updated leads and raiders
    updated_leads = "\n".join(leads_list)
    updated_raiders = "\n".join(raiders_list)
    cursor.execute("UPDATE projects SET leads = ?, raiders = ? WHERE chat_id = ? AND project_name = ?", (updated_leads, updated_raiders, chat_id, project_name))

    # Commit changes to the database
    conn.commit()
    conn.close()

    # Fetch the updated project
    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT leads, raiders FROM projects WHERE chat_id = ? AND project_name = ?", (chat_id, project_name))
    updated_project = cursor.fetchone()
    conn.close()

    if not updated_project:
        await send_message(update, f"❌ Failed to fetch updated project '{project_name}'.")
        return

    updated_leads, updated_raiders = updated_project

    # Format the updated project message
    formatted_message = (
        f"/CP {project_name}\n\n"
        f"LEADS\n"
        f"{updated_leads}\n\n"
        f"RAIDERS\n"
        f"{updated_raiders}"
    )

    # Repost the updated message
    sent_message = await send_message(update, formatted_message)

    # Pin the updated message
    await context.bot.pin_chat_message(chat_id, sent_message.message_id)

    # Notify the group
    await send_message(update, f"✅ Project '{project_name}' updated successfully!")


# Database setup
def init_db():
    conn = sqlite3.connect('reactions.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reactions (
            message_id INTEGER,
            user_id INTEGER,
            username TEXT,
            timestamp TEXT,
            PRIMARY KEY (message_id, user_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# React Command
# Command to send a message with a reaction button
async def react_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔥 React!", callback_data='react_button')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = await update.message.reply_text("Click the button to participate:", reply_markup=reply_markup)
    context.user_data['react_message_id'] = message.message_id

# Callback for the reaction button
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        conn = sqlite3.connect('reactions.db')
        cursor = conn.cursor()
        timestamp = datetime.now().isoformat()
        cursor.execute('''
            INSERT OR REPLACE INTO reactions 
            (message_id, user_id, username, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (query.message.message_id, query.from_user.id, 
              query.from_user.username, timestamp))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            text=f"✅ @{query.from_user.username} reacted!",
            reply_markup=query.message.reply_markup
        )
    except Exception as e:
        print(f"Error: {e}")
        await query.edit_message_text(
            text="❌ Failed to save reaction. Please try again.",
            reply_markup=query.message.reply_markup
        )



# Auto-Pick Command
async def auto_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select participants with early reaction bias"""
    # Check if the command is used in reply to a message
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a reaction message!")
        return
    
    # Get the message ID of the replied-to message
    message_id = update.message.reply_to_message.message_id
    
    # Get reactions from the database
    conn = sqlite3.connect('reactions.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT username, timestamp 
        FROM reactions 
        WHERE message_id = ?
        ORDER BY timestamp
    ''', (message_id,))
    reactors = cursor.fetchall()
    conn.close()
    
    # Check if there are any reactions
    if not reactors:
        await update.message.reply_text("No reactions found!")
        return
    
    # Create a weighted list (earlier reactors have higher weight)
    weights = [1 / (i + 1) ** 2 for i in range(len(reactors))]  # Weight decreases with position
    
    # Default to 3 picks if no number is specified
    try:
        num_picks = min(int(context.args[0]), len(reactors)) if context.args else 3
    except ValueError:
        await update.message.reply_text("❌ Invalid number of picks. Usage: /auto_pick <number>")
        return
    
    # Select participants using weighted random choice
    selected = random.choices(
        [r[0] for r in reactors],  # List of usernames
        weights=weights,           # Weights based on reaction order
        k=num_picks                # Number of participants to pick
    )
    
    # Remove duplicates while preserving order
    seen = set()
    unique_selected = [x for x in selected if not (x in seen or seen.add(x))]
    
   # Fun phrases to add at the end
    fun_phrases = [
        "Make una no dull me o! 😂",
        "Who go carry last? 🏃‍♂️",
        "E no easy to be winner o! 🏆",
        "Sharp guys dey win always! 🔥"
    ]
    
    # Format the response message
    response = (
        f"💀Omor, Tension everywhere\n\n"
        f"😎 But I don select {len(unique_selected)} raiders wey react sharp sharp\n\n" +
        "\n".join(f" @{username} " for username in unique_selected) +
        f"\n\n{random.choice(fun_phrases)}"
    )
    
    # Send the response
    await update.message.reply_text(response)

async def sp_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    
    if not context.args:
        await send_message(update, "❌ Please specify a project name\nUsage: /sp <project_name>")
        return
        
    project_name = " ".join(context.args)

    # Get project details
    with connect_bot_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT leads, raiders 
            FROM projects 
            WHERE chat_id = ? AND project_name = ?
        """, (chat_id, project_name))
        project = cursor.fetchone()

    if not project:
        await send_message(update, f"❌ Project '{project_name}' not found")
        return

    # Process leads and raiders
    leads = project[0].split('\n') if project[0] else []
    raiders = project[1].split('\n') if project[1] else []

    # Format message
leads_list = '\n'.join(leads) if leads else 'No leads assigned 🌟'
raiders_list = '\n'.join(raiders) if raiders else 'No raiders assigned 🌟'

    message = (
    f"🟥🟥 {project_name} 🟥🟥\n\n"
    f"✨ LEADS ✨\n{leads_list}\n\n"
    f"🔥 RAIDERS 🔥\n{raiders_list}\n\n"
    f"🕒 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    await send_message(update, message)

# Command Handlers
async def start(update: Update, context: CallbackContext) -> None:
    # Create a single button for "ADD ME TO CHAT"
    keyboard = [
        [InlineKeyboardButton("➕ ADD ME TO YOUR RAID GROUP", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the welcome message with the button
    await send_message(
        update,
        "👋 Hey there! I am GROK, the ultimate tool for shill raiding management.\n\n"
        "I’m here to help you:\n"
        "🔸 Create and manage raid teams\n"
        "🔸 Verify and approve raiders\n"
        "🔸 Track engagement and leaderboard rankings\n"
        "🔸 Manage projects and assign LEADS\n"
        "🔸 Swap raiders seamlessly\n\n"
        "Click the /help command to get started! 🚀",
        reply_markup=reply_markup
    )

async def help_command(update_or_query, context: CallbackContext) -> None:
    help_text = """
    Available Commands:
    /create_team <team_name> - Create a new team
    /list_teams - View all teams
    /view_team <team_name> - View members of a team
    /CP - Create a project
    /swap - Swap raiders IN AND OUT of projects
    /remove_team <team_name> - Remove a team (only leader can do this)
    /leave_team <team_name> - Leave a team
    /remove_inactive - Remove inactive members
    /leaderboard - View the leaderboard
    /verify_team <team_name> - Verify a team
    /register_raider <team_name> <username> - Register a raider
    """
    # Check if the input is a query or an update
    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(help_text)
    else:
        await update_or_query.edit_message_text(help_text)  # For callback queries

async def create_team_command(update: Update, context: CallbackContext):
    if not context.args:
        await send_message(update, "Usage: /create_team <team_name>")
        return
    
    team_name = " ".join(context.args)  # Capture team name from command args
    leader_id = update.effective_user.id  # Get the Telegram user ID

    result = create_team(team_name, leader_id)  # Call function with both arguments
    await send_message(update, result)  # Send response message

async def list_pending_raiders_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Check if user is a team leader
    conn = connect_teams_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE leader_id = ?", (user_id,))
    team = cursor.fetchone()
    
    if not team:
        await send_message(update, "You are not a team leader.")
        return
    
    team_id = team[0]
    cursor.execute("SELECT user_id, username, twitter_handle FROM pending_raiders WHERE team_id = ?", (team_id,))
    pending_raiders = cursor.fetchall()
    conn.close()
    
    if not pending_raiders:
        await update.message.reply_text("No pending raiders.")
        return

    keyboard = []
    for raider_id, raider_username in pending_raiders:
        approve_button = InlineKeyboardButton(f"✅ Approve {raider_username}", callback_data=f"approve_{raider_id}")
        reject_button = InlineKeyboardButton(f"❌ Reject {raider_username}", callback_data=f"reject_{raider_id}")
        keyboard.append([approve_button, reject_button])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pending Raider Approvals:", reply_markup=reply_markup)

async def handle_approval_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    action, user_id = query.data.split("_")

    conn = connect_teams_db()
    cursor = conn.cursor()

    if action == "approve":
        cursor.execute("UPDATE raiders SET approved = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Raider {user_id} has been approved!")
    elif action == "reject":
        cursor.execute("DELETE FROM raiders WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.edit_message_text(f"❌ Raider {user_id} has been rejected!")

    conn.close()
    await query.answer()

async def register_raider_command(update: Update, context: CallbackContext):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /register <team_name> <twitter_handle>")
        return

    team_name = context.args[0]
    twitter_handle = context.args[1].lstrip('@')
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    if not username:
        await update.message.reply_text("❌ You need a Telegram username to register!")
        return

    response = register_raider(user_id, username, twitter_handle, team_name)
    await update.message.reply_text(response)


async def list_teams_command(update: Update, context: CallbackContext) -> None:
    await send_message(update, list_teams())

async def view_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, "Usage: /view_team <team_name>")
        return
    team_name = context.args[0]
    await send_message(update, view_team(team_name))

async def create_project_command(update: Update, context: CallbackContext):
    args = context.args
    if len(args) < 2:
        await send_message(update, "Usage: /create_project <team_name> <project_name>")
        return

    team_name = args[0]
    project_name = " ".join(args[1:])
    leader_id = update.effective_user.id  # Get the user ID of the command sender

    result = create_project(team_name, project_name, leader_id)
    await send_message(update, result)

async def list_projects_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, "Usage: /list_projects <team_name>")
        return
    team_name = context.args[0]
    await send_message(update, list_projects(team_name))

async def remove_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, "Usage: /remove_team <team_name>")
        return
    team_name = context.args[0]
    leader_id = update.effective_user.id
    await send_message(update, remove_team(team_name, leader_id))

async def leave_team_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    await send_message(update, leave_team(user_id))

async def remove_inactive_command(update: Update, context: CallbackContext) -> None:
    await send_message(update, remove_inactive())

async def leaderboard_command(update: Update, context: CallbackContext) -> None:
    await send_message(update, leaderboard())

async def error_handler(update: Update, context: CallbackContext):
    error = context.error
    if update and update.message:
        await update.message.reply_text(f"⚠️ Error: {str(error)}")
    else:
        print(f"Unhandled error: {error}")

async def verify_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, "Usage: /verify_team <team_name>")
        return
    team_name = context.args[0]
    await send_message(update, verify_team(team_name))

# Main Function
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("react", react_command))
    application.add_handler(CommandHandler("auto_pick", auto_pick))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Add handlers
    handlers = [
        ("start", start),
        ("help", help_command),
        ("create_team", create_team_command),
        ("list_teams", list_teams_command),
        ("view_team", view_team_command),
        ("create_project", create_project_command),
        ("list_projects", list_projects_command),
        ("remove_team", remove_team_command),
        ("leave_team", leave_team_command),
        ("remove_inactive", remove_inactive_command),
        ("leaderboard", leaderboard_command),
        ("swap", swap_command),
        ("verify_team", verify_team_command),
        ("sp", sp_command),
        ("auto_pick", auto_pick),
        ("react", react_command),
        ("button", button_callback),
        ("register_raider", register_raider_command),
        ("view_project", view_project_command)
    ]
    for command, handler in handlers:
        application.add_handler(CommandHandler(command, handler))
        application.add_handler(CommandHandler("react", react_command))
        application.add_handler(CommandHandler("auto_pick", auto_pick))

    # Add message handler for project lists
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\/CP"), handle_project_list))
     
    # Add callback query handler for approval buttons
    application.add_handler(CallbackQueryHandler(handle_approval_callback))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
