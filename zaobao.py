#!/usr/bin/python3
import os
import re
import time
import hashlib
import requests
from random import randrange
from bs4 import BeautifulSoup

class zaobao:
    def __init__(self, bot_id, chat_id):
        self.bot_id = bot_id
        self.chat_id = chat_id
        self.news_list = []
        self.url = 'https://www.zaobao.com.sg'
        with open('ua.json', 'r') as f:
            ua_list = eval(f.read())
            ua = ua_list[randrange(0,len(ua_list))]
            self.header = {'User-Agent': ua}
        with open('send.txt', 'r') as f:
            self.sended_list = eval(f.read())

    # 获取新闻列表
    def getNewsList(self):
        r = requests.get(self.url + '/realtime', headers=self.header)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        cat = soup.find('div', {'id': 'realtime-articles-by-web-category'})
        china_list = cat.div.contents[1].div.ul.contents
        world_list = cat.div.contents[2].div.ul.contents
        print(time.strftime('%Y-%m-%d %H:%M:%S'), f'共发现新闻{len(china_list + world_list)}篇')
        for i in (china_list + world_list):
            # 列表标题和新闻详情页标题有可能不一致
            # 使用链接判重也会出现重复发送现象（暂未找出原因）
            # 故使用链接和标题的md5值双重判重
            # 使用zlib的crc32值会更快
            url = i.find('a')['href']
            title = i.find('h2').text.strip()
            url_md5 = hashlib.md5(url.encode('utf-8')).hexdigest()
            title_md5 = hashlib.md5(title.encode('utf-8')).hexdigest()
            if url_md5 not in self.sended_list and title_md5 not in self.sended_list:
                self.news_list.append(url)
                print(time.strftime('%Y-%m-%d %H:%M:%S'), title, url, '待获取')
        print(time.strftime('%Y-%m-%d %H:%M:%S'), f'待获取新闻共{len(self.news_list)}篇')

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
        print(time.strftime('%Y-%m-%d %H:%M:%S'), title, url, '已获取')
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
    
    # 更新新闻列表
    def updateList(self):
        with open('send.txt', 'w') as f:
            send = self.sended_list
            send = send[-320:len(send)]
            f.write(str(send))
        print(time.strftime('%Y-%m-%d %H:%M:%S'), '列表已更新')

if __name__ == '__main__':
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
            msg = f"<a href='{url}'>{title}</a> " + kw
            r = zb.sendMessage(msg, False)
        print(time.strftime('%Y-%m-%d %H:%M:%S'), title, url, '已发送', r.json())
        zb.sended_list.extend([hashlib.md5(url.encode('utf-8')).hexdigest(), hashlib.md5(title.encode('utf-8')).hexdigest()])
        time.sleep(5)
    zb.updateList()
