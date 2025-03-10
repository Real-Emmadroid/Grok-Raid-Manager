import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler
from database import connect_db
from database import create_team, join_team, list_teams, view_team, create_project, list_projects, remove_team, leave_team, remove_inactive, leaderboard, swap_raiders, verify_team, register_raider, approve_raider, reject_raider

# Configuration
TOKEN = "7846706967:AAFuL6C3XHqhr6d7UZ-3BKb80AJruEjHgsA"
application = ApplicationBuilder().token("7846706967:AAFuL6C3XHqhr6d7UZ-3BKb80AJruEjHgsA").build()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def format_command_usage(command: str, usage: str) -> str:
    return f"Usage: {command} {usage}"

async def send_message(update: Update, text: str) -> None:
    await update.message.reply_text(text)

# Command Handlers
async def start(update: Update, context: CallbackContext) -> None:
    await send_message(update, "Welcome to the Raid Team Bot! Use /help to see available commands.")

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = """
    Available Commands:
    /create_team <team_name> - Create a new team
    /join_team <team_name> - Join an existing team
    /list_teams - View all teams
    /view_team <team_name> - View members of a team
    /create_project <team_name> <project_name> - Create a project
    /list_projects <team_name> - List projects of a team
    /remove_team <team_name> - Remove a team (only leader can do this)
    /leave_team <team_name> - Leave a team
    /remove_inactive - Remove inactive members
    /leaderboard - View the leaderboard
    /swap <raider1> <raider2> - Swap raiders between projects
    /verify_team <team_name> - Verify a team
    /register_raider <team_name> <twitter_handle> - Register a raider
    /approve_raider <user_id> - Approve a raider

    """
    await send_message(update, help_text)
async def create_team_command(update: Update, context: CallbackContext):
    if not context.args:
        await send_message(update, "Usage: /create_team <team_name>")
        return
    
    team_name = " ".join(context.args)  # Capture team name from command args
    leader_id = update.effective_user.id  # Get the Telegram user ID

    result = create_team(team_name, leader_id)  # Call function with both arguments
    await send_message(update, result)  # Send response message

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("➕ ADD ME TO CHAT", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("⚙ CONTINUE SETUP HERE", callback_data="continue_setup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to the Raid Team Bot!\n\n"
        "Click one of the options below to get started:",
        reply_markup=reply_markup
    )

async def button_callback(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "continue_setup":
        await query.message.reply_text("Let's continue the setup. What do you want to do next?")

# Ensure these handlers are properly registered in your existing dispatcher
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_callback))


async def list_pending_raiders_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Check if user is a team leader
    conn = connect_db()
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

    conn = connect_db()
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
        await update.message.reply_text("Usage: /register_raider <team_name> <twitter_handle>")
        return

    team_name = context.args[0]
    twitter_handle = context.args[1]
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    response = register_raider(user_id, username, twitter_handle, team_name)
    await update.message.reply_text(response)

async def approve_raider_command(update: Update, context: CallbackContext):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /approve_raider <user_id>")
        return

    user_id = int(context.args[0])
    leader_id = update.message.from_user.id

    response = approve_raider(user_id, leader_id)
    await update.message.reply_text(response)


async def reject_raider_command(update: Update, context: CallbackContext):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /reject_raider <user_id>")
        return

    user_id = int(context.args[0])
    leader_id = update.message.from_user.id

    response = reject_raider(user_id, leader_id)
    await update.message.reply_text(response)

async def join_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, format_command_usage("/join_team", "<team_name>"))
        return
    team_name = context.args[0]
    await send_message(update, join_team(team_name))

async def list_teams_command(update: Update, context: CallbackContext) -> None:
    await send_message(update, list_teams())

async def view_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, format_command_usage("/view_team", "<team_name>"))
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

    result = create_project(team_name, project_name, leader_id)  # Pass leader_id
    await send_message(update, result)


async def list_projects_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, format_command_usage("/list_projects", "<team_name>"))
        return
    team_name = context.args[0]
    await send_message(update, list_projects(team_name))

async def remove_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, format_command_usage("/remove_team", "<team_name>"))
        return
    team_name = context.args[0]
    await send_message(update, remove_team(team_name))

async def leave_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, format_command_usage("/leave_team", "<team_name>"))
        return
    team_name = context.args[0]
    await send_message(update, leave_team(team_name))


async def remove_inactive_command(update: Update, context: CallbackContext) -> None:
    await send_message(update, remove_inactive())

async def leaderboard_command(update: Update, context: CallbackContext) -> None:
    await send_message(update, leaderboard())

async def swap_raiders_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        await send_message(update, format_command_usage("/swap", "<raider1> <raider2>"))
        return
    raider1, raider2 = context.args
    await send_message(update, swap_raiders(raider1, raider2))

async def verify_team_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        await send_message(update, format_command_usage("/verify_team", "<team_name>"))
        return
    team_name = context.args[0]
    await send_message(update, verify_team(team_name))

# Main Function
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    handlers = [
        ("start", start),
        ("help", help_command),
        ("create_team", create_team_command),
        ("join_team", join_team_command),
        ("list_teams", list_teams_command),
        ("view_team", view_team_command),
        ("create_project", create_project_command),
        ("list_projects", list_projects_command),
        ("remove_team", remove_team_command),
        ("leave_team", leave_team_command),
        ("remove_inactive", remove_inactive_command),
        ("leaderboard", leaderboard_command),
        ("swap", swap_raiders_command),
        ("verify_team", verify_team_command),
        ("register_raider", register_raider_command),
        ("approve_raider", approve_raider_command),
        ("reject_raider", reject_raider_command),
        ("list_pending_raiders", list_pending_raiders_command)
    ]
    for command, handler in handlers:
        application.add_handler(CommandHandler(command, handler))
    application.run_polling()

if __name__ == "__main__":
    main()
