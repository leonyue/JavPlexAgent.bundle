import datetime
import os
import urllib
from difflib import SequenceMatcher

from typing import List

from api_caribbeancom import CaribbeancomApi
from api_fanza import FanzaApi, Item
from environments import is_local_debugging
from utility import extract_filename_without_ext_and_part_number, extract_part_number_from_filename

if is_local_debugging:
    from framework.framework_proxy import Proxy
    from framework.framework_agent import Agent, MetadataSearchResult, ObjectContainer
    from framework.framework_http import HTTP
    from framework.framework_locale import Locale
    from framework.framework_log import Log
    from framework.framework_platform import Platform
    from framework.framework_proxy import Proxy


# noinspection PyMethodMayBeStatic,DuplicatedCode
class JavMovieAgent(Agent.Movies):
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
        'com.nicholasworkshop.javplexagents',
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
        :type media: Media
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
        Log.Debug("media.filename: {}".format(urllib.unquote(media.filename)))

        # generating keywords from directory and filename
        filename = urllib.unquote(media.filename)
        directory = os.path.basename(os.path.dirname(filename))
        filename_without_ext_and_part = extract_filename_without_ext_and_part_number(filename)
        Log.Debug("directory: {}".format(directory))
        Log.Debug("filename_without_ext_and_part: {}".format(filename_without_ext_and_part))

        # query fanza api with keywords
        self.search_caribbeancom(results, directory)
        self.search_caribbeancom(results, filename_without_ext_and_part)
        self.search_fanza(results, directory)
        self.search_fanza(results, filename_without_ext_and_part)
        Log.Error("Searching is done")

    def search_caribbeancom(self, results, keyword):
        """
        :type results: ObjectContainer
        :type keyword: str
        """
        id = CaribbeancomApi.extract_id(keyword)
        if id is None: return

        Log.Info("Search item with keyword: {}".format(id))
        item = CaribbeancomApi.get_item(id)
        result = MetadataSearchResult(
            id="carib-" + item.id,
            name="{} {}".format(id, item.title),
            year=item.upload_date.year,
            lang=Locale.Language.Japanese,
            thumb=item.poster_url,
            score=100)
        results.Append(result)
        Log.Info("Added search result: {}".format(result))

    def search_fanza(self, results, keyword):
        """
        :type results: ObjectContainer
        :type keyword: str
        """
        Log.Info("Search item with keyword: {}".format(keyword))
        body = FanzaApi.search_item(keyword)
        Log.Info("Found number of items: {}".format(body.result.total_count))

        # some more debugging
        Log.Debug("body.result.status: {}".format(body.result.status))
        Log.Debug("body.result.total_count: {}".format(body.result.status))

        # items that we found and add them to the matchable list
        items = body.result['items']  # type: List[Item]
        for i, item in enumerate(items):
            Log.Debug("body.result['items'][{}].content_id: {}".format(i, item.content_id))
            Log.Debug("body.result['items'][{}].product_id: {}".format(i, item.product_id))
            date = datetime.datetime.strptime(item.date, '%Y-%m-%d %H:%M:%S')
            score = int(SequenceMatcher(None, FanzaApi.normalize(keyword), item.content_id).ratio() * 100)
            result = MetadataSearchResult(
                id="fanza-" + item.content_id,
                name="[{}] {}".format(item.content_id.upper(), item.title),
                year=date.year,
                lang=Locale.Language.Japanese,
                thumb=item.imageURL.small,
                score=score)
            results.Append(result)
            Log.Info("Added search result: {}".format(result))

    def update(self, metadata, media, lang, force):
        """
        :type metadata: Movie
        :type media: Media
        :type lang: str
        :type force: bool
        """
        Log.Info("=========== Update ==========")
        Log.Info("Updating metadata: {}".format(metadata))
        Log.Info("Updating media: {}".format(media))
        Log.Info("Updating lang: {}".format(lang))
        Log.Info("Updating force: {}".format(force))

        # actual updating
        self.update_fanza(metadata, media)
        self.update_caribbeancom(metadata, media)

    def update_caribbeancom(self, metadata, media):
        if not metadata.id.startswith('carib-'): return
        id = metadata.id.lstrip(len('carib-'))

        # some debugging
        Log.Debug("id: {}".format(id))
        Log.Debug("metadata.id: {}".format(metadata.id))
        Log.Debug("metadata.title: {}".format(metadata.title))
        Log.Debug("metadata.year: {}".format(metadata.year))
        Log.Debug("media.id: {}".format(media.id))
        Log.Debug('media.items[0].parts[0].file: {}'.format(media.items[0].parts[0].file))

        # query fanza api
        item = CaribbeancomApi.get_item(id)

        # feed in information
        metadata.title = item.title
        metadata.original_title = item.title
        metadata.year = item.upload_date.year
        metadata.rating = float(item.rating)
        metadata.content_rating_age = 18
        metadata.content_rating = "Adult"
        metadata.originally_available_at = item.upload_date
        metadata.summary = "{}\n\n{}".format(item.title, item.description)
        # metadata.countries = {"Japan"}
        # metadata.writers = {}
        # metadata.directors = {}
        # metadata.producers = {}
        metadata.studio = "Caribbeancom"
        # metadata.tags = {}
        metadata.tagline = "??"

        # # adding part number
        # filename = media.items[0].parts[0].file
        # part = extract_part_number_from_filename(filename)
        # if part:
        #     Log.Debug("part: {}".format(part))
        # metadata.id = "{}-{}".format(item.content_id, part)
        # metadata.title = "{} (Part {})".format(item.content_id, part)
        # Log.Debug("new metadata.id: {}".format(metadata.id))
        # Log.Debug("new metadata.title: {}".format(metadata.title))

        # setting up posters
        for key in metadata.posters.keys(): del metadata.posters[key]
        poster_url = item.poster_url
        Log.Debug("poster_url: {}".format(poster_url))
        metadata.posters[poster_url] = Proxy.Media(HTTP.Request(poster_url))
        # metadata.posters[2] = Proxy.Media(HTTP.Request(item.imageURL.large))
        # metadata.posters[3] = Proxy.Media(HTTP.Request(item.imageURL.small))

        # setting up artworks
        # for key in metadata.art.keys(): del metadata.art[key]
        # for key in item.sampleImageUrl.sample_s:
        #     del metadata.art[key]
        # # poster_url = item.imageURL.small
        # # Log.Debug("poster_url: {}".format(poster_url))
        # metadata.posters[poster_url] = Proxy.Media(HTTP.Request(poster_url))

    def update_fanza(self, metadata, media):
        if not metadata.id.startswith('fanza-'): return
        id = metadata.id.lstrip(len('fanza-'))

        # some debugging
        Log.Debug("id: {}".format(id))
        Log.Debug("metadata.id: {}".format(metadata.id))
        Log.Debug("metadata.title: {}".format(metadata.title))
        Log.Debug("metadata.year: {}".format(metadata.year))
        Log.Debug("media.id: {}".format(media.id))
        Log.Debug('media.items[0].parts[0].file: {}'.format(media.items[0].parts[0].file))

        # query fanza api
        body = FanzaApi.get_item(id)
        Log.Debug("body.result.status: {}".format(body.result.status))
        Log.Debug("body.result.total_count: {}".format(body.result.status))
        Log.Debug("body.result['items'][0].content_id: {}".format(body.result['items'][0].content_id))
        Log.Info("Found number of items: {}".format(body.result.total_count))

        # feed in information
        item = body.result['items'][0]  # type: Item
        summary = FanzaApi.get_product_description(item.URL)
        date = datetime.datetime.strptime(item.date, '%Y-%m-%d %H:%M:%S')
        metadata.title = item.content_id.upper()
        metadata.original_title = item.title
        metadata.year = date.year
        metadata.rating = float(item.review.average)
        metadata.content_rating_age = 18
        metadata.content_rating = "Adult"
        metadata.originally_available_at = date
        metadata.summary = "{}\n\n{}".format(item.title, summary)
        # metadata.countries = {"Japan"}
        # metadata.writers = {}
        # metadata.directors = {}
        # metadata.producers = {}
        metadata.studio = "??"
        # metadata.tags = {}
        metadata.tagline = "??"

        # adding part number
        filename = media.items[0].parts[0].file
        part = extract_part_number_from_filename(filename)
        if part:
            Log.Debug("part: {}".format(part))
        metadata.id = "{}-{}".format(item.content_id, part)
        metadata.title = "{} (Part {})".format(item.content_id, part)
        Log.Debug("new metadata.id: {}".format(metadata.id))
        Log.Debug("new metadata.title: {}".format(metadata.title))

        # setting up posters
        for key in metadata.posters.keys(): del metadata.posters[key]
        poster_url = item.imageURL.small
        Log.Debug("poster_url: {}".format(poster_url))
        metadata.posters[poster_url] = Proxy.Media(HTTP.Request(poster_url))
        # metadata.posters[2] = Proxy.Media(HTTP.Request(item.imageURL.large))
        # metadata.posters[3] = Proxy.Media(HTTP.Request(item.imageURL.small))

        # setting up artworks
        # for key in metadata.art.keys(): del metadata.art[key]
        # for key in item.sampleImageUrl.sample_s:
        #     del metadata.art[key]
        # # poster_url = item.imageURL.small
        # # Log.Debug("poster_url: {}".format(poster_url))
        # metadata.posters[poster_url] = Proxy.Media(HTTP.Request(poster_url))
