# -*- coding: utf-8 -*-
import datetime
import time
import praw
import sqlite3
import logging
import os
import vals
import sys
from logging.handlers import TimedRotatingFileHandler

FORMATTER = logging.Formatter(
    "%(asctime)s — %(name)s — %(levelname)s — %(message)s")
LOG_FILE = os.path.join(vals.cwd, "HHHBot.log")


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER)
    return console_handler


def get_file_handler():
    file_handler = TimedRotatingFileHandler(LOG_FILE, when='midnight')
    file_handler.setFormatter(FORMATTER)
    return file_handler


def get_logger(logger_name):
    logger = logging.getLogger(logger_name)
    # better to have too much log than not enough
    logger.setLevel(logging.DEBUG)
    logger.addHandler(get_console_handler())
    logger.addHandler(get_file_handler())
    # with this pattern, it's rarely necessary to propagate the error up to parent
    logger.propagate = False
    return logger


log = get_logger("hhh_main")


class HHHBot:
    def __init__(self):
        log.debug("Beginning __init__")
        self.footer = '\n\n---\n\n^(This post was generated by a bot)\n\n^Subscribe ^to ^roundups: ^[[Daily](http://www.' \
                      'reddit.com/message/compose/?to={username}&subject=subscribe&message=daily)] ^[[Weekly](http://www.' \
                      'reddit.com/message/compose/?to={username}&subject=subscribe&message=weekly)] '\
                        '^[[Both](http://www.reddit.com/message/compose/?to={username}&subject=subscribe&message=both)] '\
                      '^[[Unsubscribe](http://www.reddit.com/message/compose/?to={username}' \
                      '&subject=unsubscribe&message=remove)]\n\n ^[[Source](https://github.com/iwishiwasaneagle/HHHFreshBot2.0)] ^[[Feedback](http://www.reddit.com/message/compose/?to={admin}' \
                      '&amp;subject=%2Fu%2FHHHFreshBot2.0%20feedback;message=If%20you%20are%20providing%20feedback%20about%20a%20specific' \
                      '%20post%2C%20please%20include%20the%20link%20to%20that%20post.%20Thanks!)]'.format(
            username=vals.username, admin=vals.admin)

        self.db = sqlite3.connect(os.path.join(vals.cwd, "fresh.db"))

        self.c = self.db.cursor()
        self.c.execute("CREATE TABLE IF NOT EXISTS subscriptions(USER TEXT, SUBSCRIPTION TEXT)")
        self.c.execute(
            "CREATE TABLE IF NOT EXISTS posts (ID TEXT, TITLE TEXT, PERMA TEXT, URL TEXT, TIME INT, SCORE INT, SUBMITTER TEXT)")
        self.db.commit()

        self.r = praw.Reddit(client_id=vals.client_id, client_secret=vals.client_secret,
                             password=vals.password, username=vals.username, user_agent=vals.userAgent)
        self.prawCharLimit = 10000*0.9

        self.sub = self.r.subreddit(vals.subreddit)

        self.today = datetime.datetime.utcnow().strftime('%A')
        self.ydat = (datetime.datetime.utcnow() - datetime.timedelta(1)).strftime('%A')

        # Config
        self.postScoreThreshold = 50
        self.fetchPostMaxAge = 7 * 24 * 60 * 60  # 1 day
        self.deletePostAge = 31 * 24 * 60 * 60  # 1 month

    def __del__(self):
        self.c.close()
        self.db.commit()
        self.db.close()

    def fetchNewPosts(self):
        for post in self.sub.new(limit=5000):
            if '[fresh' in post.title.lower() and post.score > self.postScoreThreshold and time.time() - post.created_utc < self.fetchPostMaxAge:  # [fresh...] tag, high enough score, and not too old

                self.c.execute("SELECT * FROM posts WHERE ID=?", (post.id,))

                if self.c.fetchone() is None:
                    id_ = post.id
                    title = post.title.replace("[", "\[").replace("]", "\]")
                    permalink = 'https://redd.it/' + id_
                    url = post.url
                    created = post.created_utc
                    score = post.score
                    submitter = post.author.name


                    log.debug("Fresh post found - name {title}, id {id}, score {score}, age {age} hrs".format(
                        title=title,
                        id=id_,
                        score=score,
                        age=round((time.time() - created) / (60 * 60), 2)))
                    self.db.execute("INSERT INTO posts VALUES (?,?,?,?,?,?,?)",
                                    (id_, title, permalink, url, created, score, submitter))
        self.db.commit()

    def garbageDisposal(self):
        self.c.execute("DELETE FROM posts WHERE TIME<{} OR SCORE<{}".format(
            time.time() - self.deletePostAge,  # Select all posts where the unix time of the posts creation is lower than current time - posts creation time
            self.postScoreThreshold
        ))
        self.db.commit()

    def updateScore(self):
        self.c.execute("SELECT * FROM posts")

        for row in self.c:

            id_ = row[0]
            oldScore = row[5]
            post = self.r.submission(id=id_)
            score = post.score

            if abs(score-oldScore)>20: #Only significant changes
                log.debug("Post id {id} updated to new score {score} (change of {change})".format(
                    id=id_,
                    score=score,
                    change=oldScore - score))
                self.db.execute("UPDATE posts SET SCORE=? WHERE ID=?", (score, id_))

        self.db.commit()

    def checkInbox(self):
        for pm in self.r.inbox.unread():
            response = ""

            subject = pm.subject.lower()
            body = pm.body.lower()
            try:
                author = pm.author.name
            except AttributeError:
                author = "None"

            if not pm.was_comment:
                if "unsubscribe" in subject:
                    if 'daily' in body:
                        log.info("Unsubscribing {} from daily".format(author))
                        response = self.unsubscribeUser(author, 'daily')
                    elif 'weekly' in body:
                        log.info("Unsubscribing {} from weekly".format(author))
                        response = self.unsubscribeUser(author, 'weekly')
                    elif 'remove' in body:
                        log.info("Unsubscribing {} from all mailing lists".format(author))
                        response = self.unsubscribeUser(author, 'both')
                    else:
                        log.info("Unsubscribe message from {} could not be understood".format(author))
                        response = 'I couldn\'t understand your message. Please use one of the links below to subscribe!'

                elif "subscribe" in subject:
                    if 'daily' in body:
                        response = self.subscribeUser(author, 'daily')
                    elif 'weekly' in body:
                        response = self.subscribeUser(author, 'weekly')
                    elif 'both' in body:
                        response = self.subscribeUser(author, 'both')
                    else:
                        log.info("Subscribe message from {} could not be understood".format(author))
                        response = 'I couldn\'t understand your message. Please use one of the links below to subscribe!'

                else:
                    log.info("Message from {author} has been forwarded to admin".format(author=author))
                    self.r.redditor(vals.admin).message('PM from /u/{}'.format(author),
                                                        "Message from /u/{author}\n\nSubject: {subject} \n\n---\n\n {body}".format(
                                                            author=author,
                                                            subject=subject,
                                                            body=body
                                                        ) + self.footer)
                    response = 'I received your message, but I\'m just a bot! I forwarded it to my admin {admin} who will take a look at it when he "\
                                "gets a chance.\n\nIf it\'s urgent, you should PM them directly.\n\nIf you\'re trying to subscribe to one of the roundups,"\
                                 "use the links below.\n\nThanks!'.format(admin=vals.admin)


                try:
                    pm.reply(response+self.footer)
                except Exception:

                    log.exception("Failed to send message to {} with body {}".format(author, response))
            else:
                log.info("Forwarding comment message to admin")
                self.r.redditor(vals.admin).message('Comment from /u/{}'.format(author),
                                                    'Message from /u/{author}\n\nSubject: {subject}\n\nContext: {context}\n\n---\n\n{body}'.format(
                                                        author=author,
                                                        subject=subject,
                                                        context=pm.context,
                                                        body=body
                                                    ))
            pm.mark_read()

    def subscribeUser(self, user, subscription):
        self.c.execute("SELECT * FROM subscriptions WHERE USER = ?", (user,))
        msg = ''
        val = self.c.fetchall()
        if val is None:
            self.c.execute("INSERT INTO subscriptions VALUES (?,?)", (user, subscription))
            log.info("Subscribed {} to {}".format(user, subscription))
            msg = "You have been subscribed to the {} mailing list".format(subscription)
        else:
            for row in val:
                if row[1] == subscription:
                    log.info("User {} already subscribed to \"{}\" mailing list".format(user, subscription))
                    msg = "You are already subscribed to the \"{}\" mailing list!".format(subscription)
                else:
                    self.c.execute("UPDATE subscriptions SET SUBSCRIPTION=? WHERE USER=?", ("both", user))
                    log.info("Subscribed {} to both".format(user))
                    msg = "You have been subscribed to both mailing lists!"
        self.db.commit()
        return msg

    def unsubscribeUser(self, user, unsubscribeFrom):
        self.c.execute('SELECT * FROM subscriptions WHERE USER = ?', (user,))
        val = self.c.fetchone()
        msg = ''
        if val is None:
            return 'Unable to unsubscribe because you are not currently subscribed to any mailing lists.'
        else:
            if val[1] == "both":
                if unsubscribeFrom == "daily":
                    self.c.execute("UPDATE subscriptions SET SUBSCRIPTION=? WHERE USER=?", ("weekly", user))
                    msg = 'You have been unsubscribed from the daily mailing list.'
                elif unsubscribeFrom == "weekly":
                    self.c.execute("UPDATE subscriptions SET SUBSCRIPTION=? WHERE USER=?", ("daily", user))
                    msg = 'You have been unsubscribed from the weekly mailing list.'
            else:
                self.c.execute('DELETE FROM subscriptions WHERE USER = ?', (user,))
                msg = 'You have been unsubscribed from both mailing lists. Sorry to see you go!'
            self.db.commit()
            return msg

    def generate(self, sTimeFrame):

        self.c.execute("SELECT * FROM posts WHERE TIME>? ORDER BY SCORE DESC", (time.time()-sTimeFrame,))

        dict_ = {}


        for post in self.c:

            id_ = post[0]
            title = post[1]
            perma = post[2]
            url = post[3]
            t = post[4]
            key = datetime.datetime.utcfromtimestamp(t).strftime("%A, %B %w, %Y")
            score = post[5]
            submitter = post[6]

            entry = '[{title}]({url}) | [link]({perma}) | {score} | /u/{submitter}\n'.format(title=title, url=url, perma=perma, score=score, submitter=submitter)

            if key not in dict_.keys():
                dict_[key] = []

            dict_[key].append(entry)


        msg = []
        for key in dict_.keys():
            text = ""
            text = text + "**"+key+"**" + "\n\nPost | link | Score | User \n :--|:--|:--|:--|\n"
            for item in dict_[key]:
                text += item
            text+="\n\n"
            msg.append((text,key))

        msg.sort(key=lambda x: time.strptime(x[1], "%A, %B %w, %Y"))

        return msg

    def mailDaily(self):
        self.updateScore()

        message = self.generate(1*24*60*60)
        intro = 'Welcome to The Daily [Fresh]ness! Fresh /r/hiphopheads posts delivered right to your inbox ever day.\n\n'

        text = intro
        for day in message:
            text += day[0]
        text += self.footer

        self.c.execute('SELECT * FROM subscriptions WHERE SUBSCRIPTION = ? OR SUBSCRIPTION = ?', ('daily', 'both',))
        i = 0
        for row in self.c:
            log.debug("Mailing {} their daily message".format(row[0]))
            self.r.redditor((row[0])).message("The Daily Freshness for {}".format(message[0][1]), text)
            i+=1
        log.info("Sent {i} people their daily message".format(i=i))

    def mailWeekly(self):
        self.updateScore()

        message = self.generate(7*24*60*60)
        intro = 'Welcome to The Weekly [Fresh]ness! Fresh /r/hiphopheads posts delivered right to your inbox every week.\n\n'

        text = intro
        parts = []
        for day in message:
            print(day[1], len(day[0]))
            tempText = text + day[0]
            if len(tempText) > self.prawCharLimit:
                parts.append(text)
                tempText = day[0]
            text = tempText
        parts.append(text) #To account for if the last day exceeds the prawCharLimit, or there is only one part

        parts[len(parts)-1]+=self.footer

        self.c.execute('SELECT * FROM subscriptions WHERE SUBSCRIPTION = ? OR SUBSCRIPTION = ?', ('weekly', 'both',))
        users= self.c.fetchall()
        i = 0
        for part in range(len(parts)):
            for row in users:
                if len(parts) == 1:
                    log.debug("Mailing {} their weekly message".format(row[0]))
                    self.r.redditor((row[0])).message("The Weekly Freshness for the week beginning {}".format(message[0][1]), parts[part])
                else:
                    log.debug("Mailing {} their weekly message part {}".format(row[0], part+1))
                    self.r.redditor((row[0])).message(
                        "The Weekly Freshness for the week beginning {} : Part {}".format(message[0][1], part+1), parts[part])

                i+=1
        log.info("Sent {i} weekly messages to {u} people".format(i=i, u=len(users)))

    def postWeekly(self):
        self.updateScore()

        if vals.DEV:
            sub = self.r.subreddit("testingsubforbot123")
        else:
            sub = self.sub


        message = self.generate(7*24*60*60)
        intro = 'Welcome to The Weekly [Fresh]ness! Fresh /r/hiphopheads posts delivered right to your inbox every week.\n\n'

        text = intro
        parts = []
        for day in message:
            tempText = text + day[0]
            if len(tempText) > self.prawCharLimit:
                parts.append(text)
                tempText = day[0]
            text = tempText
        parts.append(text) #To account for if the last day exceeds the prawCharLimit, or there is only one part

        self.c.execute('SELECT * FROM subscriptions WHERE SUBSCRIPTION = ? OR SUBSCRIPTION = ?', ('weekly', 'both',))
        users= self.c.fetchall()
        i = 0
        for part in range(len(parts)):
            for row in users:
                if len(parts) == 1:
                    log.debug("Mailing {} their weekly message".format(row[0]))
                    sub.submit("The Weekly Freshness for the week beginning {}".format(message[0][1]), selftext=parts[part]+self.footer)
                else:
                    if part == 0:
                        submission = sub.submit("The Weekly Freshness for the week beginning {}".format(message[0][1]), selftext="**Part {}**\n\n".format(part+1)+parts[part]+self.footer)
                        log.debug("Mailing {} their weekly message part {}".format(row[0], part+1))
                    else:
                        submission = submission.reply("**Part {}**\n\n".format(part+1)+parts[part]+self.footer)

                i+=1
        log.info("Sent {i} weekly messages to {u} people".format(i=i, u=len(users)))


if __name__ == "__main__":
    triggers = ["getFresh", "mailDaily", "mailWeekly", "postWeekly", "checkMail", "help"]

    if len(sys.argv)==2:
        if sys.argv[1] in triggers:
            h = HHHBot()
            try:
                if sys.argv[1] == triggers[0]:
                    # Run this twice a day
                    h.fetchNewPosts()
                    h.updateScore()
                    h.checkInbox()
                elif sys.argv[1] == triggers[1]:
                    h.checkInbox()
                    h.mailDaily()
                elif sys.argv[1] == triggers[2]:
                    h.checkInbox()
                    h.mailWeekly()
                elif sys.argv[1] == triggers[3]:
                    h.checkInbox()
                    h.postWeekly()
                elif sys.argv[1] == triggers[4]:
                    h.checkInbox()
                else:
                    print("\n".join([f for f in triggers]))
            except Exception as e:
                log.exception("Exception in main core of code... yikes")

        else:
            log.error("No correct argument was given")
    else:
        log.error("No argument was given")