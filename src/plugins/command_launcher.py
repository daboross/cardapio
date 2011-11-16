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

	author             = 'Cardapio team' 
	name               = _('Command Launcher')
	description        = _('Run commands from the search box')

	url                = ''
	help_text          = ''
	version            = '1.13'

	plugin_api_version = 1.40

	search_delay_type  = None

	default_keyword    = 'run'

	category_name      = _('Run Command')
	category_icon      = 'system-run'
	icon               = 'system-run'
	category_tooltip   = _('Run system commands, just like in the command-line')

	fallback_icon      = 'system-run'

	hide_from_sidebar  = True 		


	def __init__(self, cardapio_proxy, category):
		'''	
		This method is called when the plugin is enabled.
		Nothing much to be done here except initialize variables and set loaded to True
		'''
		self.c = cardapio_proxy
		
		try:
			import os
			from glob import iglob

		except Exception, exception:
			self.c.write_to_log(self, 'Could not import certain modules', is_error = True)
			self.c.write_to_log(self, exception, is_error = True)
			self.loaded = False
			return

		self.os    = os
		self.iglob = iglob
		
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

			cmd_iter = self.iglob('%s/%s*' % (path, cmdname))

			while num_results < result_limit:

				try: cmd = self.os.path.basename(cmd_iter.next())
				except StopIteration: break

				cmdargs = cmd + args
				item = {
					'name'          : cmdargs,
					'tooltip'       : 'Run \'%s\'' % cmdargs,
					'icon name'     : cmd,
					'type'          : 'raw-no-notification',
					'command'       : cmdargs,
					'context menu'  : [
						{
						'name'      : self.in_a_terminal % cmdargs,
						'tooltip'   : self.in_a_terminal_tooltip % cmdargs,
						'icon name' : 'utilities-terminal',
						'type'      : 'raw-in-terminal',
						#'command'   : 'gnome-terminal -x bash -c \"%s ; bash\"' % cmdargs
						'command'   : cmdargs
						},
						{
						'name'      : self.as_root % cmdargs,
						'tooltip'   : self.as_root_tooltip % cmdargs,
						'icon name' : cmd,
						'type'      : 'raw',
						'command'   : 'gksudo \"%s\"' % cmdargs
						}]
					}
				results.append(item)
				num_results += 1
					
		results.sort(key = lambda r: r['name'])
					
		# Thiago> if the command was not found, don't display anything
		#
		# if not results:
		# 	results.append({
		# 		'name'          : text,
		# 		'tooltip'       : 'Run \'%s\'' % text,
		# 		'icon name'     : 'system-run',
		# 		'type'          : 'raw',
		# 		'command'       : text,
		# 		'context menu'  : [
		# 			{
		# 			'name'      : self.in_a_terminal % text,
		# 			'tooltip'   : self.in_a_terminal_tooltip % text,
		# 			'icon name' : 'utilities-terminal',
		# 			'type'      : 'raw',
		# 			'command'   : 'gnome-terminal -x bash -c \"%s ; bash\"' % text
		# 			},
		# 			{
		# 			'name'      : self.as_root % text,
		# 			'tooltip'   : self.as_root_tooltip % text,
		# 			'icon name' : 'system-run',
		# 			'type'      : 'raw',
		# 			'command'   : 'gksudo \"%s\"' % text
		# 			}]
		# 		})

		self.c.handle_search_result(self, results, self.current_query)

