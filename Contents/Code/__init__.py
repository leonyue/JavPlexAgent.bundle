import datetime
from difflib import SequenceMatcher

from munch import Munch

from api_fanza import FanzaApi
from environments import is_local_debugging

if is_local_debugging:
    from framework_agent import Agent, MetadataSearchResult, ObjectContainer
    from framework_metadata import Movie
    from framework_locale import Locale
    from framework_log import Log
    from framework_platform import Platform


# noinspection PyPep8Naming
def Start():
    Log.Error("=========== Start ==========")


# noinspection PyMethodMayBeStatic
class JavAgent(Agent.Movies):
    name = 'Jav Media'
    ver = '1.0.0'
    primary_provider = True
    languages = [  # must have the language of the system, other update() will not be called
        Locale.Language.English,
        Locale.Language.Chinese,
        Locale.Language.Japanese,
        Locale.Language.Korean,
        Locale.Language.French,
        Locale.Language.NoLanguage]
    accepts_from = [
        'com.plexapp.agents.localmedia',
        'com.plexapp.agents.opensubtitles',
        'com.plexapp.agents.podnapisi',
        'com.plexapp.agents.subzero'
    ]
    contributes_to = [
        'com.plexapp.agents.themoviedb',
        'com.plexapp.agents.imdb',
        'com.plexapp.agents.none'
    ]

    def __init__(self):
        """
        This is where everything starts.
        """
        super(Agent.Movies, self).__init__()
        Log.Error("=========== Init ==========")
        Log.Info("{} Version: {}".format(self.name, self.ver))
        Log.Info('Plex Server Version: {}'.format(Platform.ServerVersion))

    def search(self, results, media, lang, manual):
        """
        This is called when you click on "fix match" button in Plex.
        :type results: ObjectContainer
        :type media: Movie
        :type lang: str
        :type manual: bool
        :return:
        """
        Log.Info("=========== Search ==========")
        Log.Info("Searching results: {}".format(results))
        Log.Info("Searching media: {}".format(media))
        Log.Info("Searching lang: {}".format(lang))
        Log.Info("Searching manual: {}".format(manual))

        # some debugging
        Log.Debug("media.id: {}".format(media.id))
        Log.Debug("media.name: {}".format(media.name))
        Log.Debug("media.year: {}".format(media.year))

        # query fanza api
        code = "ssni-558"
        response = FanzaApi.get_item_list(code)
        body = Munch.fromDict(response.json())
        Log.Debug("body.result.status: {}".format(body.result.status))
        Log.Debug("body.result.total_count: {}".format(body.result.status))
        Log.Debug("body.result['items'][0].content_id: {}".format(body.result['items'][0].content_id))
        Log.Info("Found number of items: {}".format(body.result.total_count))

        # items that we found and add them to the matchable list
        items = body.result['items']
        for item in items:
            date = datetime.datetime.strptime(item.date, '%Y-%m-%d %H:%M:%S')
            score = int(SequenceMatcher(None, code, item.content_id).ratio() * 100)
            media.year = date.year
            media.id = item.content_id
            media.name = item.title
            media.title_sort = item.content_id
            result = MetadataSearchResult(
                id=item.content_id,
                name=item.title,
                year=date.year,
                lang=Locale.Language.Japanese,
                score=score,
                thumb=item.imageURL.list)  # thumb??
            results.Append(result)
            Log.Info("Added search result: {}".format(result))

        # all set
        Log.Error("Searching is done")

    def update(self, metadata, media, lang, force):
        """
        :type metadata: Movie
        :type media: Movie
        :type lang: str
        :type force: bool
        """
        Log.Info("=========== Update ==========")
        Log.Info("Updating metadata: {}".format(metadata))
        Log.Info("Updating media: {}".format(media))
        Log.Info("Updating lang: {}".format(lang))
        Log.Info("Updating force: {}".format(force))

        poster_data = None
        poster_filename = None
        fanart_data = None
        fanart_filename = None

        path1 = media.items[0].parts[0].file
        log.debug('media file: {name}'.format(name=path1))

        folder_path = os.path.dirname(path1)
        log.debug('folder path: {name}'.format(name=folder_path))
