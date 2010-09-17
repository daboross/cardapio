import_error = None
try:
	import os
	import sqlite3
	import shutil
	
except Exception, exception:
	import_error = exception
	

class CardapioPlugin (CardapioPluginInterface):
	author = 'Cardapio Team'
	name = _('Firefox Bookmarks')
	description = _('Search for Firefox Bookmarks')

	url = ''
	help_text = ''
	version = '1.0'

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
		
		if import_error:
			self.c.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.c.write_to_log(self, import_error, is_error = True)
			self.loaded = False
			return
		
		self.build_bookmark_list()
		
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
	
	def build_bookmark_list(self):
		
		firefox_path = os.environ['HOME'] + "/.mozilla/firefox"
		ini_file = open('%s/profiles.ini' % firefox_path)
		prof_list = ini_file.read().split()
		ini_file.close()
		
		prof_folder = prof_list[prof_list.index('Default=1') - 1].split('=')[1]
		db_path = '%s/%s/places.sqlite' % (firefox_path, prof_folder)
		
		if not os.path.exists(db_path):
			self.c.write_to_log(self, 'Could not find the bookmarks database', is_error = True)
			return
		
		#places.sqlite is locked when firefox is running, so we must make
		#a temporary copy to read the bookmarks from
		db_copy_path = '%s.copy' % db_path
		shutil.copy(db_path, db_copy_path)
		
		sql_conn = sqlite3.connect(db_copy_path)

		sql_query = "SELECT moz_bookmarks.title, moz_places.url \
					 FROM moz_bookmarks, moz_places  \
					 WHERE moz_bookmarks.fk = moz_places.id AND moz_places.url NOT LIKE 'place:%'"
					 
		c = sql_conn.execute(sql_query)
		
		self.item_list = []
		for row in c:
			item = {
					'name'		 : _('%s') % row[0],
					'tooltip'	  : _('Go To \"%s\"') % row[0] ,
					'icon name'	: 'html', 
					'type'		 : 'xdg',
					'command'	  : '%s' % row[1],
					'context menu' : None,
					}
			self.item_list.append(item)
		
		sql_conn.close()
		os.remove(db_copy_path)
		
	#TODO: Find a way to update plugin when bookmarks change in Firefox
		
