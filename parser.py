# python playercounter.py /path/to/server.log

import datetime
import MySQLdb
import os.path
import os
import sys

from collections import defaultdict
from stat import ST_SIZE
from time import sleep, time

db = MySQLdb.connect(user="minecraft", db="minecraft")

class Tail(object):
    """The Tail monitor object."""
    
    def __init__(self, path, only_new = False,
                 min_sleep = 1,
                 sleep_interval = 1,
                 max_sleep = 60):
        """Initialize a tail monitor.
             path: filename to open
             only_new: By default, the tail monitor will start reading from
               the beginning of the file when first opened. Set only_new to
               True to have it skip to the end when it first opens, so that
               you only get the new additions that arrive after you start
               monitoring. 
             min_sleep: Shortest interval in seconds to sleep when waiting
               for more input to arrive. Defaults to 1.0 second.
             sleep_interval: The tail monitor will dynamically recompute an
               appropriate sleep interval based on a sliding window of data
               arrival rate. You can set sleep_interval here to seed it
               initially if the default of 1.0 second doesn't work for you
               and you don't want to wait for it to converge.
             max_sleep: Maximum interval in seconds to sleep when waiting
               for more input to arrive. Also, if this many seconds have
               elapsed without getting any new data, the tail monitor will
               check to see if the log got truncated (rotated) and will
               quietly reopen itself if this was the case. Defaults to 60.0
               seconds.
        """

        # remember path to file in case I need to reopen
        self.path = os.path.abspath(path)
        self.f = open(self.path,"r")
        self.min_sleep = min_sleep * 1.0
        self.sleep_interval = sleep_interval * 1.0
        self.max_sleep = max_sleep * 1.0
        if only_new:
            # seek to current end of file
            file_len = os.stat(path)[ST_SIZE]
            self.f.seek(file_len)
        self.pos = self.f.tell()        # where am I in the file?
        self.last_read = time()         # when did I last get some data?
        self.queue = []                 # queue of lines that are ready
        self.window = []                # sliding window for dynamically
                                        # adjusting the sleep_interval

    def _recompute_rate(self, n, start, stop):
        """Internal function for recomputing the sleep interval. I get
        called with a number of lines that appeared between the start and
        stop times; this will get added to a sliding window, and I will
        recompute the average interarrival rate over the last window.
        """
        self.window.append((n, start, stop))
        purge_idx = -1                  # index of the highest old record
        tot_n = 0                       # total arrivals in the window
        tot_start = stop                # earliest time in the window
        tot_stop = start                # latest time in the window
        for i, record in enumerate(self.window):
            (i_n, i_start, i_stop) = record
            if i_stop < start - self.max_sleep:
                # window size is based on self.max_sleep; this record has
                # fallen out of the window
                purge_idx = i
            else:
                tot_n += i_n
                if i_start < tot_start: tot_start = i_start
                if i_stop > tot_stop: tot_stop = i_stop
        if purge_idx >= 0:
            # clean the old records out of the window (slide the window)
            self.window = self.window[purge_idx+1:]
        if tot_n > 0:
            # recompute; stay within bounds
            self.sleep_interval = (tot_stop - tot_start) / tot_n
            if self.sleep_interval > self.max_sleep:
                self.sleep_interval = self.max_sleep
            if self.sleep_interval < self.min_sleep:
                self.sleep_interval = self.min_sleep

    def _fill_cache(self):
        """Internal method for grabbing as much data out of the file as is
        available and caching it for future calls to nextline(). Returns
        the number of lines just read.
        """
        old_len = len(self.queue)
        line = self.f.readline()
        while line != "":
            self.queue.append(line)
            line = self.f.readline()
        # how many did we just get?
        num_read = len(self.queue) - old_len
        if num_read > 0:
            self.pos = self.f.tell()
            now = time()
            self._recompute_rate(num_read, self.last_read, now)
            self.last_read = now
        return num_read

    def _dequeue(self):
        """Internal method; returns the first available line out of the
        cache, if any."""
        if len(self.queue) > 0:
            line = self.queue[0]
            self.queue = self.queue[1:]
            return line
        else:
            return None

    def _reset(self):
        """Internal method; reopen the internal file handle (probably
        because the log file got rotated/truncated)."""
        self.f.close()
        self.f = open(self.path, "r")
        self.pos = self.f.tell()
        self.last_read = time()

    def nextline(self):
        """Return the next line from the file. Blocks if there are no lines
        immediately available."""

        # see if we have any lines cached from the last file read
        line = self._dequeue()
        if line:
            return line
        
        # ok, we are out of cache; let's get some lines from the file
        if self._fill_cache() > 0:
            # got some
            return self._dequeue()

        # hmm, still no input available
        while True:
            sleep(self.sleep_interval)
            if self._fill_cache() > 0:
                return self._dequeue()
            now = time()
            if (now - self.last_read > self.max_sleep):
                # maybe the log got rotated out from under us?
                if os.stat(self.path)[ST_SIZE] < self.pos:
                    # file got truncated and/or re-created
                    self._reset()
                    if self._fill_cache() > 0:
                        return self._dequeue()

    def close(self):
        """Close the tail monitor, discarding any remaining input."""
        self.f.close()
        self.f = None
        self.queue = []
        self.window = []

    def __iter__(self):
        """Iterator interface, so you can do:

        for line in filetail.Tail('log.txt'):
            # do stuff
            pass
        """
        return self

    def next(self):
        """Kick the iterator interface. Used under the covers to support:

        for line in filetail.Tail('log.txt'):
            # do stuff
            pass
        """
        return self.nextline()

