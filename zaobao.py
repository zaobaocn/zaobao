#!/usr/bin/python3
import os
import time
import requests
import telegram
from random import randrange
from bs4 import BeautifulSoup


class zaobao:
    def __init__(self, bot_id, chat_id):
        self.bot_id = bot_id
        self.chat_id = chat_id
        self.news_list = []
        self.all_news = set()
        self.url = 'https://www.zaobao.com.sg'
        with open('ua.json', 'r') as f:
            ua_list = eval(f.read())
            ua = ua_list[randrange(0,len(ua_list))]
            self.header = {'User-Agent': ua}
        with open('list.txt', 'r') as f:
            self.old_news = eval(f.read())
        with open('send.txt', 'r') as f:
            self.sended_list = eval(f.read())
        print(time.strftime('%Y-%m-%d %H:%M:%S'), f'上次旧闻共{len(self.old_news)}篇')

    # 获取新闻列表
    def getNewsList(self):
        r = requests.get(self.url + '/realtime', headers=self.header)
        soup = BeautifulSoup(r.text, 'html.parser')
        china = soup.find('div', {'class': 'layout__region--second'})
        world = soup.find_all('div', {'class': 'layout__region--first'})[1]
        china_list = china.find_all('span', {'class': 'realtime-title'})
        world_list = world.find_all('span', {'class': 'realtime-title'})
        print(time.strftime('%Y-%m-%d %H:%M:%S'), f'共发现新闻{len(china_list + world_list)}篇')
        for i in (china_list + world_list):
            url = self.url + i.a['href']
            self.all_news.add(i.a['href'])
            # 加sended_list判断是因为有时前一次获取的内容比当前这次获取的新闻条目要“新”
            if i.a['href'] not in self.old_news and url not in self.sended_list:
                self.news_list.append(url)
        print(time.strftime('%Y-%m-%d %H:%M:%S'), f'待获取新闻{len(self.news_list)}篇')

    # 获取新闻全文
    def getArticle(self, url):
        r = requests.get(url, headers=self.header)
        soup = BeautifulSoup(r.text, 'html.parser')
        # 标题
        title = soup.find('div', {'class': "article-title"}).text.strip()
        article_title = f"<a href='{url}'>" + '<b>' + title + '</b>' + '</a>'
        # 封面
        figure = soup.find('figure', {'class': 'inline-figure'})
        if figure:
            img = figure.find('img')['data-src']
            if 'http' not in img:
                img = self.url + img
        else:
            img = ''
        # 内容
        article_content = soup.find('div', {'class': "article-content-rawhtml"})
        ps = article_content.find_all('p')
        article = ''
        for p in ps:
            article += '\n\n' + p.text
        # 关键词
        kw = ''
        keywords = soup.find('div', {'class': 'keywords'})
        if keywords:
            kw_list = keywords.ul.find_all('li')  
            for i in kw_list:
                kw += f'#{i.text.strip()} '
        msg = article_title + article + '\n\n' + kw
        print(time.strftime('%Y-%m-%d %H:%M:%S'), title, '已获取')
        return title,msg,img,kw
    
    # 推送新闻至TG
    def sendMsg(self, title, msg, img, kw, url):
        bot = telegram.Bot(self.bot_id)
        try:
            if img:
                bot.send_photo(self.chat_id, img, msg, parse_mode='HTML')
            else:
                bot.sendMessage(self.chat_id, msg, parse_mode='HTML', disable_web_page_preview=True)
            self.sended_list.append(url)
            print(time.strftime('%Y-%m-%d %H:%M:%S'), title, '已发送')
            # no more than 20 messages per minute to the same group
            if len(self.news_list) != 1:
                time.sleep(3)
        except Exception as e:
            print("上传TG过程：", e)
            ins_url = f'https://t.me/iv?url={url}&rhash=fb7348ef6b5de0'
            msg = f"<a href='{ins_url}'>Full Text</a> " + kw
            bot.sendMessage(self.chat_id, msg, parse_mode='HTML')
            self.sended_list.append(url)
            print(time.strftime('%Y-%m-%d %H:%M:%S'), title, "转为即时预览发送")
    
    # 更新新闻列表
    def updateList(self):
        with open('list.txt', 'w') as f:
            f.write(str(self.all_news))
        with open('send.txt', 'w') as f:
            send = self.sended_list
            send = send[-80:len(send)]
            f.write(str(send))
        print(time.strftime('%Y-%m-%d %H:%M:%S'), '列表已更新')


if __name__ == '__main__':
    bot_id = os.getenv('BOT_ID')
    chat_id = os.getenv('CHAT_ID')
    zb = zaobao(bot_id, chat_id)
    zb.getNewsList()
    for url in zb.news_list:
        title,msg,img,kw = zb.getArticle(url)
        zb.sendMsg(title, msg, img, kw, url)
    zb.updateList()
