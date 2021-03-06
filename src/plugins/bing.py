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
    """
    Plugin based on Microsoft's Bing API. Basics of the API are described in
    this document:
    http://www.bing.com/developers/s/API%20Basics.pdf

    All web requests are done in asynchronous and cancellable manner.
    """

    # Cardapio's variables
    author = 'Pawel Bara'
    name = _('Bing')
    description = _("Perform a search using Microsoft's Bing")
    version = '0.95'

    url = ''
    help_text = ''

    plugin_api_version = 1.40

    search_delay_type = 'remote'

    default_keyword = 'bing'

    category_name = _('Bing Results')
    category_tooltip = _('Results found using Bing')

    category_icon = 'system-search'
    icon = 'system-search'
    fallback_icon = ''

    hide_from_sidebar = True

    def __init__(self, cardapio_proxy, category):

        self.cardapio = cardapio_proxy

        try:
            import json
            import gio
            import urllib
            from glib import GError

        except Exception, exception:
            self.cardapio.write_to_log(self, 'Could not import certain modules', is_error=True)
            self.cardapio.write_to_log(self, exception, is_error=True)
            self.loaded = False
            return

        self.json = json
        self.gio = gio
        self.urllib = urllib
        self.GError = GError

        self.cancellable = self.gio.Cancellable()

        # Bing's API arguments (my AppID and a request for a web search)
        self.api_base_args = {
            'Appid': '237CBC82BB8C3F7F5F19F6A77B0D38A59E8F8C2C',
            'sources': 'web'
        }

        # Bing's base URLs (search and search more variations)
        self.api_base_url = 'http://api.search.live.net/json.aspx?{0}'
        self.web_base_url = 'http://www.bing.com/search?{0}'

        self.loaded = True

    def search(self, text, result_limit):

        if len(text) == 0:
            return

        self.cardapio.write_to_log(self, 'searching for {0} using Bing'.format(text), is_debug=True)

        self.cancellable.reset()

        # prepare final API URL
        current_args = self.api_base_args.copy()
        current_args['web.count'] = result_limit

        current_args['query'] = text
        final_url = self.api_base_url.format(self.urllib.urlencode(current_args))

        self.cardapio.write_to_log(self, 'final API URL: {0}'.format(final_url), is_debug=True)

        # asynchronous and cancellable IO call
        self.current_stream = self.gio.File(final_url)
        self.current_stream.load_contents_async(self.show_search_results,
                                                cancellable=self.cancellable,
                                                user_data=text)

    def show_search_results(self, gdaemonfile, result, text):
        """
        Callback to asynchronous IO (Bing's API call).
        """

        # watch out for connection problems
        try:
            json_body = self.current_stream.load_contents_finish(result)[0]

            # watch out for empty input
            if len(json_body) == 0:
                return

            response = self.json.loads(json_body)
        except (ValueError, self.GError) as ex:
            self.cardapio.handle_search_error(self, 'error while obtaining data: {0}'.format(str(ex)))
            return

        # decode the result
        try:
            items = []

            response_body = response['SearchResponse']['Web']

            # if we have any results...
            if response_body['Total'] != 0:
                # remember them all
                for item in response_body['Results']:
                    items.append({
                        'name': item['Title'],
                        'tooltip': item['Url'],
                        'icon name': 'text-html',
                        'type': 'xdg',
                        'command': item['Url'],
                        'context menu': None
                    })

            # always add 'Search more...' item
            search_more_args = {'q': text}

            items.append({
                'name': _('Show additional results'),
                'tooltip': _('Show additional search results in your web browser'),
                'icon name': 'system-search',
                'type': 'xdg',
                # TODO: cardapio later unquotes this and then quotes it again;  # it's screwing my quotation
                'command': self.web_base_url.format(self.urllib.urlencode(search_more_args)),
                'context menu': None
            })

            # pass the results to Cardapio
            self.cardapio.handle_search_result(self, items, text)

        except KeyError:
            self.cardapio.handle_search_error(self, "Incorrect Bing's JSON structure")

    def cancel(self):
        self.cardapio.write_to_log(self, 'cancelling a recent Bing search (if any)', is_debug=True)

        if not self.cancellable.is_cancelled():
            self.cancellable.cancel()