"""
create table mc_visitor (
    id int primary key auto_increment,
    name varchar(64),
    ip varchar(32) null,
    date_joined datetime,
    date_left datetime null
);
create index name on mc_visitor (name);
create unique index name_date on mc_visitor (name, date_joined);
"""

class LogParser(object):
    def __init__(self, logfile):
        self.visitor_stack = {}
        self.logfile = logfile
    
    def handle_disconnect(self, player, date):
        visitor_id = self.visitor_stack.pop(player, None)
        if visitor_id:
            print "%s (%s) has disconnected" % (player, visitor_id)
            cursor = db.cursor()
            cursor.execute("update mc_visitor set date_left = %s where id = %s", [date, visitor_id])
            cursor.close()
        
    def handle_connect(self, player, date):
        self.handle_disconnect(player, date)
        cursor = db.cursor()
        cursor.execute('insert ignore into mc_visitor (name, date_joined) values(%s, %s)', [player, date])
        visitor_id = db.insert_id()
        if not visitor_id:
            cursor.execute('select id from mc_visitor where name = %s and date_joined = %s', [player, date])
            visitor_id = cursor.fetchone()[0]
        cursor.close()
        self.visitor_stack[player] = visitor_id
        print "%s (%s) has connected" % (player, visitor_id)

    def begin(self):
        for line in Tail(self.logfile):
            line = line.strip()
            try:
                broken = line.split(' ')
                tokens = broken[3:]
            except IndexError:
                continue

            if not tokens:
                continue

            date = ' '.join(broken[0:2])
            date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S')

            if tokens[0].startswith('<') or tokens[0].startswith('/') or tokens[0].startswith('*'):
                continue
            
            player = None
            if 'Starting minecraft server version' in line:
                for player in self.visitor_stack.keys():
                    self.handle_disconnect(player, date)
                self.visitor_stack = {}
            elif ' lost connection' in line:
                player = tokens[0]
                self.handle_disconnect(player, date)
            elif line.endswith(' logged in'):
                player = tokens[0]
                
                # this shouldnt happen
                self.handle_connect(player, date)
            elif ' Banning ' in line or ' Kicking ' in line:
                player = tokens[-1]
                self.handle_disconnect(player, date)

def main(logfile):
    LogParser(logfile).begin()

if __name__ == '__main__':
    main(' '.join(sys.argv[1:]))