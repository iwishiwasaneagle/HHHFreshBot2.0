# -*- coding: utf-8 -*-
import datetime
import time
import praw
import sqlite3
import logging
import os
import vals
import sys
import unidecode
import numpy as np
from tabulate import tabulate


db = sqlite3.connect(os.path.join(vals.cwd, "fresh.db"))
c = db.cursor()

# Get user data
c.execute("SELECT * FROM subscriptions")

users=0
both=0
daily=0
weekly=0

for f in c.fetchall():
    users+=1
    f = f[1]
    if f=="both":
        both+=1
    elif f=="daily":
        daily+=1
    else:
        weekly+=1

print(tabulate([["Users", users],["Both", both],["Daily", daily],["Weekly",weekly]],headers=["Type", "Number"], tablefmt='orgtbl'))



