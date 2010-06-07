from distutils.core import setup

setup(
	name         = 'Cardapio',
	version      = '0.9.5',
	description  = 'A menu with search capabilities.',
	author       = 'Thiago Teixeira',
	author_email = 'tvst@hotmail.com',
	url          = 'https://www.launchpad.net/cardapio',
	packages     = ['cardapio'],
	package_data = {'cardapio': ['cardapio.ui']},
	data_files   = [
			('/usr/local/bin', ['cardapio/cardapio']),
			('/usr/lib/bonobo/servers', ['cardapio/cardapio.server']),
		],
	)

