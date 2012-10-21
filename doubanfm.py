#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os, re, time, thread, glib, gobject
import pygst
pygst.require("0.10")
import gst, json, urllib, httplib, contextlib, random
from select import select
from Cookie import SimpleCookie
from contextlib import closing 

class PrivateFM(object):
    def __init__ (self, username, password):
        self.dbcl2 = None
        self.login(username, password)
    
    def login(self, username, password):
        data = urllib.urlencode({'form_email':username, 'form_password':password})
        with closing(httplib.HTTPConnection("www.douban.com")) as conn:
            conn.request("POST", "/accounts/login", data, {"Content-Type":"application/x-www-form-urlencoded"})
            cookie = SimpleCookie(conn.getresponse().getheader('Set-Cookie'))
            if not cookie.has_key('dbcl2'):
                print 'login failed'
                thread.exit()
                return 
            dbcl2 = cookie['dbcl2'].value
            if dbcl2 and len(dbcl2) > 0:
                self.dbcl2 = dbcl2
                self.uid = self.dbcl2.split(':')[0]
            self.bid = cookie['bid'].value
  
    def get_params(self, typename=None):
        params = {}
        params['r'] = random.random()
        params['uid'] = self.uid
        params['channel'] = '0' 
        if typename is not None:
            params['type'] = typename
        return params

    def communicate(self, params):
        data = urllib.urlencode(params)
        cookie = 'dbcl2="%s"; bid="%s"' % (self.dbcl2, self.bid)
        header = {"Cookie": cookie}
        with closing(httplib.HTTPConnection("douban.fm")) as conn:
            conn.request('GET', "/j/mine/playlist?"+data, None, header)
            result = conn.getresponse().read()
            return result

    def playlist(self):
        params = self.get_params('n')
        result = self.communicate(params)
        return json.loads(result)['song']
     
    def del_song(self, sid, aid):
        params = self.get_params('b')
        params['sid'] = sid
        params['aid'] = aid
        result = self.communicate(params)
        return json.loads(result)['song']

    def fav_song(self, sid, aid):
        params = self.get_params('r')
        params['sid'] = sid
        params['aid'] = aid
        self.communicate(params)

    def unfav_song(self, sid, aid):
        params = self.get_params('u')
        params['sid'] = sid
        params['aid'] = aid
        self.communicate(params)

class DoubanFM_CLI:
    def __init__(self, channel):
        self.user = None
        self.username = None
	self.password = None
        if channel == '0':
            self.private = True
        else:
            self.private = False
        self.player = gst.element_factory_make("playbin", "player")
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        self.ch = 'http://douban.fm/j/mine/playlist?type=n&h=&channel='+channel
	self.controls = {'n':self.control_next, 'f':self.control_fav,
	    'd':self.control_del, 'p':self.control_pause} 
	if os.path.isfile('configs.yaml'):
	    import yaml
	    configs = yaml.load(open('configs.yaml'))
	else:
	    configs = {}
	if configs.get('info_format') != None: 
	    self.info_format = configs['info_format'] 
	else:
	    self.info_format = u'正在播放：{title}\t歌手：{artist}\t专辑：{albumtitle}'
	if configs.get('username') != None:
	    self.username = configs.get('username')
	    if configs.get('password') != None:
		self.password = configs.get('password')

    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.player.set_state(gst.STATE_NULL)
            self.playmode = False
        elif t == gst.MESSAGE_ERROR:
            self.player.set_state(gst.STATE_NULL)
            err, debug = message.parse_error()
            print "Error: %s" % err, debug
            self.playmode = False

    def get_songlist(self):
        if self.user:
            self.songlist = self.user.playlist()
        elif self.private:
	    if self.username == None:
		self.username = raw_input("请输入豆瓣登录账户：") 
	    else:
		print "豆瓣登录账户：" + self.username
	    if self.password == None:
		import getpass
		self.password = getpass.getpass("请输入豆瓣登录密码：") 
            self.user = PrivateFM(self.username, self.password)
            self.songlist = self.user.playlist()
        else:
            self.songlist = json.loads(urllib.urlopen(self.ch).read())['song']
	
    def control_next(self, r):
	return 'next'

    def control_fav(self, r):
	if self.private == True:
	    self.user.fav_song(r['sid'], r['aid'])
	    print "加心成功"
	return 'fav'

    def control_del(self, r):
	if self.private == True:
	    self.songlist = self.user.del_song(r['sid'], r['aid'])
	    print "删歌成功:)"
        return 'del'

    def control_pause(self, r):
	if gst.STATE_PLAYING == self.player.get_state()[1]:
	    self.player.set_state(gst.STATE_PAUSED)
	    print '已暂停'
	    return 'pause'
	else:
	    self.player.set_state(gst.STATE_PLAYING)
	    print '继续播放'
	    return 'continue'

    def control(self,r):
        rlist, _, _ = select([sys.stdin], [], [], 1)
        if rlist:
            s = sys.stdin.readline()
	    if s[0] in self.controls:
	    	return self.controls[s[0]](r)
	    return None

    def song_info(self,r):
	def replace(matchobj):
	    if matchobj.group(0)[1:-1] in r:
		return r[matchobj.group(0)[1:-1]]
	    else:
		return matchobj(0)
	return re.sub('\{\w*\}', replace, self.info_format)

    def start(self):
        self.get_songlist()
        for r in self.songlist:
            song_uri = r['url']
            self.playmode = True
	    print self.song_info(r)
            self.player.set_property("uri", song_uri)
            self.player.set_state(gst.STATE_PLAYING)
            while self.playmode:
                c = self.control(r)
                if c == 'next' or c == 'del':
                    self.player.set_state(gst.STATE_NULL)
                    self.playmode = False
                    break 
        loop.quit()

def print_channel_info():
    import json
    channel_url = "http://www.douban.com/j/app/radio/channels"
    channellist = json.loads(urllib.urlopen(channel_url).read())['channels']
    channellist.sort(key=lambda x: x["channel_id"])
    for x in channellist:
        print "%s: %s (%s)" % (x["channel_id"],
                               x["name"].encode("utf-8"),
                               x["name_en"].encode("utf-8"))
print_channel_info()
c = raw_input('请输入您想听的频道数字:')
doubanfm = DoubanFM_CLI(c)
common_info = u'跳过输入n，暂停输入p'
private_info = u'加心输入f，删歌输入d'
use_info = common_info
if c == '0': 
    use_info = u'；'.join([common_info, private_info])
print use_info
while True:
    thread.start_new_thread(doubanfm.start, ())
    gobject.threads_init()
    loop = glib.MainLoop()
    loop.run()

