#!/usr/bin/python3
import os
import time
import json
import sqlite3
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

    # 目标分类的 URL 前缀
    TARGET_CATEGORIES = ('/news/china', '/news/world')

    # 获取新闻列表
    def getNewsList(self):
        r = requests.get(self.url + '/realtime', headers=self.header)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        cat = soup.find('div', {'id': 'realtime-articles-by-web-category'})
        if not cat:
            logging.error('找不到新闻列表容器 #realtime-articles-by-web-category')
            return

        # 找到所有分类列，通过列标题 <h2> 内的链接 href 判断是否是目标分类
        # 不依赖位置索引，新加或调换列不影响抓取
        row = cat.find('div', class_='row')
        cols = row.find_all('div', recursive=False) if row else []
        story_links = []
        for col in cols:
            h2 = col.find('h2')
            if not h2:
                continue
            category_link = h2.find('a', href=True)
            if not category_link:
                continue
            # 只处理目标分类
            if any(category_link['href'].startswith(prefix) for prefix in self.TARGET_CATEGORIES):
                story_links += col.find_all('a', href=lambda h: h and '/story' in h)

        logging.info(f'共发现新闻{len(story_links)}篇')
        seen = set()
        for a in story_links:
            url = a['href']
            if url in seen:
                continue
            seen.add(url)
            title = a.find('h2') or a.find('p')  # 文章标题标签
            title_text = title.text.strip() if title else url
            self.cursor.execute("SELECT 1 FROM sent_items WHERE url = ?", (url,))
            if self.cursor.fetchone() is None:
                self.news_list.append(url)
                logging.info(f'{title_text} {url} 待获取')
        logging.info(f'待获取新闻共{len(self.news_list)}篇')

    # 获取新闻全文
    def getArticle(self, url):
        r = requests.get(self.url + url, headers=self.header)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        # 标题
        h1 = soup.find('h1')
        if not h1:
            logging.warning(f'无法找到标题 {url}，跳过')
            return None, None, None, None
        title = h1.text.strip()
        article_title = f"<a href='{self.url + url}'>" + '<b>' + title + '</b>' + '</a>'
        # 封面图：从 og:image meta 标签获取
        og_img = soup.find('meta', property='og:image')
        img = og_img['content'] if og_img and og_img.get('content') else None
        # 内容
        article_content = soup.find('div', {'class': "articleBody"})
        if not article_content:
            logging.warning(f'无法找到正文 {url}，跳过')
            return None, None, None, None
        ps = article_content.find_all('p')
        article = ''
        for p in ps:
            article += '\n\n' + p.text
        # 关键词：从 <meta name="keywords"> 获取，更稳定
        kw = ''
        meta_kw = soup.find('meta', attrs={'name': 'keywords'})
        if meta_kw and meta_kw.get('content'):
            kw = ' '.join(f'#{k.strip()}' for k in meta_kw['content'].split(',') if k.strip())
        msg = article_title + article + '\n\n' + kw
        logging.info(f'{title} {url} 已获取')
        return title, msg, img, kw
    
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
        title, msg, img, kw = zb.getArticle(url)
        if title is None:  # 解析失败，跳过该篇
            continue
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
            zb.add_sent_item(url) # Add the URL directly
            zb.conn.commit() # Commit after each successful send
        else:
             logging.error(f'Failed to send {title} {url}. Status: {r.status_code}, Response: {r.json()}')

        time.sleep(5) # Keep the delay for now

    # Cleanup old entries and close DB connection at the end
    zb.cleanup_db(days_to_keep=7) # Keep records for 7 days (configurable)
    zb.close_db()
