#  
#  Copyright (C) 2010 Cardapio Team (tvst@hotmail.com)
# 
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

class CardapioPlugin (CardapioPluginInterface):
	author = 'Cardapio Team'
	name = _('Web Bookmarks')
	description = _('Search for pages bookmarked in Firefox, Chrome, or Chromium')

	url                = ''
	help_text          = ''
	version            = '1.0'

	plugin_api_version = 1.40

	search_delay_type  = None
	category_name      = _('Web Bookmarks')
	category_icon      = 'html'
	icon               = 'html'
	category_tooltip   = _('Pages bookmarked in Firefox, Chrome, or Chromium')

	fallback_icon      = 'html'

	hide_from_sidebar  = True


	def __init__(self, cardapio_proxy, category):
		'''	
		This method is called when the plugin is enabled.
		Nothing much to be done here except initialize variables and set loaded to True
		'''
		self.c = cardapio_proxy
		
		try:
			import os
			import sqlite3
			import shutil
			import gio
			
		except Exception, exception:
			self.c.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.c.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return

		self.os      = os
		self.sqlite3 = sqlite3
		self.shutil  = shutil
		self.gio     = gio
		
		self.loaded = False #plugin will not be loaded if no supported browsers are found
		
		# search for browsers installed and do initial load of bookmark lists
		self.init_browser_lists()
   	

	def __del__(self):

		# handle objects that somehow seem to leak memory

		if self.ff_monitor is not None:
			if self.ff_monitor.handler_is_connected(self.ff_monitor_handler):
				self.ff_monitor.disconnect(self.ff_monitor_handler)

		self.ff_list = None # for some reason this has to be cleared to prevent a memory leak (wtf)

		if self.chromium_monitor is not None:
			if self.chromium_monitor.handler_is_connected(self.chromium_monitor_handler):
				self.chromium_monitor.disconnect(self.chromium_monitor_handler)

		self.chromium_list = None # for some reason this has to be cleared to prevent a memory leak (wtf)
		
		if self.chrome_monitor is not None:
			if self.chrome_monitor.handler_is_connected(self.chrome_monitor_handler):
				self.chrome_monitor.disconnect(self.chrome_monitor_handler)

		self.chrome_list = None # for some reason this has to be cleared to prevent a memory leak (wtf)


	def init_browser_lists(self):
		## Look for firefox and setup bookmark list and file monitor if found
		self.ff_monitor = None
		self.ff_list = []
		firefox_path = self.os.path.join(self.os.environ['HOME'],".mozilla/firefox")
		if self.os.path.exists(self.os.path.join(firefox_path,'profiles.ini')):
			
			try:
				self.load_firefox_bm()
			
				self.ff_monitor = self.gio.File(self.ff_db_path).monitor_file()
				self.ff_monitor_handler = self.ff_monitor.connect('changed', self.on_ff_bookmark_change)
				self.loaded = True
				self.c.write_to_log(self, 'Found Firefox Browser Installed')
			
			except Exception, e:
				self.c.write_to_log(self, "Error loading firefox bookmarks", is_error = True)
				self.c.write_to_log(self, e, is_error = True)
				self.ff_list = []
			
		
		## Look for chromium and setup bookmark list and file monitor if found	
		self.chromium_monitor = None
		self.chromium_list = []
		chromium_path = self.os.path.join(self.os.environ['HOME'],".config/chromium/Default")
		self.chromium_bm_path = self.os.path.join(chromium_path,'Bookmarks')
		
		if self.os.path.exists(self.chromium_bm_path):
			try:
				self.load_chromium_bm()
				self.chromium_monitor = self.gio.File(self.chromium_bm_path).monitor_file()
				self.chromium_monitor_handler = self.chromium_monitor.connect('changed', self.on_chromium_bookmark_change)
				self.loaded = True
				self.c.write_to_log(self, 'Found Chromium Browser Installed')
			
			except Exception, e:
				self.c.write_to_log(self, "Error loading chromium bookmarks", is_error = True)
				self.c.write_to_log(self, e, is_error = True)
				self.chromium_list = []
				
		## Look for google chrome and setup bookmark list and file monitor if found	
		self.chrome_monitor = None
		self.chrome_list = []
		chrome_path = self.os.path.join(self.os.environ['HOME'],".config/google-chrome/Default")
		self.chrome_bm_path = self.os.path.join(chrome_path,'Bookmarks')
		
		if self.os.path.exists(self.chrome_bm_path):
			try:
				self.load_chrome_bm()
				self.chrome_monitor = self.gio.File(self.chrome_bm_path).monitor_file()
				self.chrome_monitor_handler = self.chrome_monitor.connect('changed', self.on_chrome_bookmark_change)
				self.loaded = True
				self.c.write_to_log(self, 'Found Google-Chrome Browser Installed')
			
			except Exception, e:
				self.c.write_to_log(self, "Error loading Google-Chrome bookmarks", is_error = True)
				self.c.write_to_log(self, e, is_error = True)
				self.chrome_list = []


	def search(self, text, result_limit):
		#First we get results from every browser's plugin list
		#then we sort alphabetically
		#then we enforce the results limit when passing to the search handler
		
		results = []
		self.current_query = text
		text = text.lower()
		
		if text == "": result_limit = 1000 #no result limit when plugin  is on sidebar
				
		self.search_bm_list(text, self.ff_list, results)
		
		self.search_bm_list(text, self.chromium_list, results)
		
		self.search_bm_list(text, self.chrome_list, results)
			
		results.sort(key = lambda r: r['name']) 
		
		self.c.handle_search_result(self, results[:result_limit], self.current_query) 


	def search_bm_list(self, text, bm_list, results):
		for item in bm_list:
			if item['name'] is None: item['name'] = item['command']
			if item['name'].lower().find(text) != -1:
				results.append(item)


	def load_firefox_bm(self, *dummy):
		
		firefox_path = self.os.path.join(self.os.environ['HOME'],".mozilla/firefox")
		ini_file = open(self.os.path.join(firefox_path,'profiles.ini'))
		
		prof_list = ini_file.read().split()
		ini_file.close()
		
		# this was a nested "try" statement, but apparently that caused a memory leak (wtf!?)
		exception_thrown = False
		try:
			prof_folder = prof_list[prof_list.index('Default=1') - 1].split('=')[1]
			
		except ValueError:
			exception_thrown = True
			
		if exception_thrown:
			try:
				prof_folder = prof_list[prof_list.index('Name=default') + 2].split('=')[1]
			
			except ValueError:
				raise Exception('Could not determine firefox profile folder')				
			
		prof_path = self.os.path.join(firefox_path,prof_folder)
		
		self.ff_db_path = self.os.path.join(prof_path, 'places.sqlite')
		
		
		if not self.os.path.exists(self.ff_db_path):
			raise Exception('could not find the firefox bookmarks database')

		
		# places.sqlite is locked when firefox is running, so we must make
		# a temporary copy to read the bookmarks from
		db_copy_path = '%s.copy' % self.ff_db_path
		self.shutil.copy(self.ff_db_path, db_copy_path)
		
		sql_conn = self.sqlite3.connect(db_copy_path)

		sql_query = "SELECT moz_bookmarks.title, moz_places.url \
					 FROM moz_bookmarks, moz_places  \
					 WHERE moz_bookmarks.fk = moz_places.id AND moz_places.url NOT LIKE 'place:%'"
					 
		self.ff_list = []

		try:
			for bookmark in sql_conn.execute(sql_query):
				self.ff_list.append({
						'name'         : bookmark[0],
						'tooltip'      : _('Firefox bookmark:\n%s') % bookmark[1],
						'icon name'    : 'html',
						'type'         : 'xdg',
						'command'      : bookmark[1],
						'context menu' : [
							{
							'name'         : _('Open in Firefox'),
							'tooltip'      : _('Go To \"%s\" in Firefox') % bookmark[0],
							'icon name'    : 'firefox',
							'type'         : 'raw',
							'command'      : 'firefox \"%s\"' % bookmark[1]
							}]
						})

		except Exception, exception:
			self.c.write_to_log(self, exception, is_error = True)

		sql_conn.close()
		self.os.remove(db_copy_path)


	def load_chromium_bm(self):

		try: 
			f = open(self.chromium_bm_path)
			
			read_queue = ["",""]
			bm_list = []
			
			for line in f:
				
				if line.find("\"url\": ") != -1:
					bm_list.append([read_queue[0],line])
				
				read_queue.pop(0)
				read_queue.append(line)
				
			f.close()
		except Exception, exception:
			 raise Exception("Error reading chromium bookmark file")
			
				 
		self.chromium_list = []

		for line in bm_list:
			name = line[0].split("\"")[3]
			url = line[1].split("\"")[3]
			self.chromium_list.append({
					'name'         : name,
					'tooltip'      : _('Chromium bookmark:\n%s') % url,
					'icon name'    : 'html',
					'type'         : 'xdg',
					'command'      : url,
					'context menu' : [
						{
						'name'         : _('Open in Chromium'),
						'tooltip'      : _('Go To \"%s\" in Chromium') % name,
						'icon name'    : 'chromium',
						'type'         : 'raw',
						'command'      : 'chromium-browser \"%s\"' %line[1].split("\"")[3]
						}]
					})


	#of course its very similar to the chromium function, but there are enough
	#variables and strings that need to be different so I didn't try to
	#implement it as the same function
	def load_chrome_bm(self):

		try: 
			f = open(self.chrome_bm_path)
			
			read_queue = ["",""]
			bm_list = []
			
			for line in f:
				
				if line.find("\"url\": ") != -1:
					bm_list.append([read_queue[0],line])
				
				read_queue.pop(0)
				read_queue.append(line)
				
			f.close()
		except Exception, exception:
			 raise Exception("Error reading google chrome bookmark file")
			
				 
		self.chrome_list = []
	
		for line in bm_list:
			name = line[0].split("\"")[3]
			url = line[1].split("\"")[3]
			self.chrome_list.append({
					'name'         : name,
					'tooltip'      : _('Chrome bookmark:\n%s') % url,
					'icon name'    : 'html',
					'type'         : 'xdg',
					'command'      : url,
					'context menu' : [
						{
						'name'         : _('Open in Google Chrome'),
						'tooltip'      : _('Go To \"%s\" in Google Chrome') % name,
						'icon name'    : 'google-chrome',
						'type'         : 'raw',
						'command'      : 'google-chrome \"%s\"' %line[1].split("\"")[3]
						}]
					})


	def on_ff_bookmark_change(self, monitor, _file, other_file, event):
		try:
			self.load_firefox_bm()
		except Exception, e:
			self.c.write_to_log(self, "Error reloading firefox bookmarks", is_error = True)
			self.c.write_to_log(self, e, is_error = True)
			self.ff_list = []


	def on_chromium_bookmark_change(self, monitor, _file, other_file, event):
		try:
			self.load_chromium_bm()
		except Exception, e:
			self.c.write_to_log(self, "Error reloading chromium bookmarks", is_error = True)
			self.c.write_to_log(self, e, is_error = True)
			self.chromium_list = []


	def on_chrome_bookmark_change(self, monitor, _file, other_file, event):
		try:
			self.load_chrome_bm()
		except Exception, e:
			self.c.write_to_log(self, "Error reloading google chrome bookmarks", is_error = True)
			self.c.write_to_log(self, e, is_error = True)
			self.chrome_list = []

