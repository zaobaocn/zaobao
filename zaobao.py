#!/usr/bin/python3
import os
import re
import sys # Import sys for exit
import time
import json
import sqlite3
# import hashlib # Removed hashlib
import requests
import logging
from random import randrange
from bs4 import BeautifulSoup

class zaobao:
    def __init__(self, bot_id, chat_id):
        self.bot_id = bot_id
        self.chat_id = chat_id
        self.news_list = []
        self.url = 'https://www.zaobao.com.sg'
        self.db_file = 'sent_news.db'
        self.conn = None
        self.cursor = None
        self._init_db() # Initialize database connection and table

        try:
            with open('ua.json', 'r') as f:
                ua_list = json.load(f)
                # Ensure ua_list is not empty before using randrange
                if ua_list: 
                    ua = ua_list[randrange(0,len(ua_list))]
                    self.header = {'User-Agent': ua}
                else:
                    logging.warning("ua.json is empty. Using default User-Agent.")
                    self.header = {'User-Agent': 'Mozilla/5.0'}
        except (FileNotFoundError, json.JSONDecodeError, IndexError) as e:
            logging.error(f"Error loading ua.json: {e}. Using default User-Agent.")
            # Provide a default UA or handle the error appropriately
            self.header = {'User-Agent': 'Mozilla/5.0'}
            
    def _init_db(self):
        """Initializes the SQLite database connection and creates the table if it doesn't exist."""
        try:
            self.conn = sqlite3.connect(self.db_file)
            self.cursor = self.conn.cursor()
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS sent_items (
                    url TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL
                )
            ''')
            self.conn.commit()
            logging.info(f"Database '{self.db_file}' initialized successfully.")
        except sqlite3.Error as e:
            logging.error(f"Database error during initialization: {e}")
            # Handle error appropriately, maybe exit or fallback
            if self.conn:
                self.conn.close()
            raise # Re-raise the exception if initialization fails critically
            
    def close_db(self):
        """Closes the database connection."""
        if self.conn:
            try:
                self.conn.commit() # Ensure any pending changes are saved
                self.conn.close()
                logging.info("Database connection closed.")
            except sqlite3.Error as e:
                 logging.error(f"Database error during close: {e}")

    # 获取新闻列表
    def getNewsList(self):
        """Fetches the list of news URLs from the realtime page."""
        self.news_list = [] # Clear list for fresh fetch
        try:
            logging.info("Fetching news list...")
            r = requests.get(self.url + '/realtime', headers=self.header, timeout=15) # Increased timeout
            r.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            r.encoding = 'utf-8'
            soup = BeautifulSoup(r.text, 'html.parser')
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching news list: {e}")
            return # Exit the method if fetching fails

        # --- Robust HTML Parsing for News List ---
        cat = soup.find('div', {'id': 'realtime-articles-by-web-category'})
        if not cat:
            logging.error("Could not find the main news category container ('realtime-articles-by-web-category'). Website structure might have changed.")
            return

        # Find news sections more robustly (e.g., by looking for specific attributes or structure)
        # This part is still somewhat fragile and depends on the site structure.
        # Consider using more specific CSS selectors if possible.
        try:
            # Assuming the structure remains div -> div -> ul for China and World news
            china_section = cat.select_one('div > div:nth-of-type(1) > ul') 
            world_section = cat.select_one('div > div:nth-of-type(2) > ul')
            
            china_items = china_section.find_all('li', recursive=False) if china_section else []
            world_items = world_section.find_all('li', recursive=False) if world_section else []
            all_items = china_items + world_items
            
            logging.info(f'共发现新闻{len(all_items)}篇')

            for item in all_items:
                link_tag = item.find('a', href=True)
                title_tag = item.find('h2')

                if link_tag and title_tag:
                    url = link_tag['href']
                    title = title_tag.text.strip()
                    
                    # Basic validation for URL (starts with /)
                    if not url.startswith('/'):
                        logging.warning(f"Skipping item with potentially invalid URL: {url}")
                        continue

                    # Check if the URL exists in the database
                    try:
                        self.cursor.execute("SELECT 1 FROM sent_items WHERE url = ?", (url,))
                        if self.cursor.fetchone() is None:
                            self.news_list.append(url)
                            logging.info(f'{title} | {url} | 待获取')
                        # else:
                        #     logging.debug(f"Skipping already sent URL: {url}")
                    except sqlite3.Error as e:
                        logging.error(f"Database error checking URL {url}: {e}")
                else:
                    logging.warning(f"Could not extract URL or Title from list item: {item.prettify()}") # Log problematic item

        except (AttributeError, IndexError, TypeError) as e:
             logging.error(f"Error parsing news list HTML structure: {e}. Website structure might have changed.")
        # --- End Robust HTML Parsing ---
             
        logging.info(f'待获取新闻共{len(self.news_list)}篇')

    # 获取新闻全文
    def getArticle(self, url):
        """Fetches and parses a single news article."""
        title, msg, img, kw = None, None, None, '' # Initialize return values
        try:
            full_url = self.url + url
            logging.debug(f"Fetching article: {full_url}")
            r = requests.get(full_url, headers=self.header, timeout=15) # Increased timeout
            r.raise_for_status()
            r.encoding = 'utf-8'
            soup = BeautifulSoup(r.text, 'html.parser')
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching article {url}: {e}")
            return title, msg, img, kw # Return None values

        # --- Robust HTML Parsing for Article ---
        try:
            # 标题
            title_tag = soup.find('h1')
            if title_tag:
                title = title_tag.text.strip()
                article_title_html = f"<a href='{full_url}'>" + '<b>' + title + '</b>' + '</a>'
            else:
                logging.warning(f"Could not find title (h1) for article: {url}")
                return None, None, None, '' # Cannot proceed without title

            # 封面 (Handle potential missing thumbnail)
            img_match = re.search(r'"thumbnailUrl":\s*"(.*?)"', r.text)
            img = img_match.groups()[0] if img_match else None
            if not img:
                 logging.warning(f"Could not find thumbnailUrl for article: {url}")

            # 内容
            article_content_div = soup.find('div', {'class': "articleBody"})
            article_text = ''
            if article_content_div:
                ps = article_content_div.find_all('p')
                article_text = '\n\n'.join(p.text for p in ps)
            else:
                 logging.warning(f"Could not find article body (div.articleBody) for article: {url}")

            # 关键词
            keywords_div = soup.find('div', {'class': 'max-h-max'})
            if keywords_div:
                kw_list = keywords_div.find_all('a')
                kw = ' '.join(f'#{i.text.strip()}' for i in kw_list)

            if not article_text and not img: # If no content and no image, maybe skip?
                 logging.warning(f"Article has no text content or image: {url}")
                 # Decide if you still want to send just the title/link

            msg = article_title_html + article_text + '\n\n' + kw
            logging.info(f'{title} | {url} | 已获取')

        except (AttributeError, IndexError, TypeError, re.error) as e:
             logging.error(f"Error parsing article HTML {url}: {e}")
             # Return None to indicate parsing failure
             return None, None, None, '' 
        # --- End Robust HTML Parsing ---

        return title, msg, img, kw
    
    # 推送新闻至TG
    def sendMessage(self, text, disable_preview=True):
        """Sends a text message to Telegram."""
        if not self.bot_id or not self.chat_id:
             logging.error("BOT_ID or CHAT_ID is missing, cannot send message.")
             return None
        api_url = f"https://api.telegram.org/bot{self.bot_id}/sendMessage"
        data = {'chat_id': self.chat_id, 'text': text, 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': disable_preview}}
        try:
            logging.debug(f"Sending message to {self.chat_id}")
            r = requests.post(api_url, json=data, timeout=10) 
            return r
        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending message to Telegram: {e}")
            return None # Return None if sending fails
    
    def sendPhoto(self, photo, caption):
        """Sends a photo message to Telegram."""
        if not self.bot_id or not self.chat_id:
             logging.error("BOT_ID or CHAT_ID is missing, cannot send photo.")
             return None
        api_url = f"https://api.telegram.org/bot{self.bot_id}/sendPhoto"
        # Corrected parameter name 'pohoto' to 'photo'
        data = {'chat_id': self.chat_id, 'photo': photo, 'caption': caption, 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}}
        try:
            logging.debug(f"Sending photo to {self.chat_id}")
            r = requests.post(api_url, json=data, timeout=20) # Increased timeout for photo upload
            return r
        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending photo to Telegram: {e}")
            return None # Return None if sending fails
    
    # (updateList method removed as it's replaced by direct DB operations)
 
    def add_sent_item(self, url):
        """Adds a sent item's URL to the database with the current timestamp."""
        try:
            current_time = time.time()
            self.cursor.execute("INSERT OR IGNORE INTO sent_items (url, timestamp) VALUES (?, ?)", (url, current_time))
            # Commit happens after each successful send in the main loop now
        except sqlite3.Error as e:
            logging.error(f"Database error adding item {url}: {e}")

    def cleanup_db(self, days_to_keep=7):
        """Removes entries older than the specified number of days from the database."""
        if not self.conn:
             logging.warning("Database connection not available for cleanup.")
             return
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            logging.info(f"Cleaning up database entries older than {days_to_keep} days...")
            self.cursor.execute("DELETE FROM sent_items WHERE timestamp < ?", (cutoff_time,))
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            if deleted_count > 0:
                logging.info(f"Cleaned up {deleted_count} old entries from the database.")
            else:
                logging.info("No old entries found to clean up.")
        except sqlite3.Error as e:
            logging.error(f"Database error during cleanup: {e}")

if __name__ == '__main__':
    # 配置日志记录
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    bot_id = os.getenv('BOT_ID')
    chat_id = os.getenv('CHAT_ID')

    # --- Environment Variable Check ---
    if not bot_id:
        logging.critical("Environment variable BOT_ID is not set. Exiting.")
        sys.exit(1) # Use sys.exit for cleaner exit
    if not chat_id:
        logging.critical("Environment variable CHAT_ID is not set. Exiting.")
        sys.exit(1)
    # --- End Environment Variable Check ---

    zb = None # Initialize zb to None
    try: 
        zb = zaobao(bot_id, chat_id)
        zb.getNewsList()
        
        if not zb.news_list:
             logging.info("No new news items to process.")
        else:
            logging.info(f"Processing {len(zb.news_list)} new news items...")

        for url in zb.news_list:
            title, msg, img, kw = zb.getArticle(url)
            
            # Skip if getArticle failed (returned None for title)
            if title is None: 
                logging.warning(f"Skipping article due to previous fetch/parse error: {url}")
                continue

            r = None # Initialize r
            send_successful = False
            
            # Try sending with photo first if available
            if img:
                logging.debug(f"Attempting to send with photo: {url}")
                r = zb.sendPhoto(img, msg)
                if r and r.status_code == 200:
                    send_successful = True
                elif r: # Request went through but got error status
                     logging.warning(f"sendPhoto failed for {title} ({r.status_code}). Response: {r.text}. Trying text only.")
                # If r is None, network error already logged by sendPhoto

            # If photo send failed or no image, send text only
            if not send_successful:
                 logging.debug(f"Attempting to send text only: {url}")
                 r = zb.sendMessage(msg)
                 if r and r.status_code == 200:
                     send_successful = True
                 elif r: # Request went through but got error status
                     logging.warning(f"sendMessage failed for {title} ({r.status_code}). Response: {r.text}. Trying fallback.")
                 # If r is None, network error already logged by sendMessage

            # If both attempts failed, try sending link only as fallback
            if not send_successful:
                logging.warning(f"All send attempts failed for {title}. Attempting fallback (link only).")
                msg_fallback = f"<a href='{zb.url + url}'>{title}</a> {kw}".strip() # Add keywords if available
                r = zb.sendMessage(msg_fallback, False) # Enable preview for fallback link
                if r and r.status_code == 200:
                    send_successful = True
                elif r: # Fallback also failed
                     logging.error(f'Final fallback send attempt failed for {title} {url}. Status: {r.status_code}, Response: {r.text}')
                # If r is None, network error logged by sendMessage

            # Add sent item URL to DB only if any send attempt was successful
            if send_successful:
                try:
                    response_json = r.json() # Try to get JSON response
                except json.JSONDecodeError:
                    response_json = r.text # Fallback to text if not JSON
                logging.info(f'{title} | {url} | 已发送 | Response: {response_json}')
                zb.add_sent_item(url) # Add the URL directly
                try:
                    zb.conn.commit() # Commit after each successful send
                except sqlite3.Error as e:
                    logging.error(f"Database commit error after sending {url}: {e}")
            else:
                 # Log final failure if no attempt succeeded
                 logging.error(f"All send attempts ultimately failed for: {title} | {url}")


            # Consider making sleep duration configurable or dynamic
            time.sleep(randrange(3, 8)) # Use random sleep to appear less bot-like

    except Exception as e:
        # Catch any unexpected errors in the main loop
        logging.critical(f"An unexpected error occurred in the main process: {e}", exc_info=True) # Log traceback
    finally:
        # Ensure DB cleanup and closure happens even if errors occurred
        if zb and zb.conn: # Check if zb and connection were initialized
            zb.cleanup_db(days_to_keep=7) # Keep records for 7 days (configurable)
            zb.close_db()
        else:
            logging.info("Skipping DB cleanup/close as connection was not established.")
            
    logging.info("Script finished.")
