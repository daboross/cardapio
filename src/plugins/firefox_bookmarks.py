class CardapioPlugin (CardapioPluginInterface):
	author = 'Cardapio Team'
	name = _('Firefox Bookmarks')
	description = _('Search for Firefox Bookmarks')

	url = ''
	help_text = ''
	version = '1.2'

	plugin_api_version = 1.39 

	search_delay_type = None
	category_name = _('Firefox Bookmarks')
	category_icon = 'firefox'
	category_tooltip   = _('Web bookmarks in Firefox')
	
	fallback_icon	  = 'html'

	hide_from_sidebar = True 		


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
		lock_path = self.os.path.join(self.prof_path,'lock')
		
		# The lock file may not exist at first, but the monitor will
		# detect when it is created and deleted
		self.package_monitor = self.gio.File(lock_path).monitor_file()
		self.package_monitor.connect('changed', self.on_lock_changed)
		
	   	self.loaded = True # set to true if everything goes well

	   	
	def search(self, text, result_limit):
		results = []
		self.current_query = text
		text = text.lower()
		
		for item in self.item_list:
			if len(results) >= result_limit: break
			
			if item['name'].lower().find(text) != -1:
				results.append(item)
		
		self.c.handle_search_result(self, results, self.current_query)
	

	def build_bookmark_list(self, *dummy):
		
		firefox_path = self.os.path.join(self.os.environ['HOME'],".mozilla/firefox")
		ini_file = open(self.os.path.join(firefox_path,'profiles.ini'))
		prof_list = ini_file.read().split()
		ini_file.close()
		
		# this was a nested "try" statement, but apparently that caused a memory
		# leak (wtf!?)
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
		
		db_path = self.os.path.join(self.prof_path, 'places.sqlite')
		
		if not self.os.path.exists(db_path):
			self.c.write_to_log(self, 'could not find the bookmarks database', is_error = true)
			return

		self.db_monitor = self.gio.File(db_path).monitor_file()
		self.db_monitor.connect('changed', self.build_bookmark_list)
		
		# places.sqlite is locked when firefox is running, so we must make
		# a temporary copy to read the bookmarks from
		db_copy_path = '%s.copy' % db_path
		self.shutil.copy(db_path, db_copy_path)
		
		sql_conn = self.sqlite3.connect(db_copy_path)

		sql_query = "SELECT moz_bookmarks.title, moz_places.url \
					 FROM moz_bookmarks, moz_places  \
					 WHERE moz_bookmarks.fk = moz_places.id AND moz_places.url NOT LIKE 'place:%'"
					 
		self.item_list = []

		try:
			for bookmark in sql_conn.execute(sql_query):
				self.item_list.append({
						'name'         : '%s' % bookmark[0],
						'tooltip'      : _('Go To \"%s\"') % bookmark[0] ,
						'icon name'    : 'html',
						'type'         : 'xdg',
						'command'      : '%s' % bookmark[1],
						'context menu' : None,
						})

		except Exception, exception:
			self.c.write_to_log(self, exception, is_error = True)

		sql_conn.close()
		self.os.remove(db_copy_path)
		

	def on_lock_changed(self, monitor, file_, other_file, event):
		# Happens whenever Firefox is closed
		if event == self.gio.FILE_MONITOR_EVENT_DELETED:
			self.c.ask_for_reload_permission(self)	

			
	def on_reload_permission_granted(self):
		self.build_bookmark_list()	

