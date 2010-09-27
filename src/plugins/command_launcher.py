import_error = None
try:
	import os
	import glob

except Exception, exception:
	import_error = exception


class CardapioPlugin (CardapioPluginInterface):

	author             = 'Cardapio team' 
	name               = _('Command Launcher')
	description        = _('Run commands from the search box')

	url                = ''
	help_text          = ''
	version            = '1.1'

	plugin_api_version = 1.39

	search_delay_type  = None

	default_keyword    = 'run'

	category_name      = _('Run Command')
	category_icon      = 'system-run'
	category_tooltip   = _('Run system commands, just like in the command-line')

	fallback_icon      = 'system-run'

	hide_from_sidebar  = True 		


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
		
		self.pathlist = os.environ['PATH'].split(':')

		self.in_a_terminal         = _('Execute \'%s\' In Terminal')
		self.in_a_terminal_tooltip = _('Execute the command \'%s\' inside a new terminal window')
		self.as_root               = _('Execute \'%s\' As Root')
		self.as_root_tooltip       = _('Execute the command \'%s\' with administrative rights')
		
	   	self.loaded = True # set to true if everything goes well


	def search(self, text, result_limit):

		self.current_query = text
		results = []

		text_list = text.split(None, 1)
		cmdname   = text_list[0]

		if len(text_list) == 2:
			args = ' ' + text_list[1]
		else:
			args = ''

		num_results = 0
		for path in self.pathlist:
			if num_results >= result_limit: break

			cmd_iter = (glob.iglob('%s/%s*' % (path, cmdname)))

			while True:
				if num_results >= result_limit: break

				try:
					cmd = os.path.basename(cmd_iter.next())
					cmdargs = cmd + args
					item = {
						'name'          : '%s%s' % (cmd, args),
						'tooltip'       : 'Run \'%s%s\'' % (cmd, args),
						'icon name'     : cmd,
						'type'          : 'raw',
						'command'       : '%s%s' % (cmd, args),
						'context menu'  : [
							{
							'name'      : self.in_a_terminal % cmdargs,
							'tooltip'   : self.in_a_terminal_tooltip % cmdargs,
							'icon name' : 'utilities-terminal',
							'type'      : 'raw',
							'command'   : 'gnome-terminal -x bash -c \"%s%s ; bash\"' % (cmd, args)
							},
							{
							'name'      : self.as_root % cmdargs,
							'tooltip'   : self.as_root_tooltip % cmdargs,
							'icon name' : cmd,
							'type'      : 'raw',
							'command'   : 'gksudo \"%s%s\"' % (cmd, args)
							}]
						}
					results.append(item)
					num_results += 1

				except StopIteration:
					break
					
		results.sort(key = lambda r: r['name'])
					
		if not results:
			results.append({
				'name'          : text,
				'tooltip'       : 'Run \'%s\'' % text,
				'icon name'     : 'system-run',
				'type'          : 'raw',
				'command'       : text,
				'context menu'  : [
					{
					'name'      : self.in_a_terminal % text,
					'tooltip'   : self.in_a_terminal_tooltip % text,
					'icon name' : 'utilities-terminal',
					'type'      : 'raw',
					'command'   : 'gnome-terminal -x bash -c \"%s ; bash\"' % text
					},
					{
					'name'      : self.as_root % text,
					'tooltip'   : self.as_root_tooltip % text,
					'icon name' : 'system-run',
					'type'      : 'raw',
					'command'   : 'gksudo \"%s\"' % text
					}]
				})

		self.c.handle_search_result(self, results, self.current_query)

