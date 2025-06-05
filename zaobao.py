#!/usr/bin/python3
import os
import re
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
                ua = ua_list[randrange(0,len(ua_list))]
                self.header = {'User-Agent': ua}
        except (FileNotFoundError, json.JSONDecodeError, IndexError) as e:
            logging.error(f"Error loading ua.json: {e}")
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
            self.conn.commit() # Ensure any pending changes are saved
            self.conn.close()
            logging.info("Database connection closed.")

    # 获取新闻列表
    def getNewsList(self):
        r = requests.get(self.url + '/realtime', headers=self.header)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        cat = soup.find('div', {'id': 'realtime-articles-by-web-category'})
        china_list = cat.div.contents[1].div.ul.contents
        world_list = cat.div.contents[2].div.ul.contents
        logging.info(f'共发现新闻{len(china_list + world_list)}篇')
        for i in (china_list + world_list):
            # 列表标题和新闻详情页标题有可能不一致
            # 使用链接判重也会出现重复发送现象（暂未找出原因）
            # 故使用链接和标题的md5值双重判重
            # 使用zlib的crc32值会更快
            url = i.find('a')['href']
            title = i.find('h2').text.strip()
            # url_md5 = hashlib.md5(url.encode('utf-8')).hexdigest() # Removed MD5
            # title_md5 = hashlib.md5(title.encode('utf-8')).hexdigest() # Removed MD5
            # Check if the URL exists in the database
            self.cursor.execute("SELECT 1 FROM sent_items WHERE url = ?", (url,))
            if self.cursor.fetchone() is None:
                self.news_list.append(url)
                logging.info(f'{title} {url} 待获取')
        logging.info(f'待获取新闻共{len(self.news_list)}篇')

    # 获取新闻全文
    def getArticle(self, url):
        r = requests.get(self.url + url, headers=self.header)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        # 标题
        title = soup.find('h1').text.strip()
        article_title = f"<a href='{self.url + url}'>" + '<b>' + title + '</b>' + '</a>'
        # 封面
        img = re.search(r'"thumbnailUrl": "(.*?)"', r.text).groups()[0]
        # 内容
        article_content = soup.find('div', {'class': "articleBody"})
        ps = article_content.find_all('p')
        article = ''
        for p in ps:
            article += '\n\n' + p.text
        # 关键词
        kw = ''
        keywords = soup.find('div', {'class': 'max-h-max'})
        if keywords:
            kw_list = keywords.find_all('a')
            for i in kw_list:
                kw += f'#{i.text.strip()} '
        msg = article_title + article + '\n\n' + kw
        logging.info(f'{title} {url} 已获取')
        return title,msg,img,kw
    
    # 推送新闻至TG
    def sendMessage(self, text, disable_preview=True):
        data = {'chat_id': self.chat_id, 'text': text, 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': disable_preview}}
        r = requests.post(f"https://api.telegram.org/bot{self.bot_id}/sendMessage", json=data)
        return r
    
    def sendPhoto(self, pohoto, caption):
        data = {'chat_id': self.chat_id, 'photo': pohoto, 'caption': caption, 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}}
        r = requests.post(f"https://api.telegram.org/bot{self.bot_id}/sendPhoto", json=data)
        return r
    
    # (updateList method removed as it's replaced by direct DB operations)
 
    def add_sent_item(self, url):
        """Adds a sent item's URL to the database with the current timestamp."""
        try:
            current_time = time.time()
            self.cursor.execute("INSERT OR IGNORE INTO sent_items (url, timestamp) VALUES (?, ?)", (url, current_time))
            # No need to commit here, commit happens after loop or on close
        except sqlite3.Error as e:
            logging.error(f"Database error adding item {url}: {e}")

    def cleanup_db(self, days_to_keep=7):
        """Removes entries older than the specified number of days from the database."""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            self.cursor.execute("DELETE FROM sent_items WHERE timestamp < ?", (cutoff_time,))
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            if deleted_count > 0:
                logging.info(f"Cleaned up {deleted_count} old entries from the database.")
        except sqlite3.Error as e:
            logging.error(f"Database error during cleanup: {e}")

if __name__ == '__main__':
    # 配置日志记录
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    bot_id = os.getenv('BOT_ID')
    chat_id = os.getenv('CHAT_ID')
    zb = zaobao(bot_id, chat_id)
    zb.getNewsList()
    for url in zb.news_list:
        title,msg,img,kw = zb.getArticle(url)
        if img:
            r = zb.sendPhoto(img, msg)
        else:
            r = zb.sendMessage(msg)
        if r.status_code != 200:
            msg = f"<a href='{zb.url + url}'>{title}</a> " + kw
            r = zb.sendMessage(msg, False)
        
        # Add sent item URL to DB after successful send or fallback send
        if r.status_code == 200:
            logging.info(f'{title} {url} 已发送')
            # url_md5_sent = hashlib.md5(url.encode('utf-8')).hexdigest() # Removed MD5
            # title_md5_sent = hashlib.md5(title.encode('utf-8')).hexdigest() # Removed MD5
            zb.add_sent_item(url) # Add the URL directly
            # zb.add_sent_item(title_md5_sent) # No longer adding title md5
            zb.conn.commit() # Commit after each successful send
        else:
             logging.error(f'Failed to send {title} {url}. Status: {r.status_code}, Response: {r.text}')

        time.sleep(5) # Keep the delay for now

    # Cleanup old entries and close DB connection at the end
    zb.cleanup_db(days_to_keep=7) # Keep records for 7 days (configurable)
    zb.close_db()
