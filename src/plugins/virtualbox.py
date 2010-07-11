import re

class CardapioPlugin (CardapioPluginInterface):

	author = 'Clifton Mulkey'
	name = _('VirtualBox')
	description = _('Search for and start VirtualBox virtual machines from the menu')

	# not used in the GUI yet:
	url = ''
	help_text = ''
	version = '1.1'

	plugin_api_version = 1.3 

	search_delay_type = None

	category_name     = _('Virtual Machines')
	category_icon     = 'VBox'
	category_tooltip  = _('Your VirtualBox virtual machines')

	hide_from_sidebar = False
	# Set to "False" to show the "Virtual Machines" category all the time
	# Set to "True" to only show it when searching		


	def __init__(self, cardapio_proxy):
		'''	
		This method is called when the plugin is enabled.
		Here the variables are initialized an the list of virtual machines is built.
		'''
		
		self.c = cardapio_proxy

		self.num_search_results = self.c.settings['search results limit']
		self.vm_items = [] # List of virtual machine items 

		self.c.write_to_log(self, "Loading virtual machine list...")
		
		try:
			vms = subprocess.Popen(['VBoxManage', 'list', 'vms'], stdout = subprocess.PIPE).communicate()[0]
			
			vms = re.findall('\".*\"', vms) 
			# Virtual machines are listed in quotes, this extracts them
			# and builds a list from the VBoxManage output
			
			# The list of virtual machine items is built when the plugin loads
			# to save time when searching

			for vm in vms:
				name = vm.replace('\"','')
				item = {
					'name' : name,
					'tooltip' : _('Start virtual machine %(name)s') % {'name' : name},
					'icon name' : 'VBox',
					'type' : 'raw',
					'command' : 'VBoxManage startvm %s' % vm
					}
			 
				self.vm_items.append(item)

			self.loaded = True
			
		except OSError:

			self.c.write_to_log(self, "VBoxManage command not recognized: Maybe VirtualBox is not installed...")
			self.loaded = False


	def search(self, text):
  
		results = []
	
		text = text.lower()
		for item in self.vm_items:
			
			if item['name'].lower().find(text) != -1:
				results.append(item)
	  
		self.c.handle_search_result(self, results)

	
