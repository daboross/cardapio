import_error = None
try:
	import os
	import glob

except Exception, exception:
	import_error = exception


class CardapioPlugin (CardapioPluginInterface):

	author             = 'Cardapio team' # tvst: changed this, now that Clifton is in the Cardapio team
	name               = _('Command Launcher')
	description        = _('Run commands from the search box')

	url                = ''
	help_text          = ''
	version            = '1.0'

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
			if num_results > result_limit: break

			cmd_iter = (glob.iglob('%s/%s*' % (path, cmdname)))

			while True:
				if num_results > result_limit: break

				try:
					cmd = os.path.basename(cmd_iter.next())
					item = {
						'name'          : '%s%s' % (cmd, args),
						'tooltip'       : 'Run \'%s%s\'' % (cmd, args),
						'icon name'     : cmd,
						'type'          : 'raw',
						'command'       : '%s%s' % (cmd, args),
						'context menu'  : [
							{
							'name'      : '%s%s %s' % (cmd, args, '(in Terminal)'),
							'tooltip'   : 'Run \'%s%s\' in a terminal' % (cmd, args),
							'icon name' : 'utilities-terminal',
							'type'      : 'raw',
							'command'   : 'gnome-terminal -x bash -c \"%s%s ; bash\"' % (cmd, args)
							},
							{
							'name'      : '%s%s %s' % (cmd, args, '(as root)'),
							'tooltip'   : 'Run \'%s%s\' as root' % (cmd, args),
							'icon name' : cmd,
							'type'      : 'raw',
							'command'   : 'gksudo \"%s%s\"' % (cmd, args)
							}]
						}
					results.append(item)
					num_results += 1

				except StopIteration:
					# tvst: Hey Clifton, what command throws this exception?
					break
					
		# tvst: make results look a little nicer
		results.sort(key = lambda r: r['name'])
					
		# tvst: I moved the action below into an "if not results" to avoid
		# duplicate entries.

		if not results:
			results.append({
				'name'          : text,
				'tooltip'       : 'Run \'%s\'' % text,
				'icon name'     : 'system-run',
				'type'          : 'raw',
				'command'       : text,
				'context menu'  : [
					{
					'name'      : text + ' (in Terminal)',
					'tooltip'   : 'Run \'%s\' in a terminal' % text,
					'icon name' : 'utilities-terminal',
					'type'      : 'raw',
					'command'   : 'gnome-terminal -x bash -c \"%s ; bash\"' % text
					},
					{
					'name'      : text + ' (as root)',
					'tooltip'   : 'Run \'%s\' as root' % text,
					'icon name' : 'system-run',
					'type'      : 'raw',
					'command'   : 'gksudo \"%s\"' % text
					}]
				})

		self.c.handle_search_result(self, results, self.current_query)

