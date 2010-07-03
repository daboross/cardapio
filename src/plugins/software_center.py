import_error = None

try:
	import xapian
	import sys
	import apt
	import os

except Exception, exception:
	import_error = exception

class CardapioPlugin (CardapioPluginInterface):

	author = 'Clifton Mulkey'
	name = _('Software Center')
	description = _('Search for new applications in the Software Center')

	url = ''
	help_text = ''
	version = '1.0'

	plugin_api_version = 1.2 

	search_delay_type = 'local search update delay'
	category_name     = _('Uninstalled Software')
	category_icon     = 'softwarecenter'
	category_tooltip  = _('Software available to install in your system')

	hide_from_sidebar = True 		


	def __init__(self, settings, write_to_log, handle_search_result, handle_search_error):
		'''	
		This method is called when the plugin is enabled.
		Nothing much to be done here except initialize variables and set loaded to True
		'''
		
	   	self.loaded = False

		self.write_to_log = write_to_log
		self.handle_search_result = handle_search_result
		self.handle_search_error = handle_search_error
		self.num_search_results = settings['search results limit']
		
		if import_error:
			self.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.write_to_log(self, import_error, is_error = True)
			return

		software_center_path = '/usr/share/software-center'

		if not os.path.exists(software_center_path):
			self.write_to_log(self, 'Could not find the software center path', is_error = True)
			return

		sys.path.append(software_center_path)

		try:
			from softwarecenter.enums import XAPIAN_VALUE_POPCON
			from softwarecenter.db.database import StoreDatabase
			from softwarecenter.view.appview import AppViewFilter

		except Exception, exception:
			self.write_to_log(self, 'Could not load the software center modules', is_error = True)
			self.write_to_log(self, exception, is_error = True)
			return

		cache = apt.Cache()
		db_path = '/var/cache/software-center/xapian'

		if not os.path.exists(db_path):
			self.write_to_log(self, 'Could not find the database path', is_error = True)
			return

		self.db = StoreDatabase(db_path, cache)
		self.db.open()
		self.apps_filter = AppViewFilter(self.db, cache)
		self.apps_filter.set_not_installed_only(True)
		self.apps_filter.set_only_packages_without_applications(True)

		self.XAPIAN_VALUE_ICON = 172
		self.XAPIAN_VALUE_POPCON = 176
		self.XAPIAN_VALUE_SUMMARY = 177

		self.action = {
			'name'      : _('Open software center'),
			'tooltip'   : _('Search for more software with Software Center'),
			'icon name' : 'system-search', # using this icon because otherwise it looks strange...
			'type'      : 'raw',
			'command'   : 'software-center',
			}

		self.default_tooltip_str = _('Install %s')
		self.summary_str = _('Description:')
		
	   	self.loaded = True # set to true if everything goes well
		

	def search(self, text):
  
		results = []
		
		query = self.db.get_query_list_from_search_entry(text)
		
		enquire = xapian.Enquire(self.db.xapiandb)
		enquire.set_query(query[1])
		enquire.set_sort_by_value_then_relevance(self.XAPIAN_VALUE_POPCON)
		matches = enquire.get_mset(0, len(self.db))

		i = 0
		for m in matches:
			if not i < self.num_search_results : break
			
			doc = m[xapian.MSET_DOCUMENT]
			pkgname = self.db.get_pkgname(doc)
			summary = doc.get_value(self.XAPIAN_VALUE_SUMMARY)

			name = doc.get_data()

			icon_name = 'applications-other'

			if self.apps_filter.filter(doc, pkgname) and summary:
				icon_name = os.path.splitext(doc.get_value(self.XAPIAN_VALUE_ICON))[0]

				if not icon_name:
					icon_name = 'applications-other'

				tooltip = self.default_tooltip_str % name 

				if summary:
					tooltip += '\n' + self.summary_str + ' ' + summary

				item = {
					'name'      : name,
					'tooltip'   : tooltip,
					'icon name' : icon_name ,
					'type'      : 'raw',
					'command'   : "software-center '%s'" % pkgname
					}

				results.append(item)
				i += 1

		if results:
			results.append(self.action)
	
		self.handle_search_result(self, results)

