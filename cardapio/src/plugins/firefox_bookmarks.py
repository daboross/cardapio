class CardapioPlugin (CardapioPluginInterface):
	author = 'Cardapio Team'
	name = _('Firefox Bookmarks')
	description = _('Search for Firefox Bookmarks')

	url                = ''
	help_text          = ''
	version            = '1.2'

	plugin_api_version = 1.39

	search_delay_type  = None
	category_name      = _('Firefox Bookmarks')
	category_icon      = 'firefox'
	category_tooltip   = _('Web bookmarks in Firefox')

	fallback_icon      = 'html'

	hide_from_sidebar  = True


	def __init__(self, cardapio_proxy):
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
		
		self.build_bookmark_list()
		
		self.file_monitor = self.gio.File(self.db_path).monitor_file()
		self.file_monitor_handler = self.file_monitor.connect('changed', self.on_bookmarks_changed)
		
	   	self.loaded = True # set to true if everything goes well

	   	
	def __del__(self):

		# handle objects that somehow seem to leak memory

		if self.file_monitor is not None:
			if self.file_monitor.handler_is_connected(self.file_monitor_handler):
				self.file_monitor.disconnect(self.file_monitor_handler)

		self.item_list = None # for some reason this has to be cleared to prevent a memory leak (wtf)


	def search(self, text, result_limit):
		results = []
		self.current_query = text
		text = text.lower()
		
		for item in self.item_list:
			if len(results) >= result_limit: break
			if item['name'] is None: item['name'] = item['command']
			if item['name'].lower().find(text) != -1:
				results.append(item)
		
		self.c.handle_search_result(self, results, self.current_query)
	

	def build_bookmark_list(self, *dummy):
		
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
				self.c.write_to_log(self, 'Could not determine firefox profile folder', is_error = True)
				return
			
		self.prof_path = self.os.path.join(firefox_path,prof_folder)
		
		self.db_path = self.os.path.join(self.prof_path, 'places.sqlite')
		
		
		if not self.os.path.exists(self.db_path):
			self.c.write_to_log(self, 'could not find the bookmarks database', is_error = true)
			return

		
		# places.sqlite is locked when firefox is running, so we must make
		# a temporary copy to read the bookmarks from
		db_copy_path = '%s.copy' % self.db_path
		self.shutil.copy(self.db_path, db_copy_path)
		
		sql_conn = self.sqlite3.connect(db_copy_path)

		sql_query = "SELECT moz_bookmarks.title, moz_places.url \
					 FROM moz_bookmarks, moz_places  \
					 WHERE moz_bookmarks.fk = moz_places.id AND moz_places.url NOT LIKE 'place:%'"
					 
		self.item_list = []

		try:
			for bookmark in sql_conn.execute(sql_query):
				self.item_list.append({
						'name'         : bookmark[0],
						'tooltip'      : _('Go To \"%s\"') % bookmark[0],
						'icon name'    : 'html',
						'type'         : 'xdg',
						'command'      : bookmark[1],
						'context menu' : None,
						})

		except Exception, exception:
			self.c.write_to_log(self, exception, is_error = True)

		sql_conn.close()
		self.os.remove(db_copy_path)
		
		
	def on_bookmarks_changed(self, monitor, _file, other_file, event):
		self.c.ask_for_reload_permission(self)
			
	def on_reload_permission_granted(self):
		self.build_bookmark_list()	
