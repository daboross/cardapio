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

class CardapioPlugin(CardapioPluginInterface):

	author             = 'Cardapio team'
	name               = _('Software Center')
	description        = _('Search for new applications in the Software Center')

	url                = ''
	help_text          = ''
	version            = '1.24'

	plugin_api_version = 1.40

	search_delay_type  = 'remote' # HACK: this should be 'local', but searching
	                              # the software center DB can be pretty slow, so we set 
								  # this to 'remote' as a stopgap measure. See:
								  # https://bugs.launchpad.net/cardapio/+bug/642264

	default_keyword    = 'softwarecenter'
	category_name      = _('Available Software')
	category_icon      = 'softwarecenter'
	icon               = 'softwarecenter'
	category_tooltip   = _('Software available to install on your system')

	fallback_icon      = 'applications-other'

	hide_from_sidebar = True 


	def __init__(self, cardapio_proxy, category):
		'''	
		This method is called when the plugin is enabled.
		Nothing much to be done here except initialize variables and set loaded to True
		'''
		
		self.c = cardapio_proxy
		self.loaded = False
		
		try:
			import xapian
			import sys
			import apt
			import os
			import gio
			import platform

			distro, ver, dummy = platform.linux_distribution()
			self.is_maverick_or_newer = (distro == ('Ubuntu') and ver in ['10.10', '11.04', '11.10', '12.04'])
			self.is_natty_or_newer = (distro == ('Ubuntu') and ver in ['11.04', '11.10', '12.04'])

			software_center_path = '/usr/share/software-center'

			if not os.path.exists(software_center_path):
				raise Exception('Could not find the software center path')

			sys.path.append(software_center_path)

			from softwarecenter.enums import XAPIAN_VALUE_POPCON, XAPIAN_VALUE_ICON, XAPIAN_VALUE_SUMMARY
			from softwarecenter.db.database import StoreDatabase
			from softwarecenter.view.appview import AppViewFilter

			if self.is_natty_or_newer:
				from softwarecenter.db.application import Application
				from softwarecenter.enums import PKG_STATE_UNINSTALLED

		except Exception, exception:
			self.c.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.c.write_to_log(self, exception, is_error = True)
			return
			
		self.xapian               = xapian
		self.apt                  = apt
		self.os                   = os
		self.gio                  = gio
		self.XAPIAN_VALUE_ICON    = XAPIAN_VALUE_ICON
		self.XAPIAN_VALUE_SUMMARY = XAPIAN_VALUE_SUMMARY 
		self.XAPIAN_VALUE_POPCON  = XAPIAN_VALUE_POPCON
		self.StoreDatabase        = StoreDatabase
		self.AppViewFilter        = AppViewFilter

		if self.is_natty_or_newer:
			self.Application           = Application
			self.PKG_STATE_UNINSTALLED = PKG_STATE_UNINSTALLED

		self.cache = self.apt.Cache() # this line is really slow! around 0.28s on my computer!
		db_path = '/var/cache/software-center/xapian'

		if not self.os.path.exists(db_path):
			self.c.write_to_log(self, 'Could not find the database path', is_error = True)
			return

		self.db = StoreDatabase(db_path, self.cache)
		self.db.open()
		self.apps_filter = AppViewFilter(self.db, self.cache)

		if self.is_maverick_or_newer:
			self.c.write_to_log(self, 'Detected Ubuntu 10.10 or higher')

			if self.is_natty_or_newer:
				self.apps_filter.set_not_installed_only(True)
			else:
				self.apps_filter.set_only_packages_without_applications(True)

			self.action = {
				'name'         : _('Open Software Center'),
				'tooltip'      : _('Search for more software in the Software Center'),
				'icon name'    : 'system-search', # using this icon because otherwise it looks strange...
				'type'         : 'callback',
				'command'      : self.open_softwarecenter_search,
				'context menu' : None,
				}
		else:
			self.c.write_to_log(self, 'Detected Ubuntu older than 10.10')
			self.apps_filter.set_only_packages_without_applications(True)
			self.action = {
				'name'         : _('Open Software Center'),
				'tooltip'      : _('Search for more software in the Software Center'),
				'icon name'    : 'system-search', # using this icon because otherwise it looks strange...
				'type'         : 'raw',
				'command'      : 'software-center',
				'context menu' : None,
				}

		self.context_menu_action_name = _('_Install %s')
		self.context_menu_action_tooltip = _('Install this package without opening the Software Center')

		self.default_tooltip_str = _('Show %s in the Software Center')
		self.summary_str = _('Description:')

		dpkg_path = '/var/lib/dpkg/lock'

		if self.os.path.exists(dpkg_path):
			self.package_monitor = self.gio.File(dpkg_path).monitor_file()
			self.package_monitor_handler = self.package_monitor.connect('changed', self.on_packages_changed)

		else:
			self.c.write_to_log(self, 'Path does not exist:' + dpkg_path, is_warning = True)
			self.c.write_to_log(self, 'Will not be able to monitor for package changes', is_warning = True)
			self.package_monitor = None
		
		self.loaded = True # set to true if everything goes well


	def __del__(self):

		# handle objects that somehow seem to leak memory

		if self.package_monitor is not None:
			if self.package_monitor.handler_is_connected(self.package_monitor_handler):
				self.package_monitor.disconnect(self.package_monitor_handler)

		self.action = None # for some reason this has to be cleared to prevent a memory leak (wtf)
		self.db     = None
		self.cache  = None


	def search(self, text, result_limit):
 
		self.current_query = text

		results = []
		
		query = self.db.get_query_list_from_search_entry(text)
		
		enquire = self.xapian.Enquire(self.db.xapiandb)
		enquire.set_query(query[1])
		enquire.set_sort_by_value_then_relevance(self.XAPIAN_VALUE_POPCON)
		matches = enquire.get_mset(0, len(self.db))

		i = 0
		for m in matches:
			if i >= result_limit: break
			
			if self.is_natty_or_newer:
				doc = m.document
				pkgname = self.db.get_pkgname(doc)
				summary = doc.get_value(self.XAPIAN_VALUE_SUMMARY)
				app = self.Application(self.db.get_appname(doc), self.db.get_pkgname(doc), popcon=self.db.get_popcon(doc))
				uninstalled = (app.get_details(self.db).pkg_state == self.PKG_STATE_UNINSTALLED)

			else:
				doc = m[self.xapian.MSET_DOCUMENT]
				pkgname = self.db.get_pkgname(doc)
				summary = doc.get_value(self.XAPIAN_VALUE_SUMMARY)
				uninstalled = self.apps_filter.filter(doc, pkgname)

			name = doc.get_data()

			if uninstalled and summary:
				icon_name = self.os.path.splitext(doc.get_value(self.XAPIAN_VALUE_ICON))[0]

				tooltip = self.default_tooltip_str % name 

				if summary:
					tooltip += '\n' + self.summary_str + ' ' + summary

				item = {
					'name'      : name,
					'tooltip'   : tooltip,
					'icon name' : icon_name,
					'type'      : 'raw',
					'command'   : "software-center '%s'" % pkgname,
					'context menu' : [
							{
								'name'      : self.context_menu_action_name % name,
								'tooltip'   : self.context_menu_action_tooltip,
								'icon name' : 'gtk-save',
								'type'      : 'raw',
								'command'   : 'apturl-gtk apt:%s' % pkgname,
							},
						]
					}

				results.append(item)
				i += 1

		if results:
			results.append(self.action)
	
		self.c.handle_search_result(self, results, self.current_query)


	def on_reload_permission_granted(self):

		pass
		# self.cache.open(None) # There's a memory leak in this line!


	def on_packages_changed(self, monitor, file, other_file, event):

		if event == self.gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT:
			self.c.ask_for_reload_permission(self)
			

	def open_softwarecenter_search(self, text):
		try:
			subprocess.Popen(["software-center", "search:%s"  % text])
		except Exception:
			self.c.write_to_log(self, 'Unable to open Software Center', is_error = True)


