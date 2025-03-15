import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from database import Raid, save_raid, get_active_raids, delete_raid

class RaidManager:
    def __init__(self, twitter_client):
        self.twitter_client = twitter_client
        self.logger = logging.getLogger(__name__)
        self._load_active_raids()
        
    def _format_progress(self, tweet_link: str, stats: dict, goals: dict) -> str:
        return f"""🎯 Raid started! 
        {tweet_link}
        📊 Progress:
        - Likes: {stats["likes"]}/{goals["likes"]}
        - Retweets: {stats["retweets"]}/{goals["retweets"]}
        - Replies: {stats["replies"]}/{goals["replies"]}"""

    def _load_active_raids(self):
        # Load existing raids from database on startup
        for raid in get_active_raids():
            self._schedule_raid_update(raid)

    async def start_raid(self, update: Update, tweet_link: str, goals: dict):
        try:
            tweet_id = tweet_link.split("/")[-1]
            tweet_data = self.twitter_client.get_tweet(
                tweet_id,
                tweet_fields=["public_metrics"]
            )
            
            metrics = tweet_data.data["public_metrics"]
            current_stats = {
                "likes": metrics["like_count"],
                "retweets": metrics["retweet_count"],
                "replies": metrics["reply_count"]
            }

            # Create and save raid
            raid = Raid(
                chat_id=update.message.chat_id,
                message_id=update.message.message_id,
                tweet_id=tweet_id,
                goals=goals,
                stats=current_stats
            )
            save_raid(raid)

            # Schedule updates
            self._schedule_raid_update(raid)
            return self._format_progress(tweet_link, current_stats, goals)
        
        except Exception as e:
            self.logger.error(f"Raid start failed: {e}")
            return "❌ Failed to start raid."

    def _schedule_raid_update(self, raid: Raid):
        # This would need access to the application's job queue
        # (implementation depends on your framework)
        pass

    async def _update_raid_stats(self, context: ContextTypes.DEFAULT_TYPE):
        job = context.job
        chat_id = job.chat_id
        message_id = job.message_id

        try:
            # Get raid from database
            raid = self._get_raid_from_db(chat_id, message_id)
            tweet_data = self.twitter_client.get_tweet(
                raid.tweet_id,
                tweet_fields=["public_metrics"]
            )
            
            metrics = tweet_data.data["public_metrics"]
            new_stats = {
                "likes": metrics["like_count"],
                "retweets": metrics["retweet_count"],
                "replies": metrics["reply_count"]
            }

            # Update database
            raid.stats = new_stats
            save_raid(raid)

            # Check completion
            if self._goals_met(new_stats, raid.goals):
                delete_raid(chat_id, message_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🎉 All raid goals achieved!"
                )
                job.schedule_removal()

        except Exception as e:
            self.logger.error(f"Raid update failed: {e}")

    def _get_raid_from_db(self, chat_id: int, message_id: int) -> Raid:
        conn = sqlite3.connect('raids.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM raids WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id)
        )
        row = cursor.fetchone()
        conn.close()
        return Raid(
            chat_id=row[0],
            message_id=row[1],
            tweet_id=row[2],
            goals=eval(row[3]),
            stats=eval(row[4])
        )

    def _goals_met(self, stats: dict, goals: dict) -> bool:
        return all(stats[key] >= goals[key] for key in goals)