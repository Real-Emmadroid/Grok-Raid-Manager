import sqlite3

# Connect to the database
DATABASE = "raid_bot.db"
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Fetch all rows from the projects table
cursor.execute("SELECT * FROM reactions")
rows = cursor.fetchall()

# Print the rows
print("Reactions:")
for row in rows:
    print(row)

# Close the connection
conn.close()