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

	author = 'Clifton Mulkey'
	name = _('VirtualBox')
	description = _('Search for and start VirtualBox virtual machines from the menu')

	# not used in the GUI yet:
	url = ''
	help_text = ''
	version = '1.24'

	plugin_api_version = 1.40

	search_delay_type = None

	default_keyword   = 'vbox'

	category_name     = _('Virtual Machines')
	category_icon     = 'VBox'
	icon              = 'VBox'
	category_tooltip  = _('Your VirtualBox virtual machines')

	hide_from_sidebar = False
	# Set to "False" to show the "Virtual Machines" category all the time
	# Set to "True" to only show it when searching		


	def __init__(self, cardapio_proxy, category):
		'''	
		This method is called when the plugin is enabled.
		Here the variables are initialized an the list of virtual machines is built.
		'''
		
		self.c = cardapio_proxy
		
		try:
			import os
			import gio
			from vboxapi import VirtualBoxManager
			
		except Exception, exception:
			self.c.write_to_log(self, "Error importing some modules: %s" % exception, is_error = True)
			self.loaded = False
			return
		
		self.os                = os
		self.gio               = gio
			
		try:
			subprocess.Popen(['VBoxManage'], stdout = subprocess.PIPE)
			
		except OSError:
			self.c.write_to_log(self, "VBoxManage command not recognized: Maybe virtualbox is not installed...", is_error = True)
			self.loaded = False
			return
		
		self.vboxmgr = VirtualBoxManager(None,None)
		self.load_vm_items()
		
		machine_path = self.vboxmgr.vbox.systemProperties.defaultMachineFolder
		
		if self.os.path.exists(machine_path):
			self.package_monitor = self.gio.File(machine_path).monitor_directory()
			self.package_monitor.connect('changed', self.on_vms_changed)

		else:
			self.c.write_to_log(self, 'Path does not exist:' + machine_path, is_warning = True)
			self.c.write_to_log(self, 'Will not be able to monitor for virtual machine changes', is_warning = True)
			
		self.loaded = True

	
	def search(self, text, result_limit):
  
		self.current_query = text

		results = []
		
		#This may not be the best way to do this, but the idea is that the 
		#result limit should not be applied to the VirtualBox category 
		#unless a search is taking place
		if text == '':
			result_limit = 1000
	
		text = text.lower()
		for item in self.vm_items:
			
			if item['name'].lower().find(text) != -1 and len(results) < result_limit:
				results.append(item)
	  
		self.c.handle_search_result(self, results, self.current_query)

		
	def load_vm_items(self):
		self.vm_items = []
		vms = self.vboxmgr.getArray(self.vboxmgr.vbox, 'machines')
		tooltip = _('Start virtual machine %(name)s\nOS Type: %(os)s')
		
		for vm in vms:
			item = {
				'name'         : vm.name,
				'tooltip'      : tooltip % {'name': vm.name, 'os': vm.OSTypeId},
				'icon name'    : 'VBox',
				'type'         : 'raw',
				'command'      : 'VBoxManage startvm \"%s\"' % vm.name,
				'context menu' : None,
			}
			
			self.vm_items.append(item)
			
			
	def on_vms_changed(self, monitor, file, other_file, event):
		
		if event in [self.gio.FILE_MONITOR_EVENT_CREATED, 
					 self.gio.FILE_MONITOR_EVENT_DELETED]:
			
			self.c.ask_for_reload_permission(self)
			
	def on_reload_permission_granted(self):
		self.load_vm_items()
	
