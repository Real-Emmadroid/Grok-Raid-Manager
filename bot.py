import os
import logging
import sqlite3
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext, ContextTypes
)
from database import (
    connect_teams_db, connect_bot_db, create_team, list_teams, view_team, create_project, list_projects,
    remove_team, leave_team, remove_inactive, leaderboard, verify_team, register_raider
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
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ["administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

# Send a message to the chat and return the Message object
async def send_message(update: Update, text: str, reply_markup=None):
    return await update.message.reply_text(text, reply_markup=reply_markup)

# Handle project list messages
async def handle_project_list(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if not await is_admin(chat_id, user_id, context.bot):
        await send_message(update, "❌ Only admins can post project lists.")
        return

    try:
        lines = update.message.text.split("\n")
        project_name = lines[0].replace("/CP", "").strip()
        leads = [line.strip() for line in lines[2:6]]  # Lines 2 and 3 are leads
        raiders = [line.strip() for line in lines[7:]]  # Lines 5 onwards are raiders
    except Exception as e:
        await send_message(update, f"❌ Error parsing the message: {e}")
        return

    save_project(chat_id, project_name, leads, raiders)

    leads_str = '\n'.join(leads)
    raiders_str = '\n'.join(raiders)
    formatted_message = (
        f"/CP {project_name}\n\n"
        f"LEADS\n"
        f"{leads_str}\n\n"
        f"RAIDERS\n"
        f"{raiders_str}"
    )

    sent_message = await send_message(update, formatted_message)
    await context.bot.pin_chat_message(chat_id, sent_message.message_id)

# View projects in the group
async def view_project_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT project_name, leads, raiders FROM projects WHERE chat_id = ?", (chat_id,))
    projects = cursor.fetchall()
    conn.close()

    if not projects:
        await send_message(update, "No projects found for this group.")
        return

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
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if not await is_admin(chat_id, user_id, context.bot):
        await send_message(update, "❌ Only admins can update projects.")
        return

    if len(context.args) < 3 or len(context.args) % 2 != 1:
        await send_message(update, "Usage: /swap <project_name> <old_raider/lead> <new_raider/lead> [<old_raider/lead> <new_raider/lead> ...]")
        return

    project_name = " ".join(context.args[:-len(context.args) + 1])
    swap_pairs = list(zip(context.args[-len(context.args) + 1::2], context.args[-len(context.args) + 2::2]))

    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT leads, raiders FROM projects WHERE chat_id = ? AND project_name = ?", (chat_id, project_name))
    project = cursor.fetchone()

    if not project:
        await send_message(update, f"❌ Project '{project_name}' not found.")
        conn.close()
        return

    leads, raiders = project
    leads_list = leads.split("\n")
    raiders_list = raiders.split("\n")

    for old_member, new_member in swap_pairs:
        if old_member in leads_list:
            leads_list = [new_member if member == old_member else member for member in leads_list]
        elif old_member in raiders_list:
            raiders_list = [new_member if member == old_member else member for member in raiders_list]
        else:
            await send_message(update, f"❌ Member '{old_member}' not found in project '{project_name}'.")
            conn.close()
            return

    updated_leads = "\n".join(leads_list)
    updated_raiders = "\n".join(raiders_list)
    cursor.execute("UPDATE projects SET leads = ?, raiders = ? WHERE chat_id = ? AND project_name = ?", (updated_leads, updated_raiders, chat_id, project_name))
    conn.commit()
    conn.close()

    conn = connect_bot_db()
    cursor = conn.cursor()
    cursor.execute("SELECT leads, raiders FROM projects WHERE chat_id = ? AND project_name = ?", (chat_id, project_name))
    updated_project = cursor.fetchone()
    conn.close()

    if not updated_project:
        await send_message(update, f"❌ Failed to fetch updated project '{project_name}'.")
        return

    updated_leads, updated_raiders = updated_project
    formatted_message = (
        f"/CP {project_name}\n\n"
        f"LEADS\n"
        f"{updated_leads}\n\n"
        f"RAIDERS\n"
        f"{updated_raiders}"
    )

    sent_message = await send_message(update, formatted_message)
    await context.bot.pin_chat_message(chat_id, sent_message.message_id)
    await send_message(update, f"✅ Project '{project_name}' updated successfully!")

# React Command
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
        logger.error(f"Error: {e}")
        await query.edit_message_text(
            text="❌ Failed to save reaction. Please try again.",
            reply_markup=query.message.reply_markup
        )

# Auto-Pick Command
async def auto_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a reaction message!")
        return
    
    message_id = update.message.reply_to_message.message_id
    
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
    
    if not reactors:
        await update.message.reply_text("No reactions found!")
        return
    
    weights = [1 / (i + 1) ** 2 for i in range(len(reactors))]
    
    try:
        num_picks = min(int(context.args[0]), len(reactors)) if context.args else 3
    except ValueError:
        await update.message.reply_text("❌ Invalid number of picks. Usage: /auto_pick <number>")
        return
    
    selected = random.choices(
        [r[0] for r in reactors],  # List of usernames
        weights=weights,           # Weights based on reaction order
        k=num_picks                # Number of participants to pick
    )
    
    seen = set()
    unique_selected = [x for x in selected if not (x in seen or seen.add(x))]
    
    fun_phrases = [
        "Make una no dull me o! 😂",
        "Who go carry last? 🏃‍♂️",
        "E no easy to be winner o! 🏆",
        "Sharp guys dey win always! 🔥"
    ]
    
    response = (
        f"💀Omor, Tension everywhere\n\n"
        f"😎 But I don select {len(unique_selected)} raiders wey react sharp sharp\n\n" +
        "\n".join(f" @{username} " for username in unique_selected) +
        f"\n\n{random.choice(fun_phrases)}"
    )
    
    await update.message.reply_text(response)
    
# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update: {update}\nError: {context.error}", exc_info=True)
    if update and update.message:
        await update.message.reply_text(f"⚠️ Error: {str(context.error)}")

# Main Function
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_error_handler(error_handler)

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
        ("register_raider", register_raider_command),
        ("view_project", view_project_command)
    ]
    for command, handler in handlers:
        application.add_handler(CommandHandler(command, handler))

    # Add message handler for project lists
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\/CP"), handle_project_list))
     
    # Add callback query handler for approval buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()
