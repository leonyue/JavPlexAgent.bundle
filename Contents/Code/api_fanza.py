from munch import munchify
from requests import get, Response
from pyquery import PyQuery as pq

api_id = "Ngdp9rsHvCZ9EWrv1LNU"
affiliate_id = "chokomomo-990"


class FanzaApi(object):

    @staticmethod
    def normalize(keyword):
        """
        :type keyword: str
        :rtype: str
        """
        keyword = keyword.lower()
        keyword = keyword.strip()
        keyword = keyword.replace("-", "00")
        keyword = keyword.replace("dsvr", "13dsvr")
        keyword = keyword.replace("313dsvr", "13dsvr")
        keyword = keyword.replace("avopvr", "h_1158avopvr")
        keyword = keyword.replace("kmvr", "84kmvr")
        keyword = keyword.replace("bi84kmvr", "h_1285bikmvr")
        keyword = keyword.replace("bzvr", "84bzvr")
        keyword = keyword.replace("crvr", "h_1155crvr")
        keyword = keyword.replace("exvr", "84exvr")
        keyword = keyword.replace("vvvr", "84vvvr")
        keyword = keyword.replace("dtvr", "24dtvr")
        keyword = keyword.replace("scvr", "h_565scvr")
        keyword = keyword.replace("wpvr", "2wpvr")
        keyword = keyword.replace("mxvr", "h_1282mxvr")
        keyword = keyword.replace("tmavr", "55tmavr")
        keyword = keyword.replace("vovs", "h_1127vovs")
        keyword = keyword.replace("cafr", "h_1116cafr")
        keyword = keyword.replace("tpvr", "h_1256tpvr")
        return keyword

    @staticmethod
    def get_item_list(keyword):
        """
        :type keyword: str
        :rtype: GetItemListBody
        """
        return munchify(get("https://api.dmm.com/affiliate/v3/ItemList", params={
            "api_id": api_id,
            "affiliate_id": affiliate_id,
            "site": "FANZA",
            "service": "digital",
            "floor": "videoa",
            "hits": "10",
            "sort": "date",
            "keyword": FanzaApi.normalize(keyword),
            "output": "json"
        }).json())

    @staticmethod
    def get_product_description(url):
        """
        :type url: str
        :rtype: str
        """
        return pq(url)(".mg-b20.lh4").text().rstrip()


# noinspection SpellCheckingInspection
class Item(object):
    class Review(object):
        count = 0  # Stub
        average = "Stub"

    class ImageUrl(object):
        list = "Stub"
        small = "Stub"
        large = "Stub"

    class SampleImageUrl(object):
        class Sample(object):
            image = ["Stub"]

        sample_s = Sample()

    class SampleMovieURL(object):
        sp_flag = 0  # Stub
        size_560_360 = "Stub"
        size_644_414 = "Stub"
        size_720_480 = "Stub"
        size_476_306 = "Stub"

    class Prices(object):
        class Deliveries(object):
            class Delivery(object):
                type = "Stub"
                price = "Stub"

            delivery = Delivery()

        deliveries = Deliveries()
        price = "Stub"

    class ItemInfo(object):
        class Info(object):
            id = 0  # Stub
            name = "Stub"

        genre = Info()
        series = Info()
        maker = Info()
        actress = Info()
        director = Info()
        label = Info()

    service_code = "Stub"
    service_name = "Stub"
    floor_code = "Stub"
    floor_name = "Stub"
    category_name = "Stub"
    content_id = "Stub"
    product_id = "Stub"
    title = "Stub"
    volume = "Stub"
    review = Review
    url = "Stub"
    urLsp = "Stub"
    affiliateUrl = "Stub"
    affiliateUrLsp = "Stub"
    imageURL = ImageUrl
    sampleImageUrl = SampleImageUrl()
    sampleMovieURL = SampleMovieURL()
    prices = Prices()
    date = "Stub"
    iteminfo = ItemInfo()


class GetItemListBody(object):
    class Request(object):
        class Parameters(object):
            api_id = "Stub"
            affiliate_id = "Stub"
            site = "Stub"
            service = "Stub"
            floor = "Stub"
            hits = "Stub"
            sort = "Stub"
            keyword = "Stub"
            output = "Stub"

        parameters = Parameters()

    class Result(object):
        status = 0  # Stub
        result_count = 0  # Stub
        total_count = 0  # Stub
        first_position = 0  # Stub
        items = [Item()]

    request = Request()
    result = Result()
#
